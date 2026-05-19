package main

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
	"go.mongodb.org/mongo-driver/bson"
)

// ---------------------------------------------------------------------------
// mockChangeStream — a ChangeWatcher that yields a fixed list of bson.M docs
// ---------------------------------------------------------------------------

type mockChangeStream struct {
	changes []bson.M
	pos     int
	decodeErr error
	streamErr error
}

func (m *mockChangeStream) Next(_ context.Context) bool {
	return m.pos < len(m.changes)
}

func (m *mockChangeStream) Decode(val interface{}) error {
	if m.decodeErr != nil {
		m.pos++
		return m.decodeErr
	}
	ptr := val.(*bson.M)
	*ptr = m.changes[m.pos]
	m.pos++
	return nil
}

func (m *mockChangeStream) Close(_ context.Context) error { return nil }
func (m *mockChangeStream) Err() error                    { return m.streamErr }

// ---------------------------------------------------------------------------
// processChangeEvent — unit tests
// ---------------------------------------------------------------------------

func TestProcessChangeEvent_InsertEmitsMessage(t *testing.T) {
	change := bson.M{
		"operationType": "insert",
		"fullDocument":  bson.M{"comment": "hello", "author": "Alice"},
	}
	msg, ok := processChangeEvent(change)
	if !ok {
		t.Fatal("expected shouldEmit=true for insert event")
	}
	if !strings.HasPrefix(msg, "data: ") {
		t.Errorf("expected SSE prefix 'data: ', got: %q", msg)
	}
	if !strings.HasSuffix(msg, "\n\n") {
		t.Errorf("expected SSE suffix '\\n\\n', got: %q", msg)
	}
}

func TestProcessChangeEvent_NonInsertSkipped(t *testing.T) {
	for _, opType := range []string{"update", "delete", "replace", "drop"} {
		change := bson.M{
			"operationType": opType,
			"fullDocument":  bson.M{"comment": "x"},
		}
		_, ok := processChangeEvent(change)
		if ok {
			t.Errorf("op=%q: expected shouldEmit=false, got true", opType)
		}
	}
}

func TestProcessChangeEvent_MissingFullDocumentSkipped(t *testing.T) {
	change := bson.M{"operationType": "insert"} // no fullDocument
	_, ok := processChangeEvent(change)
	if ok {
		t.Fatal("expected shouldEmit=false when fullDocument is absent")
	}
}

func TestProcessChangeEvent_WrongFullDocumentTypeSkipped(t *testing.T) {
	change := bson.M{
		"operationType": "insert",
		"fullDocument":  "not-a-bson-map",
	}
	_, ok := processChangeEvent(change)
	if ok {
		t.Fatal("expected shouldEmit=false when fullDocument is not bson.M")
	}
}

// ---------------------------------------------------------------------------
// newStreamHandler — handler-level tests via Fiber's app.Test()
// ---------------------------------------------------------------------------

func newTestApp(watchFn func(ctx context.Context) (ChangeWatcher, error)) *fiber.App {
	app := fiber.New(fiber.Config{DisableStartupMessage: true})
	app.Get("/stream", newStreamHandler(watchFn))
	return app
}

func TestStreamHandler_ResponseHeaders(t *testing.T) {
	app := newTestApp(func(ctx context.Context) (ChangeWatcher, error) {
		return &mockChangeStream{}, nil
	})

	req := httptest.NewRequest("GET", "/stream", nil)
	resp, err := app.Test(req, 3000)
	if err != nil {
		t.Fatalf("app.Test failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}
	if ct := resp.Header.Get("Content-Type"); ct != "text/event-stream" {
		t.Errorf("expected Content-Type 'text/event-stream', got %q", ct)
	}
	if cc := resp.Header.Get("Cache-Control"); cc != "no-cache" {
		t.Errorf("expected Cache-Control 'no-cache', got %q", cc)
	}
}

func TestStreamHandler_EmitsInsertEventsAsSSE(t *testing.T) {
	changes := []bson.M{
		{
			"operationType": "insert",
			"fullDocument":  bson.M{"comment": "great stream", "author": "Alice"},
		},
		{
			"operationType": "insert",
			"fullDocument":  bson.M{"comment": "love it", "author": "Bob"},
		},
	}
	app := newTestApp(func(ctx context.Context) (ChangeWatcher, error) {
		return &mockChangeStream{changes: changes}, nil
	})

	req := httptest.NewRequest("GET", "/stream", nil)
	resp, err := app.Test(req, 3000)
	if err != nil {
		t.Fatalf("app.Test failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	events := strings.Split(strings.TrimRight(bodyStr, "\n"), "\n\n")
	// TrimRight leaves one trailing empty string; filter it out
	var nonEmpty []string
	for _, e := range events {
		if strings.TrimSpace(e) != "" {
			nonEmpty = append(nonEmpty, e)
		}
	}

	if len(nonEmpty) != 2 {
		t.Fatalf("expected 2 SSE events, got %d: %q", len(nonEmpty), bodyStr)
	}
	for i, ev := range nonEmpty {
		if !strings.HasPrefix(ev, "data: ") {
			t.Errorf("event[%d] missing 'data: ' prefix: %q", i, ev)
		}
	}
}

func TestStreamHandler_SkipsNonInsertEvents(t *testing.T) {
	changes := []bson.M{
		{"operationType": "update", "fullDocument": bson.M{"comment": "x"}},
		{"operationType": "insert", "fullDocument": bson.M{"comment": "hello"}},
		{"operationType": "delete"},
	}
	app := newTestApp(func(ctx context.Context) (ChangeWatcher, error) {
		return &mockChangeStream{changes: changes}, nil
	})

	req := httptest.NewRequest("GET", "/stream", nil)
	resp, err := app.Test(req, 3000)
	if err != nil {
		t.Fatalf("app.Test failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	count := strings.Count(bodyStr, "data: ")
	if count != 1 {
		t.Errorf("expected exactly 1 SSE event (only the insert), got %d in: %q", count, bodyStr)
	}
}

func TestStreamHandler_WatchErrorReturnsEmptyBody(t *testing.T) {
	app := newTestApp(func(ctx context.Context) (ChangeWatcher, error) {
		return nil, fmt.Errorf("mongo unavailable")
	})

	req := httptest.NewRequest("GET", "/stream", nil)
	resp, err := app.Test(req, 3000)
	if err != nil {
		t.Fatalf("app.Test failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if len(strings.TrimSpace(string(body))) != 0 {
		t.Errorf("expected empty body on watch error, got: %q", string(body))
	}
}

func TestStreamHandler_DecodeErrorContinuesStream(t *testing.T) {
	// First event fails to decode; second succeeds. Only the second must appear.
	ms := &mockChangeStream{
		changes: []bson.M{
			{"operationType": "insert", "fullDocument": bson.M{"comment": "hello"}},
		},
	}
	ms.decodeErr = fmt.Errorf("decode failed")
	// Override: we want first Next() to return true but Decode to fail,
	// then second Next() returns true with good data, third returns false.
	// Build a custom mock instead.
	type entry struct {
		change bson.M
		err    error
	}
	entries := []entry{
		{err: fmt.Errorf("bad decode")},
		{change: bson.M{"operationType": "insert", "fullDocument": bson.M{"comment": "ok"}}},
	}
	type seqStream struct {
		entries []entry
		pos     int
	}
	seq := &struct {
		entries []entry
		pos     int
	}{entries: entries}

	watchFn := func(ctx context.Context) (ChangeWatcher, error) {
		return &funcChangeStream{
			nextFn: func(_ context.Context) bool { return seq.pos < len(seq.entries) },
			decodeFn: func(val interface{}) error {
				e := seq.entries[seq.pos]
				seq.pos++
				if e.err != nil {
					return e.err
				}
				*(val.(*bson.M)) = e.change
				return nil
			},
			closeFn: func(_ context.Context) error { return nil },
			errFn:   func() error { return nil },
		}, nil
	}

	app := newTestApp(watchFn)
	req := httptest.NewRequest("GET", "/stream", nil)
	resp, err := app.Test(req, 3000)
	if err != nil {
		t.Fatalf("app.Test failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	count := strings.Count(string(body), "data: ")
	if count != 1 {
		t.Errorf("expected 1 SSE event after decode error, got %d: %q", count, string(body))
	}
}

// funcChangeStream lets tests wire up each method independently.
type funcChangeStream struct {
	nextFn   func(ctx context.Context) bool
	decodeFn func(val interface{}) error
	closeFn  func(ctx context.Context) error
	errFn    func() error
}

func (f *funcChangeStream) Next(ctx context.Context) bool        { return f.nextFn(ctx) }
func (f *funcChangeStream) Decode(val interface{}) error         { return f.decodeFn(val) }
func (f *funcChangeStream) Close(ctx context.Context) error      { return f.closeFn(ctx) }
func (f *funcChangeStream) Err() error                           { return f.errFn() }

// Keep the bufio import used by the stream writer in main.go from being flagged
// unused by the test binary; it is referenced only in non-test code.
var _ = (*bufio.Writer)(nil)

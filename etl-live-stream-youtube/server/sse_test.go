package main

import (
	"encoding/json"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/bson"
)

func TestFormatSSEMessage_HasCorrectPrefix(t *testing.T) {
	doc := bson.M{"comment": "hello", "author": "Alice"}
	msg, err := formatSSEMessage(doc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasPrefix(msg, "data: ") {
		t.Errorf("expected prefix 'data: ', got: %q", msg)
	}
}

func TestFormatSSEMessage_HasDoubleNewlineSuffix(t *testing.T) {
	doc := bson.M{"comment": "hello"}
	msg, err := formatSSEMessage(doc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasSuffix(msg, "\n\n") {
		t.Errorf("expected suffix '\\n\\n', got: %q", msg)
	}
}

func TestFormatSSEMessage_PayloadIsValidJSON(t *testing.T) {
	doc := bson.M{
		"video_id": "vid1",
		"comment":  "great stream",
		"sentiment": bson.M{
			"classification": "positive",
			"compound":       0.8,
		},
	}
	msg, err := formatSSEMessage(doc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	payload := strings.TrimSuffix(strings.TrimPrefix(msg, "data: "), "\n\n")
	var decoded map[string]interface{}
	if err := json.Unmarshal([]byte(payload), &decoded); err != nil {
		t.Errorf("payload is not valid JSON: %v", err)
	}
}

func TestFormatSSEMessage_EmptyDocument(t *testing.T) {
	doc := bson.M{}
	msg, err := formatSSEMessage(doc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	payload := strings.TrimSuffix(strings.TrimPrefix(msg, "data: "), "\n\n")
	if payload != "{}" {
		t.Errorf("expected '{}', got: %q", payload)
	}
}

func TestFormatSSEMessage_FieldsPreservedInPayload(t *testing.T) {
	doc := bson.M{"author": "Bob", "comment": "nice video"}
	msg, err := formatSSEMessage(doc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	payload := strings.TrimSuffix(strings.TrimPrefix(msg, "data: "), "\n\n")
	var decoded map[string]interface{}
	if err := json.Unmarshal([]byte(payload), &decoded); err != nil {
		t.Fatalf("payload is not valid JSON: %v", err)
	}
	if decoded["author"] != "Bob" {
		t.Errorf("expected author='Bob', got: %v", decoded["author"])
	}
	if decoded["comment"] != "nice video" {
		t.Errorf("expected comment='nice video', got: %v", decoded["comment"])
	}
}

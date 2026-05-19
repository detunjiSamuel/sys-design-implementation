import base64
import os
import subprocess
import sys

import cv2
import eventlet
import socketio
import structlog
from dotenv import load_dotenv
from eventlet import wsgi

from logging_config import configure_logging

log = structlog.get_logger(__name__)


def main():
    load_dotenv()
    configure_logging()

    sio = socketio.Server(cors_allowed_origins='*')
    app = socketio.WSGIApp(sio)

    video_id = ""  # temp id for me to work with

    try:
        stream_url = (
            subprocess.check_output(
                ["yt-dlp", "-f", "best", "-g",
                    f"https://www.youtube.com/watch?v={video_id}"]
            ).decode("utf-8").strip()
        )
    except subprocess.CalledProcessError as e:
        log.error("stream_url_fetch_error", error=str(e))
        sys.exit(1)

    streaming_started = False

    def generate_frames():
        nonlocal streaming_started
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            log.error("video_stream_open_error")
            streaming_started = False
            return
        while streaming_started:
            ret, frame = cap.read()
            if not ret:
                break
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = base64.b64encode(buffer).decode('utf-8')
            sio.emit('video_frame', frame_bytes)
            sio.sleep(1)
        cap.release()
        streaming_started = False

    @sio.event
    def connect(sid, environ):
        nonlocal streaming_started
        log.info("client_connected", sid=sid)
        if not streaming_started:
            streaming_started = True
            sio.start_background_task(generate_frames)

    @sio.event
    def disconnect(sid):
        log.info("client_disconnected", sid=sid)

    port = int(os.getenv("PORT", 5000))
    wsgi.server(eventlet.listen(('', port)), app)


if __name__ == '__main__':
    main()

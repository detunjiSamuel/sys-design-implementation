import cv2
import socketio
import base64
import eventlet
from eventlet import wsgi
import subprocess
import sys

import structlog
from dotenv import load_dotenv
import os

from logging_config import configure_logging

load_dotenv()
configure_logging()

log = structlog.get_logger(__name__)


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

    global streaming_started

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
    log.info("client_connected", sid=sid)
    global streaming_started
    if not streaming_started:
        streaming_started = True
        sio.start_background_task(generate_frames)


@sio.event
def disconnect(sid):
    log.info("client_disconnected", sid=sid)


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    wsgi.server(eventlet.listen(('', port)), app)

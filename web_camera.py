from flask import Response, Flask, redirect, render_template, request, session, url_for
from threading import Lock
from waitress import serve
import cv2
import logging
import signal
import sys
import time
import os

# Keep OpenCV logs quiet so terminal output stays focused on app-level messages.
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")

app = Flask(__name__)
app.secret_key = "secret_password_for_sessions"


class _SuppressCameraErrorAccessLog(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return "GET /camera_error" not in message


logging.getLogger("werkzeug").addFilter(_SuppressCameraErrorAccessLog())

# Simple demo credentials for the login page.
USERNAME = "admin"
PASSWORD = "rpi4cam"

try:
    set_log_level = getattr(cv2, "setLogLevel", None)
    log_level_error = getattr(cv2, "LOG_LEVEL_ERROR", None)
    if callable(set_log_level) and log_level_error is not None:
        set_log_level(log_level_error)
except Exception:
    pass


class CameraStream:
    """Thread-safe OpenCV camera wrapper that returns JPEG frames."""

    _JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, 80]

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self.device_source = "/dev/video0"
        self.capture = None
        self._lock = Lock()
        self._max_read_failures = 2
        self._read_failures = 0
        self._last_error = "Camera not initialized"
        self._last_logged_error = ""
        self._last_connection_message = ""
        self._connection_message_time = 0
        self._was_connected = False
        self._paused = False

    def _set_error(self, message: str):
        self._last_error = message
        if message != self._last_logged_error:
            self._last_logged_error = message
            print(f"[camera] {message}")

    def _set_connected(self):
        self._read_failures = 0
        self._last_error = ""
        self._last_logged_error = ""
        self._was_connected = True
        self._last_connection_message = "Camera connected"
        self._connection_message_time = time.monotonic()
        print("[camera] Camera connected")

    @staticmethod
    def _is_open(capture) -> bool:
        return capture is not None and capture.isOpened()

    def get_last_error(self):
        with self._lock:
            if self._last_error in {"Camera not initialized", "Camera not available", "Camera disconnected"}:
                return ""
            return self._last_error

    def get_last_connection_message(self):
        with self._lock:
            if self._connection_message_time and time.monotonic() - self._connection_message_time < 3:
                return self._last_connection_message, self._connection_message_time
            return "", 0

    def get_reconnect_message(self):
        with self._lock:
            if self._is_open(self.capture):
                return ""
            if self._was_connected:
                return "Camera disconnected. Waiting for reconnection..."
            return "Waiting for a camera to be connected..."

    def _open_capture(self, source):
        # V4L2 is the native Linux backend for USB cameras on Raspberry Pi/Linux.
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        return cap

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def resume(self):
        with self._lock:
            self._paused = False

    def activate(self):
        with self._lock:
            if self._paused:
                return False
            if self._is_open(self.capture):
                return True

            cap = self._open_capture(self.device_source)
            if cap is None:
                self._set_error("Camera not available")
                return False

            self.capture = cap
            self._set_connected()
            return True

    def is_active(self):
        with self._lock:
            return self._is_open(self.capture)

    def read_jpeg(self):
        with self._lock:
            cap = self.capture

        if cap is None or not cap.isOpened():
            return None

        ok, frame = cap.read()
        if not ok:
            with self._lock:
                self._read_failures += 1
                # Short camera hiccups can happen; only drop the capture after
                # repeated failures so transient glitches do not force reconnect.
                if self._read_failures >= self._max_read_failures:
                    active_capture = self.capture
                    if active_capture is not None and active_capture.isOpened():
                        active_capture.release()
                    self.capture = None
                    self._set_error("Camera disconnected")
            return None

        with self._lock:
            self._read_failures = 0

        ok, encoded = cv2.imencode(".jpg", frame, self._JPEG_PARAMS)
        if not ok:
            return None

        return encoded.tobytes()

    def release(self):
        with self._lock:
            active_capture = self.capture
            if active_capture is not None and active_capture.isOpened():
                active_capture.release()
            self.capture = None
            self._read_failures = 0
            self._paused = True


camera = CameraStream(device_index=0)


def is_logged_in() -> bool:
    return session.get("logged_in", False)


@app.route("/", methods=["GET"])
def home():
    if is_logged_in():
        return redirect(url_for("video_page"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("video_page"))

        return render_template("cam_login.html", error="Invalid username or password")

    return render_template("cam_login.html", error=None)


@app.route("/video", methods=["GET"])
def video_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("cam_live.html")


_STREAM_FPS = 30
_FRAME_INTERVAL = 1.0 / _STREAM_FPS
_RECONNECT_DELAY = 2.0
_TRANSIENT_READ_DELAY = 0.05


def generate_mjpeg():
    # Browser MJPEG expects a continuous stream of JPEG frames separated by
    # multipart boundaries. This generator yields one frame payload at a time.
    next_frame = time.monotonic()
    while True:
        if not camera.activate():
            if camera.is_paused():
                break
            time.sleep(_RECONNECT_DELAY)
            next_frame = time.monotonic()
            continue

        frame_bytes = camera.read_jpeg()
        if frame_bytes is None:
            if not camera.is_active():
                time.sleep(_RECONNECT_DELAY)
            else:
                time.sleep(_TRANSIENT_READ_DELAY)
            next_frame = time.monotonic()
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

        # Keep output near target FPS by sleeping only the remaining frame time.
        next_frame += _FRAME_INTERVAL
        sleep_for = next_frame - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            next_frame = time.monotonic()


@app.route("/stream", methods=["GET"])
def stream():
    if not is_logged_in():
        return redirect(url_for("login"))

    camera.resume()
    return Response(generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/camera_error", methods=["GET"])
def camera_error():
    if not is_logged_in():
        return {"error": "", "connection_message": "", "reconnect_message": ""}, 401
    connection_message, connection_time = camera.get_last_connection_message()
    return {
        "error": camera.get_last_error(),
        "connection_message": connection_message,
        "connection_time": connection_time,
        "reconnect_message": camera.get_reconnect_message(),
    }


@app.route("/logout", methods=["GET"])
def logout():
    camera.release()
    session.clear()
    return redirect(url_for("login"))


def handle_sigint(_sig, _frame):
    print("\nTerminated...")
    camera.release()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_sigint)
    serve(app, host="0.0.0.0", port=5001, threads=8)
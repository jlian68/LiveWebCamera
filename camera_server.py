#!/usr/bin/env python3
"""
LiveWebCamera - Web Camera Server for Raspberry Pi 4
Capstone project for Coursera's An Introduction to Programming the Internet of Things (IOT) Specialization

Streams live video from a connected camera (Pi Camera Module or USB webcam)
over HTTP using MJPEG (Motion JPEG) format, accessible from any web browser
on the local network.
"""

import cv2
import time
import logging
from flask import Flask, Response, render_template

# ── Configuration ──────────────────────────────────────────────────────────────
CAMERA_INDEX = 0        # 0 = first camera device (/dev/video0)
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480
JPEG_QUALITY = 80       # JPEG encoding quality (1‑100)
SERVER_HOST  = "0.0.0.0"
SERVER_PORT  = 5000
# ───────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Single shared camera instance – opened once, reused across all stream requests.
_camera: "VideoCamera | None" = None


class VideoCamera:
    """Wraps an OpenCV VideoCapture and provides JPEG‑encoded frames."""

    def __init__(self, index: int = CAMERA_INDEX):
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera at index {index}. "
                "Make sure a camera is connected and not in use by another process."
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        logger.info("Camera opened: %dx%d", FRAME_WIDTH, FRAME_HEIGHT)

    def get_frame(self) -> bytes | None:
        """Capture one frame and return it as a JPEG byte‑string, or None on error."""
        success, frame = self.cap.read()
        if not success:
            logger.warning("Failed to read frame from camera.")
            return None
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        ok, buffer = cv2.imencode(".jpg", frame, encode_params)
        return buffer.tobytes() if ok else None

    def release(self):
        """Release the underlying capture device."""
        self.cap.release()
        logger.info("Camera released.")


def get_camera() -> VideoCamera:
    """Return the shared VideoCamera, creating it on first call."""
    global _camera
    if _camera is None:
        _camera = VideoCamera()
    return _camera


def generate_mjpeg(camera: VideoCamera):
    """Generator that yields an infinite MJPEG stream from *camera*."""
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue
        yield boundary + frame + b"\r\n"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main HTML page."""
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """Return a streaming MJPEG response using the shared camera instance."""
    return Response(
        generate_mjpeg(get_camera()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Initialise the camera before accepting connections so startup errors are
    # reported immediately rather than on the first streaming request.
    get_camera()
    logger.info("Starting LiveWebCamera server on http://%s:%d", SERVER_HOST, SERVER_PORT)
    logger.info("Open a browser and navigate to http://<Pi-IP-address>:%d", SERVER_PORT)
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)

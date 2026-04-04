# LiveWebCamera

**Web Camera Server based on Raspberry Pi 4**

Capstone project for Coursera's
[An Introduction to Programming the Internet of Things (IOT) Specialization](https://www.coursera.org/specializations/iot)
offered by UC Irvine.

LiveWebCamera streams live video from a connected camera (Raspberry Pi Camera
Module or USB webcam) over HTTP using MJPEG, so any device on the same network
can watch the feed in a standard web browser — no plugins required.

---

## Features

- **MJPEG live stream** served over HTTP
- Works with the **Raspberry Pi Camera Module** or any **USB webcam**
- Clean, responsive web UI (dark-themed) accessible from any browser
- Configurable resolution, JPEG quality, host and port
- Pure Python — built with [Flask](https://flask.palletsprojects.com/) and
  [OpenCV](https://opencv.org/)

---

## Hardware Requirements

| Component | Details |
|-----------|---------|
| Board | Raspberry Pi 4 (also works on Pi 3B+) |
| Camera | Pi Camera Module v1/v2/v3 **or** any USB webcam |
| OS | Raspberry Pi OS (64-bit Bookworm or Bullseye) |
| Network | Wi-Fi or Ethernet (to access stream from another device) |

---

## Software Requirements

- Python 3.9+
- pip

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/jlian68/LiveWebCamera.git
cd LiveWebCamera

# 2. (Recommended) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

### Raspberry Pi Camera Module (CSI ribbon cable)

Enable the camera interface if you have not already done so:

```bash
sudo raspi-config
# Interface Options → Camera → Enable → Reboot
```

OpenCV accesses the Pi Camera through the V4L2 driver.  Load it once and make
the change persistent:

```bash
sudo modprobe bcm2835-v4l2
echo "bcm2835-v4l2" | sudo tee -a /etc/modules
```

### USB Webcam

Plug in the webcam and verify it is detected:

```bash
ls /dev/video*   # should show /dev/video0 (or similar)
```

---

## Configuration

Open `camera_server.py` and adjust the constants near the top of the file:

```python
CAMERA_INDEX = 0        # 0 = /dev/video0; change if using a different device
FRAME_WIDTH  = 640      # Capture width in pixels
FRAME_HEIGHT = 480      # Capture height in pixels
JPEG_QUALITY = 80       # JPEG quality (1–100); lower = faster, higher = sharper
SERVER_HOST  = "0.0.0.0"  # Listen on all interfaces
SERVER_PORT  = 5000        # TCP port
```

---

## Running the Server

```bash
python3 camera_server.py
```

You should see output similar to:

```
2024-01-01 12:00:00  INFO  Starting LiveWebCamera server on http://0.0.0.0:5000
2024-01-01 12:00:00  INFO  Open a browser and navigate to http://<Pi-IP-address>:5000
2024-01-01 12:00:00  INFO  Camera opened: 640x480
```

### Viewing the stream

1. Find your Pi's IP address: `hostname -I`
2. Open a browser on **any device on the same network** and navigate to
   `http://<Pi-IP-address>:5000`

### Running as a systemd service (optional)

To start the server automatically on boot:

```bash
sudo nano /etc/systemd/system/livewebcamera.service
```

Paste the following (adjust paths as needed):

```ini
[Unit]
Description=LiveWebCamera streaming server
After=network.target

[Service]
ExecStart=/home/pi/LiveWebCamera/.venv/bin/python3 /home/pi/LiveWebCamera/camera_server.py
WorkingDirectory=/home/pi/LiveWebCamera
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable livewebcamera
sudo systemctl start  livewebcamera
```

---

## Project Structure

```
LiveWebCamera/
├── camera_server.py      # Flask application – MJPEG streaming logic
├── templates/
│   └── index.html        # Web page served to the browser
├── static/
│   └── style.css         # Responsive dark-themed stylesheet
├── requirements.txt      # Python dependencies
└── README.md
```

---

## How It Works

1. `VideoCamera` opens the camera device via OpenCV and configures resolution.
2. `generate_mjpeg()` is a Python generator that continuously captures frames,
   JPEG-encodes them, and yields them wrapped in MJPEG multipart boundaries.
3. Flask's `/video_feed` route streams that generator as a
   `multipart/x-mixed-replace` HTTP response — the browser renders each frame
   in-place, producing smooth live video without any JavaScript polling.

---

## License

This project is released under the [MIT License](LICENSE).


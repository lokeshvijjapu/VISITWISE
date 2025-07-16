# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Raspberry Pi motion-triggered video recorder with timed cleanup,
systemd watchdog integration, and parallel uploads.
Reads Device ID from file (set via BLE), records clips on motion,
uploads in parallel, and deletes all clips older than TTL.
"""
import os
import time
import signal
import logging
import getpass
import threading
import subprocess
from datetime import datetime
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor

import sdnotify
import requests
import cv2
import numpy as np
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from libcamera import Transform

# -------- Configuration --------
VIDEO_DURATION   = 5              # seconds per clip
VIDEO_RESOLUTION = (1280, 1080)
FRAME_RATE       = 60
MOTION_THRESHOLD = 30             # frame diff threshold
MIN_MOTION_AREA  = 500            # pixels
OUTPUT_DIR       = f"/home/{getpass.getuser()}/videos"
ROTATION         = Transform(rotation=-270)

# Cleanup TTL settings
CLEANUP_TTL      = 60             # seconds; delete files older than this
CLEANUP_INTERVAL = 30             # seconds between cleanup runs

# Device ID file (written via BLE)
DEVICE_ID_FILE   = '/home/neonflake/Desktop/visitwise/device_id.txt'

# Systemd notifier
notifier = sdnotify.SystemdNotifier()

# Motion event queue and upload executor
motion_queue = Queue()
upload_executor = ThreadPoolExecutor()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Shutdown handler
def shutdown(signum, frame):
    logging.info("Shutting down...")
    try:
        picam2.stop()
        picam2.close()
    except NameError:
        pass
    notifier.notify("STOPPING=1")
    exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# Device ID loader
def get_device_id():
    try:
        with open(DEVICE_ID_FILE, 'r') as f:
            return f.read().strip()
    except Exception:
        return 'DEV_DEFAULT'

# Ensure output directory
def ensure_output_directory():
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"Cannot write to {OUTPUT_DIR}: {e}")
        return False

# Cleanup worker deletes all files older than TTL
def cleanup_worker():
    while True:
        cutoff = time.time() - CLEANUP_TTL
        for fname in os.listdir(OUTPUT_DIR):
            path = os.path.join(OUTPUT_DIR, fname)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                try:
                    os.remove(path)
                    logging.info(f"Deleted old file: {path}")
                except Exception:
                    pass
        time.sleep(CLEANUP_INTERVAL)

# Upload function includes Device ID parameter
def upload_video(path):
    device_id = get_device_id()
    try:
        with open(path, 'rb') as vf:
            files = {'file': (os.path.basename(path), vf, 'video/mp4')}
            params = {'deviceId': device_id}
            logging.info(f"Uploading {path} with deviceId={device_id}")
            r = requests.post('https://visit-wise-llm.jayaprakash.cloud/upload-video',
                              files=files, params=params, timeout=20)
        if r.status_code == 200:
            logging.info(f"Upload succeeded: {path}")
        else:
            logging.warning(f"Upload failed ({r.status_code}): {r.text}")
    except Exception as e:
        logging.error(f"Upload error: {e}")

# Record a 5s clip and convert to MP4
def record_clip(picam2, encoder):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    raw = os.path.join(OUTPUT_DIR, f"motion_{timestamp}.h264")
    mp4 = raw.replace('.h264', '.mp4')
    try:
        out = FileOutput(raw)
        picam2.start_encoder(encoder, out)
        time.sleep(VIDEO_DURATION)
        picam2.stop_encoder()
        out.close()
        cmd = ["ffmpeg", "-y", "-i", raw, "-c:v", "copy", "-c:a", "aac", mp4]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logging.error(f"FFmpeg failed: {proc.stderr}")
            return None
        os.remove(raw)
        return mp4
    except Exception as e:
        logging.error(f"Record/convert error: {e}")
        return None

# Worker that processes motion queue sequentially
def motion_worker(picam2, encoder):
    while True:
        try:
            motion_queue.get(timeout=1)
            clip = record_clip(picam2, encoder)
            if clip:
                upload_executor.submit(upload_video, clip)
        except Empty:
            continue

# Main function
def main():
    global picam2
    if not ensure_output_directory():
        logging.error("Exiting: cannot write output directory.")
        return

    # Initialize camera
    picam2 = Picamera2()
    cfg = picam2.create_video_configuration(
        main={"size": VIDEO_RESOLUTION, "format": "YUV420"},
        transform=ROTATION
    )
    picam2.configure(cfg)
    encoder = H264Encoder()
    picam2.start()

    # Start background workers
    threading.Thread(target=cleanup_worker, daemon=True).start()
    threading.Thread(target=motion_worker, args=(picam2, encoder), daemon=True).start()

    # Notify systemd that service is ready
    notifier.notify("READY=1")

    prev_frame = None
    try:
        while True:
            # Notify watchdog
            notifier.notify("WATCHDOG=1")

            # Capture and process frame
            frame = picam2.capture_array()
            gray = cv2.cvtColor(frame, cv2.COLOR_YUV420p2GRAY)
            if prev_frame is None:
                prev_frame = gray
                continue

            delta = cv2.absdiff(prev_frame, gray)
            _, thresh = cv2.threshold(delta, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if any(cv2.contourArea(c) > MIN_MOTION_AREA for c in contours):
                motion_queue.put(True)

            prev_frame = gray
            time.sleep(0.05)
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
        shutdown(None, None)

if __name__ == "__main__":
    main()
    main()

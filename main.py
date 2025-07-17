#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raspberry Pi motion-triggered video recorder with auto cleanup,
corrupt file handling, and automatic reboot logic.
"""
import os
import time
import signal
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

# ------------- Configuration -------------
VIDEO_DURATION   = 5
VIDEO_RESOLUTION = (1280, 1080)
FRAME_RATE       = 60
MOTION_THRESHOLD = 30
MIN_MOTION_AREA  = 500
OUTPUT_DIR       = f"/home/{getpass.getuser()}/videos"
ROTATION         = Transform(rotation=-270)

CLEANUP_TTL      = 60
CLEANUP_INTERVAL = 30

DEVICE_ID_FILE   = '/home/neonflake/Desktop/visitwise/device_id.txt'
MAX_CORRUPT_COUNT = 3
MAX_IDLE_SECONDS = 1800  # 30 minutes

notifier = sdnotify.SystemdNotifier()
motion_queue = Queue()
upload_executor = ThreadPoolExecutor()

picam2 = None
last_success_time = time.time()
corrupt_count = 0

# ------------- Graceful Shutdown -------------
def shutdown(signum, frame):
    try:
        picam2.stop()
        picam2.close()
    except:
        pass
    notifier.notify("STOPPING=1")
    exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# ------------- Utility Functions -------------
def reboot():
    os.system("sudo reboot")

def get_device_id():
    try:
        with open(DEVICE_ID_FILE, 'r') as f:
            return f.read().strip()
    except:
        return 'DEV_DEFAULT'

def ensure_output_directory():
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return True
    except:
        return False

def cleanup_worker():
    while True:
        cutoff = time.time() - CLEANUP_TTL
        for fname in os.listdir(OUTPUT_DIR):
            path = os.path.join(OUTPUT_DIR, fname)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                try:
                    os.remove(path)
                except:
                    pass
        time.sleep(CLEANUP_INTERVAL)

def upload_video(path):
    device_id = get_device_id()
    try:
        with open(path, 'rb') as vf:
            files = {'file': (os.path.basename(path), vf, 'video/mp4')}
            params = {'deviceId': device_id}
            requests.post('https://visit-wise-llm.jayaprakash.cloud/upload-video',
                          files=files, params=params, timeout=20)
    except:
        pass

def record_clip(picam2, encoder):
    global last_success_time, corrupt_count

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    raw = os.path.join(OUTPUT_DIR, f"motion_{timestamp}.h264")
    mp4 = raw.replace('.h264', '.mp4')

    try:
        out = FileOutput(raw)
        picam2.start_encoder(encoder, out)
        time.sleep(VIDEO_DURATION)
        picam2.stop_encoder()
        out.close()

        if os.path.getsize(raw) < 5000:
            corrupt_count += 1
            os.remove(raw)
            if corrupt_count >= MAX_CORRUPT_COUNT:
                reboot()
            return None

        cmd = ["ffmpeg", "-y", "-i", raw, "-c:v", "copy", "-c:a", "aac", mp4]
        subprocess.run(cmd, capture_output=True)
        os.remove(raw)
        last_success_time = time.time()
        corrupt_count = 0
        return mp4

    except:
        return None

def motion_worker(picam2, encoder):
    while True:
        try:
            motion_queue.get(timeout=1)
            clip = record_clip(picam2, encoder)
            if clip:
                upload_executor.submit(upload_video, clip)
        except Empty:
            continue

def idle_monitor():
    while True:
        if time.time() - last_success_time > MAX_IDLE_SECONDS:
            reboot()
        time.sleep(60)

def main():
    global picam2

    if not ensure_output_directory():
        return

    picam2 = Picamera2()
    cfg = picam2.create_video_configuration(
        main={"size": VIDEO_RESOLUTION, "format": "YUV420"},
        transform=ROTATION
    )
    picam2.configure(cfg)
    encoder = H264Encoder()
    picam2.start()

    threading.Thread(target=cleanup_worker, daemon=True).start()
    threading.Thread(target=motion_worker, args=(picam2, encoder), daemon=True).start()
    threading.Thread(target=idle_monitor, daemon=True).start()

    notifier.notify("READY=1")

    prev_frame = None
    try:
        while True:
            notifier.notify("WATCHDOG=1")
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
    except:
        shutdown(None, None)

if __name__ == "__main__":
    main()

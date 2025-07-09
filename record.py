# its working code of motion detection

import cv2
import numpy as np
import requests
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from datetime import datetime
import time
import os
import getpass
import threading
from libcamera import Transform

# Configuration
DEVICE_ID = "DEV3617"  # Replace with your device ID
API_URL = "https://visit-wise-llm.onrender.com/upload-video/"
VIDEO_DURATION = 5  # seconds
MOTION_THRESHOLD = 40  # Sensitivity for motion detection
#MIN_MOTION_AREA = 1500  # Increased for 720p resolution
MIN_MOTION_AREA = 500  # Increased for 480p resolution
OUTPUT_DIR = f"/home/{getpass.getuser()}/videos"
COOLDOWN_PERIOD = 5  # seconds to wait after recording
UPLOAD_TIMEOUT = 20  # seconds for upload timeout
#VIDEO_RESOLUTION = (640, 480)  # 480p resolution
VIDEO_RESOLUTION = (1280, 1080)  # 720p resolution

FRAME_RATE = 60
ROTATION = Transform(rotation=-270)  # Rotate 90 degrees clockwise

def ensure_output_directory():
    """Ensure the output directory exists and is writable."""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_file = os.path.join(OUTPUT_DIR, ".test_write")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        print("Output directory verified")
        return True
    except Exception as e:
        print(f"Error: Cannot write to output directory {OUTPUT_DIR}: {str(e)}")
        return False

def upload_video(video_path):
    """Upload video to API with timeout."""
    try:
        with open(video_path, 'rb') as video_file:
            files = {'file': (os.path.basename(video_path), video_file, 'video/mp4')}
            params = {'deviceId': DEVICE_ID}
            print(f"Uploading video: {video_path}")
            response = requests.post(API_URL, files=files, params=params, timeout=UPLOAD_TIMEOUT)
            if response.status_code == 200:
                print(f"Video uploaded successfully: {video_path}")
                try:
                    os.remove(video_path)
                    h264_path = video_path.replace('.mp4', '.h264')
                    if os.path.exists(h264_path):
                        os.remove(h264_path)
                    print(f"Deleted local files: {video_path}, {h264_path}")
                except Exception as e:
                    print(f"Error deleting local files: {str(e)}")
		   # print(f"Upload successful: Status {response.status_code}, {response.text}")
                return True
            else:
                print(f"Upload failed: Status {response.status_code}, {response.text}")
                return False
    except requests.exceptions.RequestException as e:
        print(f"Upload error: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error during upload: {str(e)}")
        return False

def record_and_convert(picam2, encoder, video_path):
    """Record video and convert to MP4."""
    try:
        output = FileOutput(video_path)
        print(f"Starting recording: {video_path}")
        picam2.start_encoder(encoder, output)
        time.sleep(VIDEO_DURATION)
        picam2.stop_encoder()
        print(f"Recording stopped: {video_path}")
        
        mp4_path = video_path.replace('.h264', '.mp4')
        command = f"ffmpeg -y -i {video_path} -c:v copy -c:a aac {mp4_path}"
        result = os.system(command)
        if result != 0:
            print(f"FFmpeg conversion failed for {video_path}")
            return None
        print(f"Converted to MP4: {mp4_path}")
        return mp4_path
    except Exception as e:
        print(f"Recording/conversion error: {str(e)}")
        return None

def handle_motion(picam2, encoder, video_path):
    """Handle motion: record and upload."""
    mp4_path = record_and_convert(picam2, encoder, video_path)
    if mp4_path:
        upload_video(mp4_path)

def main():
    if not ensure_output_directory():
        print("Exiting due to output directory issues.")
        return

    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(
        main={"size": VIDEO_RESOLUTION, "format": "YUV420"},
        transform=ROTATION
    )
    picam2.configure(video_config)
    encoder = H264Encoder()
    picam2.start()

    prev_frame = None
    last_motion_time = 0
    is_recording = False

    try:
        while True:
            frame = picam2.capture_array()
            gray = cv2.cvtColor(frame, cv2.COLOR_YUV420p2GRAY)

            if prev_frame is None:
                prev_frame = gray
                continue

            current_time = time.time()
            if is_recording or (current_time - last_motion_time) < (VIDEO_DURATION + COOLDOWN_PERIOD):
                time.sleep(0.1)
                continue

            frame_delta = cv2.absdiff(prev_frame, gray)
            thresh = cv2.threshold(frame_delta, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            motion_detected = False
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > MIN_MOTION_AREA:
                    print(f"Motion detected with area: {area}")
                    motion_detected = True
                    break

            prev_frame = gray.copy()

            if motion_detected and not is_recording:
                is_recording = True
                last_motion_time = current_time
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_path = os.path.join(OUTPUT_DIR, f"motion_{timestamp}.h264")
                print(f"Motion triggered recording: {video_path}")

                threading.Thread(target=handle_motion, args=(picam2, encoder, video_path)).start()

                time.sleep(0.1)
                is_recording = False

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        picam2.stop()
        picam2.close()

if __name__ == "__main__":
    main()
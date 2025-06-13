from flask import Flask, Response
import cv2
from picamera2 import Picamera2
import time

app = Flask(__name__)

# Initialize the PiCamera
picam2 = Picamera2()
picam2.start()

def generate_frames():
    while True:
        # Capture frame-by-frame
        frame = picam2.capture_array()

        # Convert the frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        
        # Convert the frame to a byte array
        frame = buffer.tobytes()

        # Yield the frame to the client
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video')
def video():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return "Visit /video to view the live stream."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)

import cv2 
import mediapipe as mp 
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode
)
import os 
import urllib.request
import time



MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_PATH="face_landmarker.task"


if not os.path.exists(MODEL_PATH):
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

options=FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=RunningMode.VIDEO,
    num_faces=1,
    min_face_detection_confidence=0.5,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=False
    
)

landmarker = FaceLandmarker.create_from_options(options)
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()

    if not ret:
        break

    frame = cv2.flip(frame, 1)

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb_frame
    )

    timestamp_ms = int(time.time() * 1000)

    result = landmarker.detect_for_video(mp_image, timestamp_ms)

    cv2.imshow("Face Mesh", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break




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
#loading the model ila runiti lprojet kitloada l fichier li fih preset model li howa face_landmarker.task
    

options=FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=RunningMode.VIDEO,
    num_faces=1,
    min_face_detection_confidence=0.5,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=False
    
)
# FaceLandmarkerOptions howa constructeur li kayakhod les options dyal lmodel li ghadi nst3mlo 9aleb ela hadouk les parametres bash tfhemhoum 

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

# had lcode kaybda capture video mn webcam w kaydir loop 3la frames li kayjio mn webcam, kaydir flip lframe bach yban kima kayban lina f miroir, kayconverti lframe mn BGR l RGB 7it mediapipe kaykhdem b RGB, kaydir inference 3la lframe w kayaffichiha f wa7ed lwindow smitha "Face Mesh"
#mli katrunner lcode ou kat7el randek l window "Face Mesh" ila werekty ela ' q ' fclavier katquitter hadik lwindow 


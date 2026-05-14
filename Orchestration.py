"""
Main entry point for Sentinel.
 
This file contains NO business logic. It only:
  1. Downloads the model if needed
  2. Creates the FaceLandmarker
  3. Runs calibration
  4. Loops: read frame -> detect -> metrics -> score -> alert -> overlay
  5. Cleans up on exit
    
    """
    
    
import cv2
import time
import os
import urllib.request
 
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)
 
from Calibration import calibrate
from Metrics import FatigueMetrics
from Scorer import compute_fatigue_score, check_emergency
from Alert import AlertStateMachine
from Overlay import draw_overlay
 
 
# ============================================================
# CONFIGURATION
# ============================================================
CAMERA_INDEX = 0
WINDOW_NAME = "Sentinel"
 
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = "face_landmarker.task"
 
 
# ============================================================
# MODEL SETUP
# ============================================================
 
def download_model():
    """Download the .task model file if not present on disk."""
    if os.path.exists(MODEL_PATH):
        return
    print(f"[SENTINEL] Telechargement du modele...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print(f"[SENTINEL] Modele telecharge: {MODEL_PATH}")
 
 
def create_landmarker():
    """
    Create and return a FaceLandmarker instance.
 
    Uses VIDEO mode (synchronous, one frame at a time).
    """
    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    return FaceLandmarker.create_from_options(options)
 
 
# ============================================================
# MAIN LOOP
# ============================================================
 
def main():
    # --- Step 1: Download model ---
    download_model()
 
    # --- Step 2: Create landmarker ---
    landmarker = create_landmarker()
    print("[SENTINEL] FaceLandmarker cree")
 
    # --- Step 3: Open camera ---
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("[ERREUR] Impossible d'ouvrir la camera.")
        print("         Essaie CAMERA_INDEX = 1 ou 2")
        return
 
    print("[SENTINEL] Camera ouverte")
 
    # --- Step 4: Calibration ---
    ear_threshold = calibrate(landmarker, cap)
 
    # Recreate landmarker (calibration may have consumed timestamps)
    landmarker.close()
    landmarker = create_landmarker()
 
    # --- Step 5: Initialize modules ---
    tracker = FatigueMetrics(ear_threshold=ear_threshold)
    state_machine = AlertStateMachine()
 
    print("[SENTINEL] Systeme pret. Appuie sur Q pour quitter.")
 
    prev_time = time.time()
    fps = 0.0
 
    # --- Step 6: Main loop ---
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[ERREUR] Frame perdu.")
                break
 
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
 
            # -- Detect landmarks --
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(time.time() * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
 
            # -- Process metrics --
            snapshot = None
            score = 0.0
            emergency = False
 
            if result.face_landmarks:
                landmarks = result.face_landmarks[0]
 
                # Update metrics tracker (stateful)
                snapshot = tracker.update(landmarks, w, h)
 
                # Compute fatigue score (stateless)
                score = compute_fatigue_score(snapshot)
 
                # Check emergency conditions (stateless)
                emergency = check_emergency(snapshot)
 
            # -- Update alert state machine --
            level = state_machine.update(score, emergency)
 
            # -- Calculate FPS --
            now = time.time()
            dt = now - prev_time
            if dt > 0:
                fps = 1.0 / dt
            prev_time = now
 
            # -- Draw overlay --
            frame = draw_overlay(frame, snapshot, score, level, fps)
 
            # -- Display --
            cv2.imshow(WINDOW_NAME, frame)
 
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
 
    except KeyboardInterrupt:
        print("\n[SENTINEL] Arret par Ctrl+C")
 
    finally:
        # --- Step 7: Cleanup ---
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        state_machine.cleanup()
        print("[SENTINEL] Ferme. A bientot.")
 
 
if __name__ == "__main__":
    main()
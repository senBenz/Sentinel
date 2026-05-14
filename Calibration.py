""" 
5-second startup calibration to personalize the EAR threshold
for the current driver's eye morphology.
 
Why calibrate?
  Every person has a different eye shape. A fixed EAR threshold
  of 0.20 might work for most people, but for someone with
  naturally narrow eyes, their "open" EAR could be 0.22,
  making a 0.20 threshold trigger false alerts constantly.
 
How it works:
  1. Ask the driver to keep eyes open for 5 seconds
  2. Collect EAR values every frame
  3. Compute the average "open" EAR
  4. Set the closed threshold at 75% of the open EAR
"""


import cv2
import time
import numpy as np
import mediapipe as mp
 
from Metrics import compute_ear
 
# ============================================================
# CONSTANTS
# ============================================================
CALIBRATION_DURATION = 5.0   # seconds
EAR_CLOSED_RATIO = 0.75     # threshold = 75% of open EAR
DEFAULT_EAR_THRESHOLD = 0.20 # fallback if calibration fails
MIN_SAMPLES = 30             # minimum frames needed for valid calibration
 
 
def calibrate(landmarker, cap):
    """
    Run 5-second calibration to determine personalized EAR threshold.
 
    Args:
        landmarker: FaceLandmarker instance (Tasks API, VIDEO mode)
        cap: cv2.VideoCapture instance
 
    Returns:
        float: personalized EAR threshold for "eyes closed" detection
 
    The driver should keep their eyes open naturally during calibration.
    The function displays a countdown on screen.
    """
    print("[CALIBRATION] Gardez les yeux ouverts pendant 5 secondes...")
 
    ear_samples = []
    start_time = time.time()
 
    while True:
        elapsed = time.time() - start_time
        remaining = CALIBRATION_DURATION - elapsed
 
        if remaining <= 0:
            break
 
        ret, frame = cap.read()
        if not ret:
            continue
 
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
 
        # Process frame with MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int(time.time() * 1000)
        result = landmarker.detect_for_video(mp_image, timestamp_ms)
 
        if result.face_landmarks:
            landmarks = result.face_landmarks[0]
            left_ear, right_ear = compute_ear(landmarks, w, h)
            avg_ear = (left_ear + right_ear) / 2.0
            ear_samples.append(avg_ear)
 
        # Draw calibration overlay
        _draw_calibration_screen(frame, remaining, len(ear_samples))
        cv2.imshow("Sentinel - Calibration", frame)
 
        if cv2.waitKey(1) & 0xFF == 27:  # ESC to skip
            break
 
    # Calculate threshold
    if len(ear_samples) < MIN_SAMPLES:
        print(f"[CALIBRATION] Pas assez d'echantillons ({len(ear_samples)}), "
              f"utilisation du seuil par defaut: {DEFAULT_EAR_THRESHOLD}")
        return DEFAULT_EAR_THRESHOLD
 
    open_ear = np.mean(ear_samples)
    threshold = open_ear * EAR_CLOSED_RATIO
 
    # Safety bounds: threshold should be between 0.10 and 0.25
    threshold = max(0.10, min(0.25, threshold))
 
    print(f"[CALIBRATION] EAR moyen yeux ouverts : {open_ear:.3f}")
    print(f"[CALIBRATION] Seuil de fermeture     : {threshold:.3f}")
 
    return threshold
 
 
def _draw_calibration_screen(frame, remaining, sample_count):
    """Draw the calibration countdown overlay on the frame."""
    h, w = frame.shape[:2]
 
    # Semi-transparent dark overlay
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
 
    # Title
    cv2.putText(frame, "CALIBRATION", (w // 2 - 120, h // 2 - 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
 
    # Instruction
    cv2.putText(frame, "Gardez les yeux ouverts", (w // 2 - 160, h // 2 - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 1)
 
    # Countdown
    cv2.putText(frame, f"{remaining:.1f}s", (w // 2 - 40, h // 2 + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
 
    # Sample count
    cv2.putText(frame, f"Echantillons: {sample_count}", (w // 2 - 80, h // 2 + 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
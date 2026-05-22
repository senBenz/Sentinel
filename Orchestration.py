"""
Main entry point for Sentinel.

This file contains NO business logic. It only:
  1. Downloads the model if needed
  2. Creates the FaceLandmarker
  3. Runs calibration
  4. Loops: read frame -> detect -> metrics -> score -> alert -> overlay
  5. Cleans up on exit

Flags:
  --lstm  <path>   Use the LSTM scorer instead of the formula-based scorer.
                   <path> must point to a sentinel_lstm.pt TorchScript file.
  --record <path>  Record MetricsSnapshots to a CSV file for LSTM training.
                   Annotate the 'label' column afterwards (0.0–1.0).
"""


import argparse
import csv
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
from lstm_data import CSV_HEADER


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
    if os.path.exists(MODEL_PATH):
        return
    print(f"[SENTINEL] Telechargement du modele...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print(f"[SENTINEL] Modele telecharge: {MODEL_PATH}")


def create_landmarker():
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
# RECORDING
# ============================================================

def _open_recorder(record_path):
    """Open a CSV writer for session recording, appending to existing data."""
    file_exists = os.path.exists(record_path) and os.path.getsize(record_path) > 0
    f = open(record_path, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
    if not file_exists:
        writer.writeheader()
    return f, writer


def _record_snapshot(writer, snapshot, score):
    """Write one MetricsSnapshot row to the recording CSV.

    label is the formula-based score normalized to [0, 1].
    The LSTM trains to predict this from the 90-frame temporal window,
    learning trajectory patterns the instantaneous formula cannot see.
    """
    writer.writerow({
        "timestamp":      f"{snapshot.timestamp:.3f}",
        "ear":            f"{snapshot.ear:.4f}",
        "perclos":        f"{snapshot.perclos:.4f}",
        "blink_rate":     f"{snapshot.blink_rate:.2f}",
        "blink_duration": f"{snapshot.blink_duration:.1f}",
        "pitch":          f"{snapshot.pitch:.2f}",
        "yaw":            f"{snapshot.yaw:.2f}",
        "roll":           f"{snapshot.roll:.2f}",
        "mar":            f"{snapshot.mar:.4f}",
        "label":          f"{score / 100.0:.4f}",
    })


# ============================================================
# MAIN LOOP
# ============================================================

def main(args):
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
    tracker       = FatigueMetrics(ear_threshold=ear_threshold)
    state_machine = AlertStateMachine()

    # --- Step 5b: LSTM scorer (optional) ---
    scorer = None
    if args.lstm:
        try:
            from lstm_scorer import LSTMScorer
            scorer = LSTMScorer(args.lstm, window=90)
        except Exception as e:
            print(f"[LSTM] Impossible de charger le modele : {e}")
            print("[LSTM] Retour au scorer classique.")
            scorer = None

    score_fn = (scorer.predict if scorer is not None else compute_fatigue_score)

    # --- Step 5c: Recording (optional) ---
    rec_file, rec_writer = None, None
    if args.record:
        rec_file, rec_writer = _open_recorder(args.record)
        print(f"[RECORD] Enregistrement vers : {args.record}")

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
            snapshot  = None
            score     = 0.0
            emergency = False

            if result.face_landmarks:
                landmarks = result.face_landmarks[0]
                snapshot  = tracker.update(landmarks, w, h)
                score     = score_fn(snapshot)
                emergency = check_emergency(snapshot)

                if rec_writer is not None:
                    _record_snapshot(rec_writer, snapshot, score)

            # -- Update alert state machine --
            level = state_machine.update(score, emergency)

            # -- Calculate FPS --
            now = time.time()
            dt  = now - prev_time
            if dt > 0:
                fps = 1.0 / dt
            prev_time = now

            # -- Draw overlay --
            frame = draw_overlay(frame, snapshot, score, level, fps)

            # -- LSTM warmup indicator --
            if scorer is not None and not getattr(scorer, '_warmed', True):
                pct = int(scorer.warmup_progress * 100)
                cv2.putText(frame, f"LSTM warmup {pct}%", (12, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 220), 1)

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
        if rec_file is not None:
            rec_file.close()
            print(f"[RECORD] Session sauvegardee → {args.record}")
            print("[RECORD] Remplis la colonne 'label' (0.0–1.0) puis lance lstm_train.py")
        print("[SENTINEL] Ferme. A bientot.")


# ============================================================
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(description="Sentinel — Détection de fatigue conducteur")
    p.add_argument(
        "--lstm", metavar="MODEL_PATH", default=None,
        help="Chemin vers sentinel_lstm.pt pour activer le scorer LSTM"
    )
    p.add_argument(
        "--record", metavar="CSV_PATH", default=None,
        help="Enregistrer les métriques dans un CSV pour entraîner le LSTM"
    )
    return p.parse_args()


if __name__ == "__main__":
    main(parse_args())

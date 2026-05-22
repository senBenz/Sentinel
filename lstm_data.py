"""
Data utilities for the Sentinel LSTM scorer.

Responsibilities:
  - normalize_snapshot : MetricsSnapshot → list[float] of 8 features in [0, 1]
  - build_sequences    : CSV of recorded sessions → (X, y) numpy arrays
  - FatigueDataset     : PyTorch Dataset wrapping (X, y)
"""

import csv
import numpy as np
import torch
from torch.utils.data import Dataset


# Feature order must match MetricsSnapshot field names exactly.
FEATURE_RANGES = {
    "ear":            (0.05, 0.40),
    "perclos":        (0.00, 1.00),
    "blink_rate":     (0.0,  40.0),
    "blink_duration": (50.0, 800.0),
    "pitch":          (-45.0, 45.0),
    "yaw":            (-60.0, 60.0),
    "roll":           (-30.0, 30.0),
    "mar":            (0.0,   1.0),
}

FEATURE_KEYS = list(FEATURE_RANGES.keys())
INPUT_SIZE = len(FEATURE_KEYS)


def normalize_snapshot(snapshot):
    """
    Convert a MetricsSnapshot into a normalized feature vector.

    Args:
        snapshot: MetricsSnapshot from Metrics.py

    Returns:
        list[float]: 8 values, each clipped to [0, 1]
    """
    features = []
    for key, (lo, hi) in FEATURE_RANGES.items():
        raw = getattr(snapshot, key)
        features.append(float(max(0.0, min(1.0, (raw - lo) / (hi - lo)))))
    return features


def normalize_row(row):
    """
    Normalize a dict row (from CSV) using the same ranges.

    Args:
        row: dict with keys matching FEATURE_KEYS

    Returns:
        list[float]: 8 normalized values
    """
    features = []
    for key, (lo, hi) in FEATURE_RANGES.items():
        raw = float(row[key])
        features.append(max(0.0, min(1.0, (raw - lo) / (hi - lo))))
    return features


def build_sequences(csv_path, window=90, stride=15):
    """
    Build (X, y) training arrays from a labeled Sentinel recording CSV.

    CSV format (one row per frame):
        timestamp, ear, perclos, blink_rate, blink_duration,
        pitch, yaw, roll, mar, label

    label: float 0.0–1.0 (formula score / 100, written automatically by --record).

    Args:
        csv_path : path to recorded CSV file
        window   : sequence length in frames (default 90 ≈ 30s at 30fps)
        stride   : step between sequences (default 15 ≈ 0.5s)

    Returns:
        X : np.array (N, window, 8)
        y : np.array (N,)
    """
    rows = []
    labels = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("label", "").strip():
                continue
            rows.append(normalize_row(row))
            labels.append(float(row["label"]))

    if len(rows) < window:
        raise ValueError(
            f"Pas assez de frames annotées ({len(rows)}) pour une fenêtre de {window}."
        )

    X, y = [], []
    for start in range(0, len(rows) - window + 1, stride):
        X.append(rows[start : start + window])
        y.append(labels[start + window - 1])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


class FatigueDataset(Dataset):
    """PyTorch Dataset wrapping (X, y) sequence arrays."""

    def __init__(self, X, y):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


CSV_HEADER = ["timestamp"] + FEATURE_KEYS + ["label"]

"""
LSTMScorer — drop-in replacement for compute_fatigue_score().

During the first `window` frames (warmup), falls back to the classic
formula-based scorer so the system is functional from second 0.
Once the buffer is full, the LSTM takes over.
"""

import numpy as np
from collections import deque

from lstm_data import normalize_snapshot, FEATURE_KEYS
from Scorer import compute_fatigue_score

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


class LSTMScorer:
    """
    Wraps a TorchScript SentinelLSTM model for real-time inference.

    Usage:
        scorer = LSTMScorer("sentinel_lstm.pt")
        score  = scorer.predict(snapshot)   # float 0–100
    """

    def __init__(self, model_path, window=90, device="cpu"):
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "PyTorch n'est pas installé. "
                "Lance : pip install torch"
            )

        import torch
        self.window = window
        self.buffer = deque(maxlen=window)
        self.device = torch.device(device)
        self._warmed = False

        self._model = torch.jit.load(model_path, map_location=self.device)
        self._model.eval()
        print(f"[LSTM] Modèle chargé : {model_path}  (fenêtre={window} frames)")

    def predict(self, snapshot):
        """
        Predict fatigue score from latest snapshot.

        Args:
            snapshot: MetricsSnapshot

        Returns:
            float: fatigue score 0–100
        """
        import torch

        self.buffer.append(normalize_snapshot(snapshot))

        if len(self.buffer) < self.window:
            return compute_fatigue_score(snapshot)

        if not self._warmed:
            self._warmed = True
            print("[LSTM] Fenêtre complète — scorer LSTM actif.")

        x = np.array(self.buffer, dtype=np.float32)          # (T, 8)
        x = torch.tensor(x[np.newaxis], dtype=torch.float32) # (1, T, 8)
        x = x.to(self.device)

        with torch.no_grad():
            raw = float(self._model(x).item())

        return max(0.0, min(100.0, raw * 100.0))

    @property
    def warmup_progress(self):
        """Fraction of warmup window filled (0.0 → 1.0)."""
        return len(self.buffer) / self.window

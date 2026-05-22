import torch
import torch.nn as nn


class SentinelLSTM(nn.Module):
    """
    2-layer LSTM that maps a sequence of T MetricsSnapshots to a fatigue score (0-1).

    Input  : (batch, T, 8)  — T frames, 8 normalized features each
    Output : (batch,)       — scalar in [0, 1], multiply by 100 for score
    """

    def __init__(self, input_size=8, hidden=64, layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden, layers,
            batch_first=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


def build_model(input_size=8, hidden=64, layers=2, dropout=0.3):
    return SentinelLSTM(input_size, hidden, layers, dropout)


def export_torchscript(model, path="sentinel_lstm.pt"):
    model.eval()
    scripted = torch.jit.script(model)
    scripted.save(path)
    print(f"[LSTM] Modèle exporté : {path}")


def load_torchscript(path, device="cpu"):
    model = torch.jit.load(path, map_location=torch.device(device))
    model.eval()
    return model

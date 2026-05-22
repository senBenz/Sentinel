"""
Training script for SentinelLSTM.

Usage:
    python lstm_train.py --data session.csv
    python lstm_train.py --data session.csv --epochs 100 --window 90 --out sentinel_lstm.pt

CSV format (produced by Orchestration.py --record):
    timestamp, ear, perclos, blink_rate, blink_duration,
    pitch, yaw, roll, mar, label

label: float 0.0–1.0 (formula score / 100), written automatically by Orchestration.py --record.
"""

import argparse
import os
import numpy as np

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, random_split
except ImportError:
    raise SystemExit("PyTorch requis. Lance : pip install torch")

from lstm_model import build_model, export_torchscript
from lstm_data import build_sequences, FatigueDataset


# ============================================================
# TRAINING
# ============================================================

def train(csv_path, window=90, stride=15, hidden=64, layers=2, dropout=0.3,
          epochs=50, batch=32, lr=1e-3, weight_decay=1e-4, patience=15,
          val_split=0.2, out="sentinel_lstm.pt", device="cpu"):

    print(f"[TRAIN] Chargement des données : {csv_path}")
    X, y = build_sequences(csv_path, window=window, stride=stride)
    print(f"[TRAIN] Séquences : {len(X)}  shape=({X.shape})")

    dataset = FatigueDataset(X, y)
    n_val = int(len(dataset) * val_split)
    n_train = len(dataset) - n_val
    train_set, val_set = random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(train_set, batch_size=batch, shuffle=True)
    val_loader   = DataLoader(val_set,   batch_size=batch, shuffle=False)

    dev = torch.device(device)
    model = build_model(hidden=hidden, layers=layers, dropout=dropout).to(dev)

    # AdamW decouples weight decay from gradient update — better generalization
    # than Adam on small fatigue datasets.
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    # CosineAnnealingWarmRestarts periodically resets the LR on a cosine curve.
    # This helps escape local minima that ReduceLROnPlateau gets stuck in.
    # T_0 = first restart cycle length; T_mult=2 doubles each cycle.
    t0 = max(10, epochs // 5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=t0, T_mult=2, eta_min=1e-5
    )
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    best_state = None
    stale = 0

    for epoch in range(1, epochs + 1):
        # --- Train ---
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(dev), y_batch.to(dev)
            pred = model(X_batch)
            loss = loss_fn(pred, y_batch)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item() * len(X_batch)
        train_loss /= n_train

        scheduler.step()

        # --- Validate ---
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(dev), y_batch.to(dev)
                pred = model(X_batch)
                val_loss += loss_fn(pred, y_batch).item() * len(X_batch)
        val_loss /= max(n_val, 1)

        if epoch % 10 == 0 or epoch == 1:
            lr_now = optimizer.param_groups[0]["lr"]
            print(f"  Epoch {epoch:3d}/{epochs}  "
                  f"train={train_loss:.4f}  val={val_loss:.4f}  lr={lr_now:.2e}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                print(f"[TRAIN] Arrêt précoce — pas d'amélioration depuis {patience} epochs.")
                break

    # --- Export best model ---
    model.load_state_dict(best_state)
    export_torchscript(model.cpu(), path=out)

    val_mae = _compute_mae(model.cpu(), val_set, batch)
    print(f"[TRAIN] Meilleur val_loss={best_val:.4f}  MAE score={val_mae*100:.1f} pts")
    print(f"[TRAIN] Modèle sauvegardé → {out}")


def _compute_mae(model, dataset, batch):
    loader = DataLoader(dataset, batch_size=batch)
    model.eval()
    errors = []
    with torch.no_grad():
        for X_batch, y_batch in loader:
            pred = model(X_batch)
            errors.extend((pred - y_batch).abs().tolist())
    return float(np.mean(errors))


# ============================================================
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(description="Entraîner SentinelLSTM")
    p.add_argument("--data",    required=True,        help="CSV enregistré par Orchestration.py --record")
    p.add_argument("--out",     default="sentinel_lstm.pt", help="Fichier TorchScript de sortie")
    p.add_argument("--window",  type=int,   default=90,   help="Longueur de séquence en frames (défaut: 90)")
    p.add_argument("--stride",  type=int,   default=15,   help="Pas entre séquences (défaut: 15)")
    p.add_argument("--hidden",  type=int,   default=64,   help="Taille hidden LSTM (défaut: 64)")
    p.add_argument("--layers",  type=int,   default=2,    help="Nombre de couches LSTM (défaut: 2)")
    p.add_argument("--dropout", type=float, default=0.3,  help="Dropout (défaut: 0.3)")
    p.add_argument("--epochs",  type=int,   default=50,   help="Epochs (défaut: 50)")
    p.add_argument("--batch",   type=int,   default=32,   help="Batch size (défaut: 32)")
    p.add_argument("--lr",           type=float, default=1e-3,  help="Learning rate initial (défaut: 0.001)")
    p.add_argument("--weight-decay", type=float, default=1e-4,  help="Régularisation AdamW (défaut: 0.0001)")
    p.add_argument("--patience",     type=int,   default=15,    help="Early stopping patience en epochs (défaut: 15)")
    p.add_argument("--val",          type=float, default=0.2,   help="Fraction validation (défaut: 0.2)")
    p.add_argument("--device",       default="cpu",             help="cpu / cuda / mps (défaut: cpu)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not os.path.exists(args.data):
        raise SystemExit(f"[ERREUR] Fichier introuvable : {args.data}")

    train(
        csv_path=args.data,
        window=args.window,
        stride=args.stride,
        hidden=args.hidden,
        layers=args.layers,
        dropout=args.dropout,
        epochs=args.epochs,
        batch=args.batch,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        val_split=args.val,
        out=args.out,
        device=args.device,
    )

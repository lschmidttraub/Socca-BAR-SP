"""Script 1 — Model optimisation for the pitch-value function V(p, t).

Pipeline
--------
1. Iterate over SkillCorner match zips. Sample frames at intervals of at
   least ΔT seconds (paper: 3 s) such that an attacking team has the ball.
2. For each sampled frame compute, for every defending player d, the
   spatial influence I_d evaluated on a uniform 21 × 15 grid. The training
   target at grid cell (i, j) is V̂(p_{i,j}, t) = clip(Σ_d I_d, 0, 1)
   (paper Eq. 4).
3. Feed (p_b, p_{i,j}, V̂) triples into a feed-forward MLP V(p_b, p; Θ)
   trained with Adam on the MSE loss (paper Eq. 5).

All coordinates are normalised to the [0, 1]^2 unit square before entering
the network. Inverse normalisation is the responsibility of the caller.

Output
------
    out/value_function.pt        — torch state_dict
    out/value_function_loss.png  — training/validation loss curve
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn, optim
from torch.utils.data import DataLoader, TensorDataset

from soccer_space.core import (
    PITCH_LEN, PITCH_WID,
    defensive_value_target, influence_grid, make_grid, normalise_xy,
)
from soccer_space.data import (
    compute_velocity_buffer, iter_frames_with_meta,
)
from soccer_space.model import ValueMLP


# UTF-8 console.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# --- Target generation (single-pass streaming) ------------------------------
def build_samples_from_match(zip_path: Path,
                             grid_xy: np.ndarray,
                             min_dt_seconds: float,
                             max_per_match: int | None,
                             vel_half_window: int = 3
                             ) -> tuple[np.ndarray, np.ndarray]:
    """For one match, compute (X, y) training pairs in a single JSONL pass.

    Algorithm
    ---------
    Maintain a rolling buffer of recent frame positions plus a list of
    pending target frames. As each new frame F arrives:
      1. Append its positions to the buffer.
      2. If F satisfies the possession + spacing constraints, register a
         new pending target carrying its (defenders, ball, team_of) data.
      3. Finalise any pending target T for which the forward velocity
         window T + vel_half_window is now buffered: compute centred-FD
         velocities, the defenders' influence grid, the clipped target
         surface, and append a flattened (X, y) batch.
      4. Prune buffer entries older than the oldest still-pending target
         minus vel_half_window.

    Returns
    -------
    X : (N, 4) — normalised (p_bx, p_by, p_x, p_y).
    y : (N, 1) — clipped sum of defenders' influence at p.
    """
    stride = int(round(min_dt_seconds * 10))
    grid_norm = normalise_xy(grid_xy).reshape(-1, 2)                 # (G, 2)

    positions_buffer: dict[int, dict[int, np.ndarray]] = {}
    pending: list[dict] = []
    last_picked = -10**9
    n_emitted = 0

    Xs: list[np.ndarray] = []
    Ys: list[np.ndarray] = []

    def _emit(p: dict) -> None:
        nonlocal n_emitted
        velmap = compute_velocity_buffer(positions_buffer, p["frame"],
                                         vel_half_window)
        team_of = p["team_of"]
        d_pos, d_vel = [], []
        for pid, xy in zip(p["player_ids"], p["player_xy"]):
            if team_of.get(int(pid), -1) != p["defending"]:
                continue
            d_pos.append(xy)
            d_vel.append(velmap.get(int(pid), np.zeros(2)))
        if len(d_pos) < 4:
            return
        d_pos = np.asarray(d_pos); d_vel = np.asarray(d_vel)
        I_def = influence_grid(grid_xy, d_pos, d_vel, p["ball"])    # (P,H,W)
        target = defensive_value_target(I_def).reshape(-1)          # (G,)
        ball_norm = normalise_xy(p["ball"][None, :])[0]
        ball_tile = np.broadcast_to(ball_norm, (grid_norm.shape[0], 2))
        X = np.concatenate([ball_tile, grid_norm], axis=1).astype(np.float32)
        y = target.astype(np.float32)[:, None]
        Xs.append(X); Ys.append(y)
        n_emitted += 1

    for f, meta in iter_frames_with_meta(zip_path):
        positions_buffer[f.frame] = {int(pid): xy
                                     for pid, xy in zip(f.player_ids,
                                                        f.player_xy)}

        # (2) Register a new pending target if eligible.
        cap_ok = (max_per_match is None
                  or n_emitted + len(pending) < max_per_match)
        if (cap_ok and f.possession_team is not None
                and f.frame - last_picked >= stride):
            defending = (meta.away_team_id
                         if f.possession_team == meta.home_team_id
                         else meta.home_team_id)
            pending.append({
                "frame": f.frame, "defending": defending,
                "ball": f.ball_xy.copy(),
                "player_ids": f.player_ids.copy(),
                "player_xy":  f.player_xy.copy(),
                "team_of":    meta.player_team,
            })
            last_picked = f.frame

        # (3) Finalise pending targets whose forward window is buffered.
        ready_cutoff = f.frame - vel_half_window
        still_pending: list[dict] = []
        for p in pending:
            if p["frame"] <= ready_cutoff:
                _emit(p)
            else:
                still_pending.append(p)
        pending = still_pending

        # (4) Prune buffer.
        oldest_needed = (min(p["frame"] for p in pending)
                         if pending else f.frame) - vel_half_window
        for k in [k for k in positions_buffer if k < oldest_needed]:
            del positions_buffer[k]

    # End-of-stream flush.
    for p in pending:
        _emit(p)

    if not Xs:
        return np.empty((0, 4), dtype=np.float32), \
               np.empty((0, 1), dtype=np.float32)
    return np.concatenate(Xs, axis=0), np.concatenate(Ys, axis=0)


# --- Training ---------------------------------------------------------------
def train(model: ValueMLP, X: np.ndarray, y: np.ndarray,
          epochs: int = 25, batch_size: int = 4096,
          lr: float = 1e-3, val_frac: float = 0.1,
          device: str = "cpu", seed: int = 0
          ) -> tuple[list[float], list[float]]:
    torch.manual_seed(seed); np.random.seed(seed)
    perm = np.random.permutation(len(X))
    cut = int(len(X) * (1 - val_frac))
    tr_idx, va_idx = perm[:cut], perm[cut:]
    Xt = torch.from_numpy(X[tr_idx]); yt = torch.from_numpy(y[tr_idx])
    Xv = torch.from_numpy(X[va_idx]); yv = torch.from_numpy(y[va_idx])

    train_loader = DataLoader(TensorDataset(Xt, yt),
                              batch_size=batch_size, shuffle=True)
    val_loader   = DataLoader(TensorDataset(Xv, yv),
                              batch_size=batch_size, shuffle=False)
    crit = nn.MSELoss()
    opt = optim.Adam(model.parameters(), lr=lr)
    model.to(device)

    tr_curve, va_curve = [], []
    for ep in range(1, epochs + 1):
        model.train()
        tot = 0.0; n = 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = crit(pred, yb)
            loss.backward(); opt.step()
            tot += loss.item() * len(xb); n += len(xb)
        tr_loss = tot / max(n, 1)

        model.eval()
        with torch.no_grad():
            tot = 0.0; n = 0
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                tot += crit(model(xb), yb).item() * len(xb); n += len(xb)
            va_loss = tot / max(n, 1)
        tr_curve.append(tr_loss); va_curve.append(va_loss)
        print(f"  epoch {ep:3d}/{epochs}  train MSE {tr_loss:.5f}   "
              f"val MSE {va_loss:.5f}")
    return tr_curve, va_curve


# --- CLI --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="sample_games/skillcorner",
                    help="Directory of SkillCorner match zips.")
    ap.add_argument("--out-dir",  default="out")
    ap.add_argument("--matches",  type=int, default=None,
                    help="Limit number of match zips processed.")
    ap.add_argument("--max-per-match", type=int, default=400)
    ap.add_argument("--min-dt", type=float, default=3.0)
    ap.add_argument("--grid-nx", type=int, default=21)
    ap.add_argument("--grid-ny", type=int, default=15)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch", type=int, default=4096)
    ap.add_argument("--val-split", type=float, default=0.1,
                    help="Fraction of frames held out for validation.")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    grid_xy = make_grid(args.grid_nx, args.grid_ny, PITCH_LEN, PITCH_WID)

    zips = sorted(Path(args.data_dir).glob("*.zip"))
    if args.matches:
        zips = zips[:args.matches]
    if not zips:
        raise SystemExit(f"No match zips found in {args.data_dir}")
    print(f"Found {len(zips)} match zip(s) in {args.data_dir}")

    Xs, Ys, manifest = [], [], []
    t0 = time.time()
    for z in zips:
        print(f"\n[match] {z.name}")
        Xm, ym = build_samples_from_match(
            z, grid_xy, args.min_dt, args.max_per_match)
        print(f"  -> {len(Xm):>8d} (p_b, p) samples")
        manifest.append({"match": z.name, "samples": int(len(Xm))})
        if len(Xm):
            Xs.append(Xm); Ys.append(ym)

    if not Xs:
        raise SystemExit("No samples collected; check tracking data.")
    X = np.concatenate(Xs, axis=0); y = np.concatenate(Ys, axis=0)
    print(f"\nTotal samples: {len(X):,}   collected in {time.time()-t0:.1f}s")

    # Hold-out spatial coordinates for validate.py.
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(X))
    cut = int(len(X) * (1 - args.val_split))
    train_idx, hold_idx = perm[:cut], perm[cut:]
    np.savez(out_dir / "value_function_holdout.npz",
             X=X[hold_idx].astype(np.float32),
             y=y[hold_idx].astype(np.float32))
    print(f"Saved {len(hold_idx):,} holdout samples for validation.")

    model = ValueMLP(hidden_dim=args.hidden)
    tr_curve, va_curve = train(
        model, X[train_idx], y[train_idx],
        epochs=args.epochs, batch_size=args.batch, lr=args.lr,
        val_frac=0.1, device=args.device,
    )

    ckpt = {
        "state_dict": model.state_dict(),
        "hidden_dim": args.hidden,
        "grid_nx": args.grid_nx, "grid_ny": args.grid_ny,
    }
    torch.save(ckpt, out_dir / "value_function.pt")
    print(f"Saved model → {out_dir / 'value_function.pt'}")

    # Loss curve.
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(tr_curve, label="train MSE", color="#A50044")
        ax.plot(va_curve, label="val MSE",   color="#0B4D98")
        ax.set_xlabel("epoch"); ax.set_ylabel("MSE")
        ax.set_title("V(p, t) — training curve")
        ax.grid(linestyle=":", alpha=0.4); ax.legend()
        plt.tight_layout(); fig.savefig(out_dir / "value_function_loss.png",
                                        dpi=150)
        plt.close(fig)
        print(f"Saved {out_dir / 'value_function_loss.png'}")
    except Exception as e:
        print(f"  (skipped loss plot: {e})")

    with open(out_dir / "training_manifest.json", "w", encoding="utf-8") as fp:
        json.dump({"matches": manifest,
                   "total_samples": int(len(X)),
                   "epochs": args.epochs,
                   "hidden_dim": args.hidden,
                   "grid": [args.grid_ny, args.grid_nx]}, fp, indent=2)


if __name__ == "__main__":
    main()

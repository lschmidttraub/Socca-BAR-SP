"""Script 3 — Spatial integration, SOG, and visualisation at time t.

Given a SkillCorner match zip and a target frame, this script:

1. Builds the discretised pitch grid (default 105 × 68 cells at 1 m
   resolution).
2. Computes per-player influence I_i(p, t) and the team pitch-control
   matrix
        PC(p, t) = σ(Σ_A I_k − Σ_B I_j)
   using fully vectorised numpy operations.
3. Evaluates the pre-trained MLP V(p_b, p; Θ) on the same grid to produce
   the spatial-value matrix V(p, t).
4. Forms the Hadamard product
        Q(p, t) = PC(p, t) ⊙ V(p, t).
5. For a temporal window of w frames, computes the discrete derivative
        G_i(t) = (1/w) Σ_{k=1..w} Q_i(t+k) − Q_i(t),
   where Q_i(t) := ∫_p I_i(p, t) V(p, t) dp ≈ Σ_p I_i(p, t) V(p, t) ΔA,
   and applies the threshold ε (paper Eq. 8) to obtain SOG_i and SOL_i.
6. Renders contourf(Q) + quiver(s_i) + scatter(μ_i) to a high-resolution
   PNG (paper Figures 3, 6).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.patches import Rectangle

from soccer_space.core import (
    PITCH_LEN, PITCH_WID,
    influence_grid, make_grid, means, normalise_xy,
    pitch_control_from_influence,
)
from soccer_space.data import (
    compute_velocity_buffer, iter_frames_with_meta, load_match_meta,
)
from soccer_space.model import ValueMLP, predict_grid


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# --- Locate target frame ----------------------------------------------------
def resolve_target_frame(zip_path: Path, time_sec: float | None,
                         frame: int | None, period: int) -> int:
    """Translate (period, time_sec) → SkillCorner frame index."""
    if frame is not None:
        return int(frame)
    meta = load_match_meta(zip_path)
    start = meta.period_starts.get(period)
    if start is None:
        raise SystemExit(f"Period {period} not found in match metadata.")
    return start + int(round(time_sec * 10))


# --- Buffer positions across a [t-half, t+w+half] window --------------------
def collect_buffer(zip_path: Path, target_frames: set[int],
                   half_window: int = 3
                   ) -> tuple[dict[int, dict[int, np.ndarray]],
                              dict[int, dict],
                              "MatchMeta"]:
    needed = set()
    for f in target_frames:
        for k in range(-half_window, half_window + 1):
            needed.add(f + k)
    positions: dict[int, dict[int, np.ndarray]] = {}
    frame_meta: dict[int, dict] = {}
    last_meta = None
    for f, meta in iter_frames_with_meta(zip_path):
        last_meta = meta
        if f.frame in needed:
            positions[f.frame] = {int(pid): xy
                                  for pid, xy in zip(f.player_ids, f.player_xy)}
        if f.frame in target_frames:
            frame_meta[f.frame] = {
                "ball_xy": f.ball_xy.copy(),
                "possession_team": f.possession_team,
                "player_ids": f.player_ids.copy(),
                "player_xy":  f.player_xy.copy(),
            }
    return positions, frame_meta, last_meta


# --- Q computation for a single frame ---------------------------------------
def compute_frame_quantities(meta, frame_info: dict, positions: dict,
                             grid_xy: np.ndarray,
                             model: ValueMLP,
                             half_window: int = 3,
                             device: str = "cpu"
                             ) -> dict:
    """Return a dict with player split, I, PC, V, Q, μ, s arrays for the
    requested frame."""
    pids = frame_info["player_ids"]
    pxy  = frame_info["player_xy"]
    ball = frame_info["ball_xy"]

    velmap = compute_velocity_buffer(positions, frame_info["_frame"],
                                     half_window)
    velocities = np.stack([velmap.get(int(pid), np.zeros(2))
                           for pid in pids], axis=0)

    home_mask = np.array([meta.player_team.get(int(pid), -1)
                          == meta.home_team_id for pid in pids])
    away_mask = np.array([meta.player_team.get(int(pid), -1)
                          == meta.away_team_id for pid in pids])

    I_all = influence_grid(grid_xy, pxy, velocities, ball)              # (P,H,W)
    I_home = I_all[home_mask]; I_away = I_all[away_mask]

    # Pitch control with attackers = team in possession (paper Eq. 2).
    poss = frame_info["possession_team"]
    if poss == meta.home_team_id:
        PC = pitch_control_from_influence(I_home, I_away)
    elif poss == meta.away_team_id:
        PC = pitch_control_from_influence(I_away, I_home)
    else:
        # Fallback when possession is undefined: home as attackers.
        PC = pitch_control_from_influence(I_home, I_away)

    # MLP-based value V.
    grid_norm = normalise_xy(grid_xy)
    ball_norm = normalise_xy(ball[None, :])[0]
    V = predict_grid(model, tuple(ball_norm), grid_norm, device=device)  # (H,W)

    Q = PC * V                                                          # (H,W)
    mu = means(pxy, velocities)                                         # (P,2)

    return {
        "I_all": I_all, "I_home": I_home, "I_away": I_away,
        "home_mask": home_mask, "away_mask": away_mask,
        "PC": PC, "V": V, "Q": Q, "mu": mu, "vel": velocities,
        "pos": pxy, "pids": pids, "ball": ball, "poss": poss,
    }


def player_quality_scalars(I_all: np.ndarray, V: np.ndarray,
                           cell_area: float) -> np.ndarray:
    """Q_i(t) — per-player scalar quality of owned space.

    Defined as the V-weighted mean over the pitch, with weights given by the
    player's influence I_i (paper section 5):

            Q_i(t) = (Σ_p I_i(p, t) V(p, t)) / (Σ_p I_i(p, t))

    The numerator is the area integral I_i · V; division by Σ I_i removes
    the dependence on grid resolution and yields a value in [0, 1] that is
    directly comparable across frames and players. ``cell_area`` is kept in
    the signature for callers that need the unnormalised integral; it is not
    used here because it cancels in the ratio.
    """
    num = (I_all * V[None, :, :]).sum(axis=(1, 2))
    den = np.maximum(I_all.sum(axis=(1, 2)), 1e-12)
    return num / den


# --- SOG --------------------------------------------------------------------
def compute_sog(zip_path: Path, t_frame: int, w_frames: int,
                grid_xy: np.ndarray, model: ValueMLP,
                epsilon: float, half_window: int,
                device: str = "cpu") -> dict:
    """Returns a dict per player with G_i, SOG_i, SOL_i, plus the frame-t
    intermediate matrices used by the visualisation."""
    cell_area = (PITCH_LEN / grid_xy.shape[1]) \
              * (PITCH_WID / grid_xy.shape[0])

    target_frames = {t_frame} | {t_frame + k for k in range(1, w_frames + 1)}
    positions, frame_meta, meta = collect_buffer(zip_path, target_frames,
                                                 half_window)
    if t_frame not in frame_meta:
        raise SystemExit(f"Frame {t_frame} not present in tracking.")

    # Compute Q_i at t.
    frame_meta[t_frame]["_frame"] = t_frame
    quant0 = compute_frame_quantities(meta, frame_meta[t_frame], positions,
                                      grid_xy, model, half_window, device)
    Q_i_t = player_quality_scalars(quant0["I_all"], quant0["V"], cell_area)
    pids_t = quant0["pids"]

    # Accumulate Q_i(t+k) for the same player ids (matched by pid).
    accum = np.zeros_like(Q_i_t); valid = 0
    for k in range(1, w_frames + 1):
        fk = t_frame + k
        info_k = frame_meta.get(fk)
        if info_k is None:
            continue
        info_k["_frame"] = fk
        qk = compute_frame_quantities(meta, info_k, positions, grid_xy,
                                      model, half_window, device)
        q_vec = np.zeros_like(Q_i_t)
        ids_k = qk["pids"]; idmap = {int(p): i for i, p in enumerate(ids_k)}
        q_k_player = player_quality_scalars(qk["I_all"], qk["V"], cell_area)
        for j, pid in enumerate(pids_t):
            ix = idmap.get(int(pid))
            if ix is not None:
                q_vec[j] = q_k_player[ix]
        accum += q_vec; valid += 1
    if valid == 0:
        G = np.zeros_like(Q_i_t)
    else:
        G = accum / valid - Q_i_t

    SOG = np.where(G >=  epsilon,  G, 0.0)
    SOL = np.where(G <= -epsilon, -G, 0.0)
    return {
        "meta": meta,
        "frame0": quant0,
        "Q_i_t": Q_i_t,
        "G": G, "SOG": SOG, "SOL": SOL,
        "pids": pids_t, "cell_area": cell_area,
    }


# --- Visualisation ----------------------------------------------------------
def render_figure(quant0: dict, meta, out_path: Path, title: str,
                  grid_xy: np.ndarray, ball_xy: np.ndarray):
    """Render Q(p, t) contourf + per-player quiver and μ scatter."""
    Q = quant0["Q"]
    xs = grid_xy[0, :, 0]; ys = grid_xy[:, 0, 1]

    fig, ax = plt.subplots(figsize=(12, 7.2))
    # Pitch outline.
    ax.add_patch(Rectangle((-PITCH_LEN/2, -PITCH_WID/2),
                           PITCH_LEN, PITCH_WID,
                           fill=False, edgecolor="black", linewidth=1.0,
                           zorder=1))
    # Q field.
    cs = ax.contourf(xs, ys, Q, levels=20, cmap="viridis", zorder=2)
    plt.colorbar(cs, ax=ax, fraction=0.04, pad=0.02,
                 label="Q(p, t) = PC · V")

    home_mask = quant0["home_mask"]; away_mask = quant0["away_mask"]
    mu  = quant0["mu"];  vel  = quant0["vel"];  pos = quant0["pos"]

    # μ_i scatter for both teams.
    ax.scatter(mu[home_mask, 0], mu[home_mask, 1],
               s=70, c="#A50044", edgecolors="white", linewidth=1.3,
               zorder=4, label=f"{meta.home_team_name} (μ_i)")
    ax.scatter(mu[away_mask, 0], mu[away_mask, 1],
               s=70, c="#0B4D98", edgecolors="white", linewidth=1.3,
               zorder=4, label=f"{meta.away_team_name} (μ_i)")
    # Velocity quivers anchored at p_i.
    ax.quiver(pos[:, 0], pos[:, 1], vel[:, 0], vel[:, 1],
              angles="xy", scale_units="xy", scale=1.0,
              color="white", width=0.0025, headwidth=4, headlength=5,
              zorder=5, alpha=0.95)
    # Ball.
    ax.scatter(ball_xy[0], ball_xy[1], s=120, c="white",
               edgecolors="black", linewidth=1.4, zorder=6, label="ball")

    ax.set_xlim(-PITCH_LEN/2 - 2, PITCH_LEN/2 + 2)
    ax.set_ylim(-PITCH_WID/2 - 2, PITCH_WID/2 + 2)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    ax.set_title(title)
    ax.legend(loc="upper right", framealpha=0.85, fontsize=9)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def render_panels(quant0: dict, meta, out_path: Path, grid_xy: np.ndarray):
    """Three-panel layout: PC, V, Q (paper Figure 6 style)."""
    xs = grid_xy[0, :, 0]; ys = grid_xy[:, 0, 1]
    PC = quant0["PC"]; V = quant0["V"]; Q = quant0["Q"]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.6))
    for ax, M, ttl in zip(axes, [PC, V, Q],
                          ["PC(p, t)", "V(p, t)", "Q(p, t) = PC · V"]):
        ax.add_patch(Rectangle((-PITCH_LEN/2, -PITCH_WID/2),
                               PITCH_LEN, PITCH_WID,
                               fill=False, edgecolor="black", linewidth=1.0))
        cs = ax.contourf(xs, ys, M, levels=20, cmap="viridis")
        plt.colorbar(cs, ax=ax, fraction=0.04, pad=0.02)
        ax.set_aspect("equal")
        ax.set_xlim(-PITCH_LEN/2 - 2, PITCH_LEN/2 + 2)
        ax.set_ylim(-PITCH_WID/2 - 2, PITCH_WID/2 + 2)
        ax.set_title(ttl); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


# --- CLI --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match",   required=True,
                    help="Path to a SkillCorner match zip.")
    ap.add_argument("--model",   default="out/value_function.pt")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--time-sec", type=float, default=None,
                    help="Seconds since the start of the chosen period.")
    ap.add_argument("--period",  type=int, default=1)
    ap.add_argument("--frame",   type=int, default=None,
                    help="Absolute frame index (overrides --time-sec).")
    ap.add_argument("--window",  type=int, default=30,
                    help="SOG window w in frames (default 30 ⇒ 3.0 s at 10 Hz)")
    ap.add_argument("--epsilon", type=float, default=0.02,
                    help="SOG threshold ε (paper section 5.1).")
    ap.add_argument("--grid-nx", type=int, default=105,
                    help="Grid columns (default 105 ⇒ 1 m resolution).")
    ap.add_argument("--grid-ny", type=int, default=68)
    ap.add_argument("--vel-half-window", type=int, default=3,
                    help="Frames each side for centred velocity FD.")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    zip_path = Path(args.match); out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid_xy = make_grid(args.grid_nx, args.grid_ny, PITCH_LEN, PITCH_WID)
    target = resolve_target_frame(zip_path, args.time_sec, args.frame,
                                  args.period)
    print(f"Match : {zip_path.name}")
    print(f"Frame : {target}  (period {args.period}, "
          f"t ≈ {args.time_sec if args.time_sec is not None else '—'} s)")
    print(f"Grid  : {args.grid_ny} × {args.grid_nx}  "
          f"({PITCH_WID/args.grid_ny:.2f} m × {PITCH_LEN/args.grid_nx:.2f} m)")

    # Load model.
    ckpt = torch.load(args.model, map_location="cpu", weights_only=False)
    model = ValueMLP(hidden_dim=ckpt.get("hidden_dim", 64))
    model.load_state_dict(ckpt["state_dict"])

    res = compute_sog(zip_path, target, args.window, grid_xy, model,
                      args.epsilon, args.vel_half_window, args.device)
    meta = res["meta"]; quant0 = res["frame0"]
    pids = res["pids"]; G = res["G"]; SOG = res["SOG"]; SOL = res["SOL"]

    print("\nSpace Occupation Gain (per player, ε = "
          f"{args.epsilon}, w = {args.window} frames)")
    print(f"  {'player_id':>10}  {'team':<8}  {'G_i':>8}  {'SOG_i':>8}  {'SOL_i':>8}")
    rows = []
    for j, pid in enumerate(pids):
        team_id = meta.player_team.get(int(pid), -1)
        team = ("home" if team_id == meta.home_team_id else
                "away" if team_id == meta.away_team_id else "?")
        print(f"  {int(pid):>10d}  {team:<8}  {G[j]:>8.4f}  "
              f"{SOG[j]:>8.4f}  {SOL[j]:>8.4f}")
        rows.append({"player_id": int(pid), "team": team,
                     "G": float(G[j]), "SOG": float(SOG[j]),
                     "SOL": float(SOL[j])})
    with open(out_dir / "sog_report.json", "w", encoding="utf-8") as fp:
        json.dump({"match": zip_path.name, "frame": target,
                   "window": args.window, "epsilon": args.epsilon,
                   "players": rows}, fp, indent=2)
    print(f"\nSaved {out_dir / 'sog_report.json'}")

    title = (f"Q(p, t) — {meta.home_team_name} vs {meta.away_team_name}  "
             f"frame {target}")
    png_path  = out_dir / f"spatial_map_frame{target}.png"
    render_figure(quant0, meta, png_path, title,
                  grid_xy, quant0["ball"])
    print(f"Saved {png_path}")

    panels_path = out_dir / f"spatial_panels_frame{target}.png"
    render_panels(quant0, meta, panels_path, grid_xy)
    print(f"Saved {panels_path}")


if __name__ == "__main__":
    main()

"""Script 2 — Validation of the parametric framework.

Two empirical evaluations on held-out data:

(a) Pitch-control Brier score
    For each pass event in the validation set, evaluate the logistic surface
        PC(p_dest, t_arrive) = σ(Σ_A I_k − Σ_B I_j)
    where A is the passer's team and B is the opposing team. The binary
    outcome y ∈ {0, 1} is 1 if possession was retained by team A (the pass
    was completed), 0 otherwise. The Brier score is
        Brier = (1/N) Σ (PC_n − y_n)^2.
    A score of 0.25 corresponds to the uninformed predictor PC ≡ 0.5.

(b) Value-function mean-squared error
    Evaluate the trained MLP on the held-out (p_b, p, V̂) triples written by
    train_value_function.py and report 1/N Σ (ŷ_n − V̂_n)^2.

Inputs
------
    --data-dir       directory of SkillCorner zips
    --events-dir     directory of StatsBomb event JSON files
    --matches-csv    matches.csv (columns: statsbomb, skillcorner, …)
    --model          path to value_function.pt
    --holdout        path to value_function_holdout.npz
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from soccer_space.core import (
    PITCH_LEN, PITCH_WID,
    influence_points, _sigmoid,
)
from soccer_space.data import (
    compute_velocity_buffer, iter_frames_with_meta,
    load_match_meta, possession_team_id,
)
from soccer_space.model import ValueMLP


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# --- StatsBomb pass extraction ----------------------------------------------
def _parse_ts(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _sb_xy_to_meters(x_yd: float, y_yd: float,
                     attacking_left_to_right: bool = True) -> np.ndarray:
    """Convert StatsBomb pitch coords (120 yd × 80 yd, origin bottom-left,
    attacking team toward x=120) to centred meters (105 m × 68 m).

    Note: SkillCorner's coordinate frame is independent of the attacking
    direction; for Brier evaluation only relative inter-team contrast
    matters, so we keep the StatsBomb orientation throughout — both passer
    and defenders are expressed in the same frame.
    """
    x_m = (x_yd / 120.0) * PITCH_LEN - PITCH_LEN / 2.0
    y_m = (y_yd /  80.0) * PITCH_WID  - PITCH_WID  / 2.0
    return np.array([x_m, y_m], dtype=np.float64)


def extract_pass_records(events_path: Path) -> list[dict]:
    """Extract (period, ts, team_id, end_xy_m, completed) from a SB events
    JSON. Only events of type Pass with end_location and outcome semantics
    are returned. Penalties / corners / throw-ins are kept (the model is
    agnostic) but kick-offs are dropped to avoid stoppage frames."""
    with open(events_path, "r", encoding="utf-8") as fp:
        events = json.load(fp)
    out = []
    for e in events:
        if (e.get("type") or {}).get("name") != "Pass":
            continue
        p = e.get("pass") or {}
        if (p.get("type") or {}).get("name") == "Kick Off":
            continue
        end = p.get("end_location")
        if not end or len(end) < 2:
            continue
        outcome = (p.get("outcome") or {}).get("name")
        completed = outcome is None        # SB convention: no outcome ⇒ ok
        team = (e.get("team") or {}).get("name")
        out.append({
            "period": e["period"],
            "ts_sec": _parse_ts(e["timestamp"]),
            "team_name": team,
            "end_xy_m": _sb_xy_to_meters(float(end[0]), float(end[1])),
            "completed": bool(completed),
        })
    return out


# --- Frame alignment --------------------------------------------------------
def passes_to_target_frames(passes: list[dict],
                            period_starts: dict[int, int],
                            arrive_extra_frames: int = 5,
                            ) -> dict[int, dict]:
    """Map each pass to a target SkillCorner frame index.

    target_frame = period_start_frame[period] + round(ts_sec * 10)
                   + arrive_extra_frames
    The constant `arrive_extra_frames` approximates ball flight time
    (default 0.5 s); the paper uses pass arrival time but SB does not store
    it. Keyed by frame, value carries the pass record.
    """
    out = {}
    for p in passes:
        period = p["period"]
        if period not in period_starts:
            continue
        f = period_starts[period] + int(round(p["ts_sec"] * 10)) \
                                  + arrive_extra_frames
        out[f] = p
    return out


# --- Brier evaluation -------------------------------------------------------
def brier_for_match(zip_path: Path,
                    events_path: Path,
                    vel_half_window: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Return (PC_at_destination, completion_outcome) for every aligned pass."""
    meta = load_match_meta(zip_path)
    name_to_team_id = {meta.home_team_name: meta.home_team_id,
                       meta.away_team_name: meta.away_team_id}
    passes = extract_pass_records(events_path)

    # Fuzzy match SB team-name → SkillCorner team_id.
    def lookup_team(name: str | None) -> int | None:
        if not name:
            return None
        nl = name.lower()
        for k, v in name_to_team_id.items():
            kl = k.lower()
            if kl == nl or nl in kl or kl in nl:
                return v
        return None

    target_passes: dict[int, dict] = {}
    for p in passes:
        tid = lookup_team(p["team_name"])
        if tid is None:
            continue
        period = p["period"]
        if period not in meta.period_starts:
            continue
        f = meta.period_starts[period] + int(round(p["ts_sec"] * 10)) + 5
        target_passes[f] = {**p, "team_id": tid}

    if not target_passes:
        return np.empty(0), np.empty(0)

    target_frames = set(target_passes.keys())

    # Buffer positions for finite-difference velocities.
    needed = set()
    for f in target_frames:
        for k in range(-vel_half_window, vel_half_window + 1):
            needed.add(f + k)
    buf: dict[int, dict[int, np.ndarray]] = {}

    pcs: list[float] = []
    ys:  list[int] = []
    for f, _m in iter_frames_with_meta(zip_path):
        if f.frame in needed:
            buf[f.frame] = {int(pid): xy
                            for pid, xy in zip(f.player_ids, f.player_xy)}
        if f.frame in target_passes:
            p = target_passes[f.frame]
            atk_team = p["team_id"]
            def_team = (meta.away_team_id if atk_team == meta.home_team_id
                        else meta.home_team_id)
            velmap = compute_velocity_buffer(buf, f.frame, vel_half_window)
            team_of = meta.player_team
            a_pos, a_vel, d_pos, d_vel = [], [], [], []
            for pid, xy in zip(f.player_ids, f.player_xy):
                pid_i = int(pid)
                t = team_of.get(pid_i, -1)
                v = velmap.get(pid_i, np.zeros(2))
                if t == atk_team:
                    a_pos.append(xy); a_vel.append(v)
                elif t == def_team:
                    d_pos.append(xy); d_vel.append(v)
            if len(a_pos) < 4 or len(d_pos) < 4:
                continue
            a_pos = np.asarray(a_pos); a_vel = np.asarray(a_vel)
            d_pos = np.asarray(d_pos); d_vel = np.asarray(d_vel)

            dest = p["end_xy_m"]
            I_a = influence_points(dest[None, :], a_pos, a_vel, f.ball_xy)  # (Pa,1)
            I_d = influence_points(dest[None, :], d_pos, d_vel, f.ball_xy)  # (Pd,1)
            pc = float(_sigmoid(I_a.sum() - I_d.sum()))
            pcs.append(pc); ys.append(int(p["completed"]))
    return np.asarray(pcs), np.asarray(ys)


# --- Value-function MSE -----------------------------------------------------
def value_mse(model: ValueMLP, holdout_path: Path,
              device: str = "cpu") -> float:
    arr = np.load(holdout_path)
    X = torch.from_numpy(arr["X"]).to(device)
    y = torch.from_numpy(arr["y"]).to(device)
    model.to(device).eval()
    with torch.no_grad():
        pred = model(X)
        mse = float(((pred - y) ** 2).mean().item())
    return mse


# --- CLI --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir",    default="sample_games/skillcorner")
    ap.add_argument("--events-dir",  default="sample_games/statsbomb")
    ap.add_argument("--matches-csv", default="matches.csv",
                    help="Optional matches.csv mapping skillcorner↔statsbomb. "
                         "If absent, the script matches by base filename.")
    ap.add_argument("--model",       default="out/value_function.pt")
    ap.add_argument("--holdout",     default="out/value_function_holdout.npz")
    ap.add_argument("--out-dir",     default="out")
    ap.add_argument("--device",      default="cpu")
    args = ap.parse_args()

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    # --- (a) Pitch-control Brier --------------------------------------------
    pairs: list[tuple[Path, Path]] = []
    if Path(args.matches_csv).exists():
        with open(args.matches_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sb = Path(args.events_dir) / f"{r['statsbomb']}.json"
                sc = Path(args.data_dir)   / f"{r['skillcorner']}.zip"
                if sb.exists() and sc.exists():
                    pairs.append((sc, sb))
    else:
        zips = sorted(Path(args.data_dir).glob("*.zip"))
        for z in zips:
            stem = z.stem
            sb = Path(args.events_dir) / f"{stem}.json"
            if sb.exists():
                pairs.append((z, sb))
    if not pairs:
        # Fallback: try the sample game pairing.
        zips = sorted(Path(args.data_dir).glob("*.zip"))
        sbs  = sorted(Path(args.events_dir).glob("*.json"))
        sbs  = [s for s in sbs if "lineups" not in s.name]
        if len(zips) == 1 and len(sbs) == 1:
            pairs = [(zips[0], sbs[0])]
            print(f"  (fallback pairing) {zips[0].name} ↔ {sbs[0].name}")

    if not pairs:
        print("WARNING: no (skillcorner, statsbomb) pairs found; "
              "skipping Brier evaluation.")
        all_pc, all_y = np.empty(0), np.empty(0)
    else:
        all_pc, all_y = [], []
        for sc, sb in pairs:
            print(f"[Brier] {sc.name} / {sb.name}")
            pcs, ys = brier_for_match(sc, sb)
            print(f"   aligned passes: {len(pcs)}")
            all_pc.append(pcs); all_y.append(ys)
        all_pc = np.concatenate(all_pc) if all_pc else np.empty(0)
        all_y  = np.concatenate(all_y)  if all_y  else np.empty(0)

    if len(all_pc):
        brier = float(np.mean((all_pc - all_y) ** 2))
        completion_rate = float(all_y.mean())
        baseline = float(np.mean((completion_rate - all_y) ** 2))
        print(f"\nPC Brier score:  {brier:.4f}   over N={len(all_pc):,} passes")
        print(f"Baseline (mean completion={completion_rate:.3f}): {baseline:.4f}")
    else:
        brier = float("nan"); completion_rate = float("nan")
        baseline = float("nan")

    # --- (b) MLP MSE on holdout ---------------------------------------------
    model_path = Path(args.model)
    holdout_path = Path(args.holdout)
    if not model_path.exists() or not holdout_path.exists():
        print(f"\n(skipped value MSE: missing {model_path} or {holdout_path})")
        mse = float("nan"); hidden_dim = None
    else:
        ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
        hidden_dim = ckpt.get("hidden_dim", 64)
        model = ValueMLP(hidden_dim=hidden_dim)
        model.load_state_dict(ckpt["state_dict"])
        mse = value_mse(model, holdout_path, device=args.device)
        print(f"\nV(p, t) holdout MSE: {mse:.5f}   "
              f"(hidden_dim={hidden_dim}, "
              f"N={np.load(holdout_path)['X'].shape[0]:,})")

    # --- Report -------------------------------------------------------------
    summary = {
        "pitch_control_brier": brier,
        "completion_rate": completion_rate,
        "pitch_control_baseline_brier": baseline,
        "value_holdout_mse": mse,
        "n_passes": int(len(all_pc)),
    }
    with open(out_dir / "validation_summary.json", "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)
    print(f"\nSaved {out_dir / 'validation_summary.json'}")


if __name__ == "__main__":
    main()

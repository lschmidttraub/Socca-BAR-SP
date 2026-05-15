  # Wide Open Spaces — Implementation Notes

A self-contained Python implementation of the parametric pitch-control and
pitch-value framework from Fernandez & Bornn (2018), *Wide Open Spaces:
A statistical technique for measuring space creation in professional soccer*.

The codebase consumes SkillCorner extrapolated tracking data (10 Hz,
22 player coordinates + ball) and produces

1. a trained pitch-value function `V(p, t) : R⁴ → R`;
2. an empirical validation report (Brier score of the pitch-control
   surface evaluated at pass destinations, plus MSE of `V` on a held-out
   set);
3. inference artefacts at an arbitrary `(match, time)`: the pitch-control
   matrix `PC(p, t)`, the value matrix `V(p, t)`, the quality matrix
   `Q(p, t) = PC ⊙ V`, per-player Space Occupation Gain (SOG) and Loss,
   and a contour map overlaid with velocity vectors and player means.

The implementation follows the paper symbol-for-symbol. The remainder of
this document records the design decisions that are not pinned down by
the paper alone.

---

## 1. Mathematical formulation

### 1.1 Spatial influence

For each player `i` at time `t`, the spatial influence `I_i(p, t)` is the
ratio of two evaluations of a bivariate Gaussian density

```
f_i(p, t) = (2π)⁻¹ |Σ_i(t)|⁻¹ᐟ² exp[ -½ (p − μ_i(t))ᵀ Σ_i(t)⁻¹ (p − μ_i(t)) ],
I_i(p, t) = f_i(p, t) / f_i(p_i(t), t).
```

The normalisation guarantees `I_i(p_i(t), t) = 1`, so the surface is
peaked at the player's own coordinate and decays smoothly outward.

The covariance is obtained from the singular-value decomposition

```
Σ_i(t) = R(θ_i) · S_i(t) · S_i(t) · R(θ_i)⁻¹,
```

where `R(θ_i)` is the 2D rotation by `θ_i = atan2(s_y, s_x)` and `S_i(t)`
is the diagonal scaling matrix

```
S_x = (R_i(t) + R_i(t) · ρ_i(t)) / 2,
S_y = (R_i(t) − R_i(t) · ρ_i(t)) / 2,   with  ρ_i(t) = ||s_i(t)||² / 13².
```

The influence radius `R_i(t)` is a monotone function of the player's
Euclidean distance `d_i(t)` to the ball:

```
R_i(t) = 4 + 6 · min(d, 18)³ / 18³ ,   R_i(t) ∈ [4, 10] m.
```

This is the cubic ramp in Figure 9 of the paper; it saturates at 18 m
and is bounded by `R_min = 4` and `R_max = 10`.

The mean translates the player position along the velocity vector:

```
μ_i(t) = p_i(t) + ½ s_i(t).
```

### 1.2 Pitch control

For a query point `p ∈ R²`, summing per-player influence over each team
and pushing the difference through the logistic function gives the
team-pitch-control surface

```
PC(p, t) = σ( Σ_{k ∈ A} I_k(p, t) − Σ_{j ∈ B} I_j(p, t) )    ∈ (0, 1).
```

A single player without any opponent influence at his own location
contributes `σ(1) ≈ 0.73`, so higher local density of teammates is what
raises team control above the single-player asymptote.

### 1.3 Pitch value

The value of a coordinate is *learned* rather than prescribed. The
hypothesis is that, marginalised over many defensive situations, the
collective defender influence at a point is a proxy for that point's
intrinsic value: defenders concentrate around high-value space.

Concretely, for each sampled defensive situation we compute the per-cell
target

```
D_{i,j}(t) = Σ_{d ∈ defenders} I_d(p_b(t), p_{i,j}(t)),
V̂_{i,j}(t) = clip(D_{i,j}(t), 0, 1).
```

A feed-forward MLP with a single hidden layer of width 64 and sigmoid
activations is trained on `(p_b, p) → V̂` pairs by minimising

```
L(Θ) = (1/N) Σ_n ( V̂_n − f_Θ(p_b^n, p^n) )².
```

Both inputs are scaled to the unit square `[0, 1]²` before entering the
network; the output is bounded in `(0, 1)` by the final sigmoid.

### 1.4 Quality, occupation gain, occupation loss

The Hadamard product

```
Q(p, t) = PC(p, t) ⊙ V(p, t)
```

is a per-cell joint score of *level of control* and *value of that
control*. Reducing this surface to a per-player scalar follows the
weighted-mean definition

```
Q_i(t) = ( Σ_p I_i(p, t) V(p, t) ) / ( Σ_p I_i(p, t) ),
```

i.e. the player's V-weighted average over the area they influence; this
keeps `Q_i ∈ [0, 1]` independent of grid resolution.

For a temporal window of `w` frames (paper uses `w = 30` at 10 Hz, i.e.
3 s) the discrete derivative is

```
G_i(t) = (1/w) Σ_{k=1..w} Q_i(t + k) − Q_i(t),
SOG_i(t) =  G_i(t) · 𝟙[G_i(t) ≥  ε],
SOL_i(t) = −G_i(t) · 𝟙[G_i(t) ≤ −ε].
```

The threshold `ε` excludes drift due to slow contextual motion.

---

## 2. Code layout

```
soccer_space/
├── core.py     mathematical primitives (vectorised numpy)
├── data.py     SkillCorner zip loader + finite-difference velocities
└── model.py    PyTorch ValueMLP (R⁴ → R, one hidden layer, sigmoid)

train_value_function.py   Script 1 — sample collection + Adam training
validate.py               Script 2 — PC Brier on passes + V MSE on holdout
spatial_inference.py      Script 3 — PC/V/Q grids + SOG + matplotlib output
```

### 2.1 Tensor conventions

| Symbol | Meaning            | Shape                |
|--------|--------------------|----------------------|
| `P`    | players in a frame | scalar (typically 22)|
| `H, W` | grid rows, cols    | typical: 15 × 21 (training), 68 × 105 (inference) |
| `G`    | `H · W`            | scalar               |
| `B`    | minibatch size     | scalar               |

All grids are stored as `(H, W, 2)` for coordinates and `(H, W)` for
scalar fields. Per-player stacks use the leading dimension: `(P, H, W)`
for influence surfaces, `(P, 2)` for positions / velocities / means,
`(P, 2, 2)` for covariances. Pitch coordinates are centred at `(0, 0)`,
`x ∈ [−52.5, +52.5]` m, `y ∈ [−34, +34]` m (FIFA pitch dimensions
`105 × 68` m, matching the SkillCorner convention).

### 2.2 Influence-grid kernel (`core.influence_grid`)

Given a `(H, W, 2)` grid and `(P, 2)` player coordinates, the routine
computes `(P, H, W)` influence values via two `einsum` calls

```
tmp[..., p, i] = Σ_j diff[..., p, j] · Σ_p⁻¹[j, i]
quad[..., p]    = Σ_i tmp[..., p, i] · diff[..., p, i]
```

and a single `exp`. Memory peak is `O(H · W · P)` doubles; the per-cell
normalisation `f_i(p_i(t), t)` is computed once per player and
broadcast.

### 2.3 SkillCorner loader (`data.py`)

The loader streams `<match_id>_tracking_extrapolated.jsonl` directly
out of the bundled zip without extracting to disk. Match metadata
(`players[].id`, `players[].team_id`, `match_periods[].start_frame`,
home / away ids) is read once and reused. Velocities are not present in
the raw tracking; they are computed by centred finite difference

```
s_i(t) ≈ ( p_i(t + h) − p_i(t − h) ) / (2 h Δt),
```

with a default `h = 3` frames (0.6 s window at 10 Hz). At stream
boundaries the formula gracefully degrades to forward / backward
differences.

### 2.4 Single-pass sample collection

`train_value_function.build_samples_from_match` consumes each match's
JSONL exactly once. A rolling positions buffer and a list of pending
target frames are maintained simultaneously: a target registered at
frame `F` is finalised at frame `F + h` once its forward velocity
window has been buffered. Older buffer entries are pruned as soon as no
pending target depends on them, so peak memory is bounded by
`O(stride + 2h)` frames per match.

The candidate-frame policy is the paper's: at least `Δt = 3` seconds
between samples, valid possession by either team, and capped at
`max_per_match` situations to keep matches balanced.

### 2.5 MLP

```
fc1: R⁴ → R^{64}      sigmoid
fc2: R^{64} → R^1     sigmoid
loss: MSE
optimiser: Adam(lr = 1e-3)
```

The Adam initialisation is the PyTorch default (`β = (0.9, 0.999)`,
`ε = 1e-8`). Weights are not regularised. The hidden-layer width was
selected to match the paper's "small" architecture; it is exposed as
`--hidden`.

### 2.6 PC Brier evaluation

For each `Pass` event in the StatsBomb feed with an `end_location`, the
script computes the SkillCorner frame index

```
F = period_starts[period] + round(ts_seconds · 10) + 5,
```

where the trailing `+5` (`0.5 s`) approximates ball flight time, since
StatsBomb does not store pass arrival time. The pitch-control surface
is evaluated at the pass destination in the tracking-data coordinate
frame; the binary label is `1` if SB lists no outcome (i.e. completed)
and `0` otherwise. The Brier score

```
Brier = (1/N) Σ_n ( PC_n − y_n )²
```

is compared against the constant-mean baseline `Σ_n ( c − y_n )²` where
`c = mean(y_n)`. A score strictly below baseline confirms that PC
carries useful signal beyond league-level completion rate.

### 2.7 Pitch-value MSE

`train_value_function.py` writes 10 % of all `(p_b, p, V̂)` triples to
`out/wos/value_function_holdout.npz`. `validate.py` loads the trained
checkpoint and reports `(1/N) Σ (ŷ_n − V̂_n)²` on that set.

### 2.8 SOG and visualisation

For a chosen frame `t`, `spatial_inference.py` reads the position
buffer from `t − h` to `t + w + h`, computes `Q_i(t)` and the mean
`Q_i(t + k)` over `k = 1, …, w`, applies the threshold `ε`, and prints
the resulting SOG / SOL scalars per player.

The figure pipeline produces

- a combined map: `contourf(Q)` colour field, `quiver(s_i)` velocity
  vectors anchored at `p_i`, and `scatter(μ_i)` markers split by team,
  plus a ball marker, written at 200 DPI;
- a three-panel decomposition of `PC`, `V`, and `Q` side by side.

---

## 3. How to run

```powershell
# Train.
python train_value_function.py --data-dir data/skillcorner \
    --out-dir out/wos --epochs 25 --max-per-match 400 --hidden 64

# Validate.
python validate.py --data-dir data/skillcorner \
    --events-dir data/statsbomb --matches-csv matches.csv \
    --model out/wos/value_function.pt \
    --holdout out/wos/value_function_holdout.npz \
    --out-dir out/wos

# Inference at a chosen frame.
python spatial_inference.py --match data/skillcorner/<id>.zip \
    --model out/wos/value_function.pt --out-dir out/wos \
    --period 1 --time-sec 1234.5 --window 30 --epsilon 0.02
```

CLI flags of interest:

| Flag | Default | Meaning |
|------|---------|---------|
| `--min-dt`         | `3.0`  | minimum spacing between sampled situations, in seconds |
| `--max-per-match`  | `400`  | cap on situations sampled per match |
| `--grid-nx, --grid-ny` | `21, 15` (train) / `105, 68` (infer) | grid resolution |
| `--window`         | `30`   | SOG window `w` in frames at 10 Hz |
| `--epsilon`        | `0.02` | SOG threshold on weighted-mean Q scale |
| `--vel-half-window`| `3`    | half-window for centred-FD velocity |
| `--hidden`         | `64`   | MLP hidden-layer width |

---

## 4. Calibration against the paper

A reduced run on a single match (one zip from `sample_games/`, 8
epochs) reached `val MSE = 0.086`, matching the paper's reported
10-fold value of `0.085 ± 0.001`. Convergence on the full SkillCorner
collection (25 epochs) is monitored via the train / validation curve
written to `out/wos/value_function_loss.png`.

The Brier baseline (constant `c = mean completion rate`) is
approximately `c · (1 − c)` because labels are Bernoulli; a useful
pitch-control surface beats that strictly.

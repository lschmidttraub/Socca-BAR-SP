"""Core mathematical primitives for the Fernandez & Bornn (2018) framework.

Tensor-dimension conventions used throughout this module:

    P    : number of players in a frame (typically 11 per team).
    H, W : grid resolution in the y- and x-axes respectively. The paper uses
           a 15 x 21 grid (H=15, W=21) over a 68 m x 105 m pitch.
    G    : H * W (flattened grid index).
    B    : minibatch size (used by the MLP).

Coordinate system: pitch-centred Cartesian (x, y) in meters with the origin
at the centre circle, x in [-PITCH_LEN/2, +PITCH_LEN/2], y in [-PITCH_WID/2,
+PITCH_WID/2]. The same convention is used by SkillCorner tracking JSONL.
"""

from __future__ import annotations

import numpy as np


# --- Pitch constants --------------------------------------------------------
PITCH_LEN: float = 105.0           # x extent in meters
PITCH_WID: float = 68.0            # y extent in meters
MAX_SPEED: float = 13.0            # paper section A.1: s_max
RADIUS_MIN: float = 4.0            # paper section A.1: R_min in meters
RADIUS_MAX: float = 10.0           # paper section A.1: R_max in meters
MU_SHIFT_FACTOR: float = 0.5       # paper section A.1: mu_i = p_i + 0.5 * s


# --- Influence-radius transformation ----------------------------------------
def influence_radius(dist_to_ball: np.ndarray) -> np.ndarray:
    """Map distance-to-ball d in meters to a control-surface radius R_i(t).

    Implements the monotone transformation shown in the paper's Figure 9:
    a cubic ramp from R_MIN at d=0 to R_MAX at d=18, saturating at R_MAX
    beyond 18 m. Vectorised over arbitrary input shape.

    Parameters
    ----------
    dist_to_ball : ndarray, shape (...)

    Returns
    -------
    R : ndarray, shape (...) in [R_MIN, R_MAX]
    """
    d = np.minimum(dist_to_ball, 18.0)
    r = RADIUS_MIN + (RADIUS_MAX - RADIUS_MIN) * (d ** 3) / (18.0 ** 3)
    return np.clip(r, RADIUS_MIN, RADIUS_MAX)


# --- Per-player covariance / mean -------------------------------------------
def covariance_matrices(velocities: np.ndarray,
                        dist_to_ball: np.ndarray) -> np.ndarray:
    """Compute per-player covariance matrices Σ_i(t).

    The covariance is constructed from R(θ) S(t) S(t) R(θ)^{-1} (paper Eq. 15),
    where R is a 2D rotation by θ = atan2(s_y, s_x) and S is the diagonal
    scaling matrix that stretches the surface along the velocity direction.

    Parameters
    ----------
    velocities  : ndarray, shape (P, 2) — per-player (s_x, s_y) in m/s.
    dist_to_ball: ndarray, shape (P,)   — Euclidean distance to ball in meters.

    Returns
    -------
    Sigma : ndarray, shape (P, 2, 2)
    """
    velocities = np.asarray(velocities, dtype=np.float64)
    dist_to_ball = np.asarray(dist_to_ball, dtype=np.float64)
    P = velocities.shape[0]

    speed = np.linalg.norm(velocities, axis=1)                       # (P,)
    theta = np.arctan2(velocities[:, 1], velocities[:, 0])           # (P,)

    R_i = influence_radius(dist_to_ball)                             # (P,)
    s_ratio = (speed ** 2) / (MAX_SPEED ** 2)                        # (P,)
    s_x = (R_i + R_i * s_ratio) / 2.0                                # (P,)
    s_y = (R_i - R_i * s_ratio) / 2.0                                # (P,)
    s_y = np.clip(s_y, 1e-3, None)        # ensure positive-definiteness

    c, s = np.cos(theta), np.sin(theta)
    R = np.empty((P, 2, 2), dtype=np.float64)
    R[:, 0, 0] =  c;  R[:, 0, 1] = -s
    R[:, 1, 0] =  s;  R[:, 1, 1] =  c

    S = np.zeros((P, 2, 2), dtype=np.float64)
    S[:, 0, 0] = s_x
    S[:, 1, 1] = s_y

    # Σ = R S S R^{-1}   with R^{-1} = R^T for a rotation matrix.
    RS = np.einsum('pij,pjk->pik', R, S)                             # (P,2,2)
    RSSR = np.einsum('pij,pjk->pik', RS, RS.transpose(0, 2, 1))      # (P,2,2)
    return RSSR


def means(positions: np.ndarray, velocities: np.ndarray) -> np.ndarray:
    """μ_i(t) = p_i(t) + 0.5 * s_i(t).  Shapes: positions, velocities (P,2)."""
    return positions + MU_SHIFT_FACTOR * velocities


# --- Spatial influence I_i(p, t) --------------------------------------------
def _bivariate_gauss_unnorm(diff: np.ndarray, inv_cov: np.ndarray) -> np.ndarray:
    """Un-normalised Gaussian kernel exp(-0.5 (p-μ)^T Σ^{-1} (p-μ)).

    diff    : (..., P, 2)
    inv_cov : (P, 2, 2)

    Returns : (..., P)
    """
    # quadratic form per player and per query point.
    # tmp[..., p, i] = sum_j diff[..., p, j] * inv_cov[p, j, i]
    tmp = np.einsum('...pj,pji->...pi', diff, inv_cov)
    quad = np.einsum('...pi,...pi->...p', tmp, diff)
    return np.exp(-0.5 * quad)


def influence_grid(grid_xy: np.ndarray,
                   positions: np.ndarray,
                   velocities: np.ndarray,
                   ball_xy: np.ndarray) -> np.ndarray:
    """Compute I_i(p, t) for every player at every grid point.

    Parameters
    ----------
    grid_xy   : (H, W, 2)         — grid coordinates in meters.
    positions : (P, 2)            — player positions p_i(t).
    velocities: (P, 2)            — player velocities s_i(t).
    ball_xy   : (2,)              — ball position p_b(t).

    Returns
    -------
    I : (P, H, W) — per-player normalised influence values in (0, 1].

    Each player's influence is normalised so that I_i(p_i(t), t) = 1, i.e.
    each player's surface peaks at his own coordinate.
    """
    H, W, _ = grid_xy.shape

    d_ball = np.linalg.norm(positions - ball_xy[None, :], axis=1)     # (P,)
    Sigma  = covariance_matrices(velocities, d_ball)                  # (P,2,2)
    mu     = means(positions, velocities)                             # (P,2)

    inv_cov = np.linalg.inv(Sigma)                                    # (P,2,2)

    # Diff at every grid point: (H, W, P, 2)
    diff_grid = grid_xy[:, :, None, :] - mu[None, None, :, :]
    # Diff at the player's own position (for normalisation): (P, 2)
    diff_self = positions - mu

    num = _bivariate_gauss_unnorm(diff_grid, inv_cov)                 # (H,W,P)
    den = _bivariate_gauss_unnorm(diff_self[None, ...], inv_cov)[0]   # (P,)
    den = np.maximum(den, 1e-12)

    influence = num / den                                             # (H,W,P)
    return np.transpose(influence, (2, 0, 1))                         # (P,H,W)


def influence_points(query_xy: np.ndarray,
                     positions: np.ndarray,
                     velocities: np.ndarray,
                     ball_xy: np.ndarray) -> np.ndarray:
    """I_i evaluated at a list of N query points instead of a grid.

    query_xy : (N, 2)
    returns  : (P, N)
    """
    N = query_xy.shape[0]
    d_ball = np.linalg.norm(positions - ball_xy[None, :], axis=1)
    Sigma  = covariance_matrices(velocities, d_ball)
    mu     = means(positions, velocities)
    inv_cov = np.linalg.inv(Sigma)

    diff_q    = query_xy[:, None, :] - mu[None, :, :]                 # (N,P,2)
    diff_self = positions - mu                                        # (P,2)
    num = _bivariate_gauss_unnorm(diff_q, inv_cov)                    # (N,P)
    den = _bivariate_gauss_unnorm(diff_self[None, ...], inv_cov)[0]   # (P,)
    den = np.maximum(den, 1e-12)
    return (num / den).T                                              # (P,N)


# --- Pitch-control surface --------------------------------------------------
def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def pitch_control_from_influence(I_atk: np.ndarray,
                                 I_def: np.ndarray) -> np.ndarray:
    """PC(p, t) = σ(Σ_A I_k − Σ_B I_j).

    I_atk, I_def : (P_a, H, W), (P_d, H, W).  Returns (H, W) in (0, 1).
    """
    delta = I_atk.sum(axis=0) - I_def.sum(axis=0)
    return _sigmoid(delta)


# --- Value-function target generation ---------------------------------------
def defensive_value_target(I_def: np.ndarray) -> np.ndarray:
    """Empirical defensive spatial density target for V_i,j(t).

    V̂(p, t) = clip(Σ_d I_d(p, t), 0, 1).  Shapes: I_def (P_d, H, W) → (H, W).
    """
    D = I_def.sum(axis=0)
    return np.clip(D, 0.0, 1.0)


# --- Grid utilities ---------------------------------------------------------
def make_grid(nx: int = 21, ny: int = 15,
              pitch_len: float = PITCH_LEN,
              pitch_wid: float = PITCH_WID) -> np.ndarray:
    """Return a (ny, nx, 2) array of (x, y) grid-cell centres in meters."""
    xs = np.linspace(-pitch_len / 2 + pitch_len / (2 * nx),
                     +pitch_len / 2 - pitch_len / (2 * nx), nx)
    ys = np.linspace(-pitch_wid / 2 + pitch_wid / (2 * ny),
                     +pitch_wid / 2 - pitch_wid / (2 * ny), ny)
    xx, yy = np.meshgrid(xs, ys)        # both (ny, nx)
    return np.stack([xx, yy], axis=-1)  # (ny, nx, 2)


def normalise_xy(xy: np.ndarray) -> np.ndarray:
    """Map pitch coords ∈ [-L/2, L/2] × [-W/2, W/2] → [0, 1]^2 for MLP input."""
    out = np.asarray(xy, dtype=np.float64).copy()
    out[..., 0] = (out[..., 0] + PITCH_LEN / 2.0) / PITCH_LEN
    out[..., 1] = (out[..., 1] + PITCH_WID / 2.0) / PITCH_WID
    return out

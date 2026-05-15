"""PyTorch model for V(p, t): a feed-forward MLP with one hidden layer.

Input  x ∈ R^4 = (p_b, p) where p_b = (p_bx, p_by) is the ball position and
                p = (p_x, p_y) is the query coordinate (both normalised to
                [0, 1]^2).
Hidden : one fully-connected layer of width `hidden_dim` with sigmoid
         activation (paper section 4).
Output : ŷ ∈ R, a sigmoid-bounded scalar in (0, 1).
"""

from __future__ import annotations

import torch
from torch import nn


class ValueMLP(nn.Module):
    def __init__(self, hidden_dim: int = 64):
        super().__init__()
        self.fc1 = nn.Linear(4, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, 1)
        self.act = nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x : (B, 4) → ŷ : (B, 1) ∈ (0, 1)."""
        h = self.act(self.fc1(x))
        y = self.act(self.fc2(h))
        return y


def predict_grid(model: ValueMLP,
                 ball_xy_norm: tuple[float, float],
                 grid_xy_norm,
                 device: str = "cpu"):
    """Evaluate the MLP on every cell of a normalised grid.

    Parameters
    ----------
    model         : trained ValueMLP.
    ball_xy_norm  : (2,) tuple, ball coordinate in [0, 1]^2.
    grid_xy_norm  : (H, W, 2) ndarray, query grid in [0, 1]^2.

    Returns
    -------
    V : (H, W) numpy ndarray in (0, 1).
    """
    import numpy as np
    H, W, _ = grid_xy_norm.shape
    flat = grid_xy_norm.reshape(-1, 2)                    # (H*W, 2)
    bx = torch.full((flat.shape[0], 1), float(ball_xy_norm[0]))
    by = torch.full((flat.shape[0], 1), float(ball_xy_norm[1]))
    px = torch.from_numpy(flat[:, 0:1].astype("float32"))
    py = torch.from_numpy(flat[:, 1:2].astype("float32"))
    x = torch.cat([bx, by, px, py], dim=1).to(device)
    model.eval()
    with torch.no_grad():
        y = model(x).cpu().numpy().reshape(H, W)
    return y

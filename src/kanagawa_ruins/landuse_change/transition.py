"""Transition matrices, gain/loss/swap decomposition and neighbourhood change context.

All area figures are sums of per-cell projected areas (m2), never cell counts.
"""

import numpy as np
import pandas as pd


def transition_matrix(frame, from_col, to_col, weight_col="area_m2", order=None):
    """Area-weighted cross tabulation (rows = from, columns = to)."""
    table = frame.pivot_table(index=from_col, columns=to_col, values=weight_col, aggfunc="sum", fill_value=0.0)
    if order is not None:
        labels = [c for c in order if c in set(table.index) | set(table.columns)]
        extra = sorted((set(table.index) | set(table.columns)) - set(labels))
        labels += extra
        table = table.reindex(index=labels, columns=labels, fill_value=0.0)
    table.index.name = from_col
    table.columns.name = to_col
    return table


def gain_loss_swap(matrix, unit="m2"):
    """Per-class gross gain/loss, net change and swap (Pontius et al. 2004 decomposition).

    swap = 2 * min(gain, loss): change that is offset by change elsewhere. High swap
    relative to net change is typical of classification noise or boundary reallocation,
    although genuine relocation of a land use can also produce it.
    """
    m = matrix.to_numpy(dtype=float)
    diag = np.diag(m)
    start = m.sum(axis=1)
    end = m.sum(axis=0)
    loss = start - diag
    gain = end - diag
    swap = 2 * np.minimum(gain, loss)
    total = gain + loss
    out = pd.DataFrame(
        {
            f"start_{unit}": start,
            f"end_{unit}": end,
            f"persistence_{unit}": diag,
            f"gross_loss_{unit}": loss,
            f"gross_gain_{unit}": gain,
            f"net_change_{unit}": end - start,
            f"swap_{unit}": swap,
            f"total_change_{unit}": total,
        },
        index=matrix.index,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        out["net_change_rate"] = np.where(start > 0, (end - start) / start, np.nan)
        out["swap_share_of_total_change"] = np.where(total > 0, swap / total, np.nan)
    return out


def rasterize(iy, ix, values, fill):
    """Place cell values on a dense grid; returns grid and (row, col) of each cell."""
    iy = np.asarray(iy)
    ix = np.asarray(ix)
    r = iy - iy.min()
    c = ix - ix.min()
    grid = np.full((r.max() + 1, c.max() + 1), fill, dtype=np.asarray(values).dtype)
    if np.any(grid.shape) and len(np.unique(r * grid.shape[1] + c)) != len(r):
        raise ValueError("Duplicate cell positions")
    grid[r, c] = values
    return grid, r, c


def _neighbours(grid, fill):
    """Stack of the 8 neighbour grids (padded with fill)."""
    p = np.pad(grid, 1, constant_values=fill)
    h, w = grid.shape
    return [p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


def change_context(iy, ix, code_from, code_to):
    """Per-cell neighbourhood context of observed change (8-neighbourhood).

    Returns a DataFrame with:
    - same_transition_neighbours: neighbours with the identical from->to transition
    - to_class_in_from_neighbourhood: the new class already bordered the cell at t0
      (a boundary shift / mixed-pixel reallocation is plausible)
    - context: 'no_change', 'isolated_boundary', 'isolated_interior', 'patch'
      ('patch' = at least 2 neighbours share the transition)
    Missing neighbours (outside the data) count as not matching.
    """
    a = np.asarray(code_from).astype(str)
    b = np.asarray(code_to).astype(str)
    vocab = {v: i + 1 for i, v in enumerate(sorted(set(a) | set(b)))}
    ia = np.array([vocab[v] for v in a], dtype=np.int32)
    ib = np.array([vocab[v] for v in b], dtype=np.int32)
    ga, r, c = rasterize(iy, ix, ia, 0)
    gb, _, _ = rasterize(iy, ix, ib, 0)
    trans = np.where(ga != gb, ga * 1000 + gb, -1)
    trans[ga == 0] = -1
    same = np.zeros(ga.shape, dtype=np.int8)
    for n in _neighbours(trans, -2):
        same += (n == trans) & (trans >= 0)
    border = np.zeros(ga.shape, dtype=bool)
    for n in _neighbours(ga, 0):
        border |= n == gb
    changed = ia != ib
    s = same[r, c]
    bd = border[r, c] & changed
    context = np.where(
        ~changed,
        "no_change",
        np.where(s >= 2, "patch", np.where(bd, "isolated_boundary", "isolated_interior")),
    )
    return pd.DataFrame(
        dict(
            same_transition_neighbours=np.where(changed, s, 0).astype(np.int8),
            to_class_in_from_neighbourhood=bd,
            context=context,
        )
    )

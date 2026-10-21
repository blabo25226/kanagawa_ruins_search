"""Spatial statistics on regular mesh grids (no libpysal dependency).

Assumptions are explicit: binary queen (8-neighbour) contiguity on the mesh grid,
row-standardised weights, cells without a value are dropped (their links removed),
inference by conditional-free random permutation of values over the observed cells.
"""

import numpy as np
from scipy import sparse


def queen_weights(rows, cols):
    """Row-standardised sparse queen weights for cells at integer grid positions."""
    rows = np.asarray(rows, dtype=np.int64)
    cols = np.asarray(cols, dtype=np.int64)
    n = len(rows)
    key = {(int(r), int(c)): i for i, (r, c) in enumerate(zip(rows, cols))}
    if len(key) != n:
        raise ValueError("Duplicate grid positions")
    src, dst = [], []
    for i, (r, c) in enumerate(zip(rows, cols)):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr or dc:
                    j = key.get((int(r) + dr, int(c) + dc))
                    if j is not None:
                        src.append(i)
                        dst.append(j)
    w = sparse.csr_matrix((np.ones(len(src)), (src, dst)), shape=(n, n))
    deg = np.asarray(w.sum(axis=1)).ravel()
    inv = np.divide(1.0, deg, out=np.zeros_like(deg), where=deg > 0)
    return sparse.diags(inv) @ w, deg


def morans_i(values, w):
    z = np.asarray(values, dtype=float)
    z = z - z.mean()
    denom = (z * z).sum()
    if denom == 0:
        return np.nan
    s0 = w.sum()
    return (len(z) / s0) * (z @ (w @ z)) / denom


def morans_i_test(values, rows, cols, permutations=999, seed=20261011):
    """Global Moran's I with a one-sided (positive autocorrelation) permutation p-value."""
    values = np.asarray(values, dtype=float)
    ok = np.isfinite(values)
    v = values[ok]
    w, deg = queen_weights(np.asarray(rows)[ok], np.asarray(cols)[ok])
    keep = deg > 0  # islands contribute nothing; drop them and renormalise
    if not keep.all():
        v = v[keep]
        w, deg = queen_weights(np.asarray(rows)[ok][keep], np.asarray(cols)[ok][keep])
    observed = morans_i(v, w)
    rng = np.random.default_rng(seed)
    sims = np.array([morans_i(rng.permutation(v), w) for _ in range(permutations)])
    p = (1 + np.sum(sims >= observed)) / (permutations + 1)
    return dict(
        I=float(observed),
        expected_I=float(-1.0 / (len(v) - 1)),
        n=int(len(v)),
        permutations=int(permutations),
        p_one_sided=float(p),
        sim_mean=float(sims.mean()),
        sim_sd=float(sims.std(ddof=1)),
        weights="queen, row-standardised, islands dropped",
    )


def block_bootstrap_ratio(num, den, blocks, n_boot=999, seed=20261011, ci=0.95):
    """CI for sum(num)/sum(den) resampling whole spatial blocks with replacement.

    Resampling blocks rather than cells keeps within-block spatial dependence; it is
    only approximately valid when dependence between blocks is weak.
    """
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    labels, inv = np.unique(np.asarray(blocks), return_inverse=True)
    bn = np.bincount(inv, weights=num, minlength=len(labels))
    bd = np.bincount(inv, weights=den, minlength=len(labels))
    est = bn.sum() / bd.sum() if bd.sum() > 0 else np.nan
    rng = np.random.default_rng(seed)
    k = len(labels)
    idx = rng.integers(0, k, size=(n_boot, k))
    sn = bn[idx].sum(axis=1)
    sd = bd[idx].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(sd > 0, sn / sd, np.nan)
    r = r[np.isfinite(r)]
    alpha = (1 - ci) / 2
    lo, hi = (np.quantile(r, [alpha, 1 - alpha]) if len(r) else (np.nan, np.nan))
    return dict(estimate=float(est), ci_low=float(lo), ci_high=float(hi), blocks=int(k), n_boot=int(n_boot))

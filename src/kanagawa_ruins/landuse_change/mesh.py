"""JIS X 0410 mesh codes for the L03-b 100 m subdivision mesh.

A 10-digit L03-b code is the 8-digit 3rd mesh code followed by the row (latitude)
and column (longitude) of the 1/10 subdivision, counted from the south-west corner.
Codes are datum-specific: the same code in Tokyo Datum and JGD2000/2011 denotes
different ground positions, so codes may only be joined within one datum family.
"""

import numpy as np

CELL_DLAT = 1.0 / 1200.0  # 3 arc-seconds
CELL_DLON = 1.0 / 800.0  # 4.5 arc-seconds


def _digits(codes, width):
    s = np.asarray(codes, dtype=str)
    if s.size and not np.all(np.char.str_len(s) == width):
        raise ValueError(f"Mesh codes must have exactly {width} digits")
    if s.size and not np.all(np.char.isdigit(s)):
        raise ValueError("Mesh codes must be numeric strings")
    return s


def _digit_matrix(s, width):
    raw = np.frombuffer(s.astype(f"S{width}").tobytes(), dtype=np.uint8)
    return (raw.reshape(-1, width) - ord("0")).astype(np.int64)


def decode_100m(codes):
    """Return global integer row/column indices (iy, ix) of 100 m cells."""
    a = _digit_matrix(_digits(codes, 10), 10)
    lat1 = a[:, 0] * 10 + a[:, 1]
    lon1 = a[:, 2] * 10 + a[:, 3]
    r2, c2, r3, c3, r4, c4 = (a[:, i] for i in range(4, 10))
    if np.any(r2 > 7) or np.any(c2 > 7):
        raise ValueError("Invalid 2nd mesh digit (must be 0-7)")
    iy = lat1 * 800 + r2 * 100 + r3 * 10 + r4
    ix = lon1 * 800 + c2 * 100 + c3 * 10 + c4
    return iy, ix


def cell_bounds_deg(iy, ix):
    """South, west, north, east in degrees of the record's own datum."""
    iy = np.asarray(iy, dtype=np.float64)
    ix = np.asarray(ix, dtype=np.float64)
    south = iy * CELL_DLAT
    west = 100.0 + ix * CELL_DLON
    return south, west, south + CELL_DLAT, west + CELL_DLON


def parent_codes(codes):
    """Return (2nd mesh 6-digit, 3rd mesh 1 km 8-digit, half mesh 500 m 9-digit) codes."""
    s = _digits(codes, 10)
    second = np.char.ljust(s, 6).astype("U6")
    third = s.astype("U8")
    a = _digit_matrix(s, 10)
    r4, c4 = a[:, 8], a[:, 9]
    quadrant = 1 + (c4 >= 5).astype(np.int64) + 2 * (r4 >= 5).astype(np.int64)
    half = np.char.add(third, quadrant.astype(str))
    return second, third, half


def encode_100m(iy, ix):
    """Inverse of decode_100m (used by tests and grid reconstruction)."""
    iy = np.asarray(iy, dtype=np.int64)
    ix = np.asarray(ix, dtype=np.int64)
    out = []
    for y, x in zip(iy, ix):
        lat1, ry = divmod(int(y), 800)
        lon1, rx = divmod(int(x), 800)
        r2, ry = divmod(ry, 100)
        c2, rx = divmod(rx, 100)
        r3, r4 = divmod(ry, 10)
        c3, c4 = divmod(rx, 10)
        out.append(f"{lat1:02d}{lon1:02d}{r2}{c2}{r3}{c3}{r4}{c4}")
    return np.array(out, dtype="U10")

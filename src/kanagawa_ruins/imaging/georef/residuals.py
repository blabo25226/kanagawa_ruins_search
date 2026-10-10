"""Planar Euclidean errors in metres; validation points never enter the fit."""

import numpy as np


def residuals(transform, points):
    if not points:
        raise ValueError("Error assessment requires points")
    rows = []
    for p in points:
        x, y = transform @ (p.pixel_x, p.pixel_y)
        dx, dy = x - p.ground_x, y - p.ground_y
        rows.append(
            dict(
                point_id=p.point_id,
                dx_m=float(dx),
                dy_m=float(dy),
                error_m=float(np.hypot(dx, dy)),
            )
        )
    errors = np.array([r["error_m"] for r in rows])
    return dict(
        count=len(rows),
        rmse_m=float(np.sqrt(np.mean(errors**2))),
        mean_error_m=float(errors.mean()),
        max_error_m=float(errors.max()),
        points=rows,
    )

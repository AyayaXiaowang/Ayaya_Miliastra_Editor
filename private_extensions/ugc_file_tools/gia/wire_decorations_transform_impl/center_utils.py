from __future__ import annotations

"""Center computation helpers shared by decorations transform policies."""

from typing import Sequence, Tuple


def normalize_axes(axes_text: str) -> Tuple[bool, bool, bool]:
    """Normalize axes text into (want_x, want_y, want_z) booleans."""
    t = str(axes_text or "").strip().lower().replace(",", "").replace(" ", "")
    if t == "":
        raise ValueError("axes 不能为空")
    if any(ch not in {"x", "y", "z"} for ch in t):
        raise ValueError(f"invalid axes: {axes_text!r}")
    want_x = "x" in t
    want_y = "y" in t
    want_z = "z" in t
    if not (want_x or want_y or want_z):
        raise ValueError(f"invalid axes: {axes_text!r}")
    return want_x, want_y, want_z


def compute_center(points: Sequence[Tuple[float, float, float]], *, mode: str) -> Tuple[float, float, float]:
    """Compute a center point from points using either bbox or mean mode."""
    if not points:
        raise ValueError("points 为空")
    m = str(mode or "").strip().lower()
    if m not in {"bbox", "mean"}:
        raise ValueError(f"invalid center mode: {mode!r}")

    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]

    if m == "mean":
        n = float(len(points))
        return (sum(xs) / n, sum(ys) / n, sum(zs) / n)

    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)


"""
geometry_utils.py
-----------------
Pure-Python geometry helpers that replicate the core Grasshopper / Pufferfish
operations used by the Stair Stepper definition.

No Rhino runtime required — all geometry is represented as plain Python
dataclasses and numpy arrays so the module runs headlessly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np


# ---------------------------------------------------------------------------
# Primitive geometry types
# ---------------------------------------------------------------------------

@dataclass
class Point3d:
    x: float
    y: float
    z: float

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=float)

    def __add__(self, other: "Point3d") -> "Point3d":
        return Point3d(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Point3d") -> "Point3d":
        return Point3d(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Point3d":
        return Point3d(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> "Point3d":
        return self.__mul__(scalar)

    def project_to_xy(self) -> "Point3d":
        """Flatten Z — mirrors GH Project component onto XY plane."""
        return Point3d(self.x, self.y, 0.0)


@dataclass
class BoundingBox:
    min_pt: Point3d
    max_pt: Point3d

    @property
    def size_x(self) -> float:
        return self.max_pt.x - self.min_pt.x

    @property
    def size_y(self) -> float:
        return self.max_pt.y - self.min_pt.y

    @property
    def size_z(self) -> float:
        return self.max_pt.z - self.min_pt.z

    @property
    def center(self) -> Point3d:
        return Point3d(
            (self.min_pt.x + self.max_pt.x) / 2,
            (self.min_pt.y + self.max_pt.y) / 2,
            (self.min_pt.z + self.max_pt.z) / 2,
        )


@dataclass
class Rectangle2d:
    """Axis-aligned rectangle in XY, anchored at origin_pt."""
    origin: Point3d
    width: float   # X extent
    height: float  # Y extent


@dataclass
class Cell:
    """
    One rectangular grid cell — four corner points in XY, plus its
    2-D center used for containment testing.
    """
    corners: List[Point3d]   # 4 corners in order (CCW)
    center: Point3d


@dataclass
class StairSurface:
    """
    A planar quad surface placed at a specific Z elevation —
    the output of the stair-stepping operation.
    """
    corners: List[Point3d]   # 4 corners at their final Z
    elevation: float
    step_index: int


# ---------------------------------------------------------------------------
# Bounding box
# ---------------------------------------------------------------------------

def compute_bounding_box(points: List[Point3d]) -> BoundingBox:
    """
    Mirrors GH Bounding Box component.
    Returns axis-aligned bbox of any point cloud.
    """
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return BoundingBox(
        min_pt=Point3d(min(xs), min(ys), min(zs)),
        max_pt=Point3d(max(xs), max(ys), max(zs)),
    )


# ---------------------------------------------------------------------------
# Parameter Rectangle Grid  (mirrors Pufferfish component)
# ---------------------------------------------------------------------------

def parameter_series(n_divisions: int) -> List[float]:
    """
    Create n_divisions+1 evenly-spaced parameters from 0 → 1.
    Mirrors the GH Series(0, 1/n, n+1) → Division pattern.
    """
    if n_divisions < 1:
        raise ValueError("n_divisions must be >= 1")
    return [i / n_divisions for i in range(n_divisions + 1)]


def parameter_rectangle_grid(
    rect: Rectangle2d,
    params_x: List[float],
    params_y: List[float],
) -> List[Cell]:
    """
    Divide a rectangle into cells using parameter lists along X and Y.
    Mirrors Pufferfish 'Parameter Rectangle Grid' component.

    params_x / params_y should be values in [0, 1] in ascending order.
    """
    ox, oy = rect.origin.x, rect.origin.y
    w, h = rect.width, rect.height

    cells: List[Cell] = []
    for j in range(len(params_y) - 1):
        for i in range(len(params_x) - 1):
            x0 = ox + params_x[i]     * w
            x1 = ox + params_x[i + 1] * w
            y0 = oy + params_y[j]     * h
            y1 = oy + params_y[j + 1] * h

            corners = [
                Point3d(x0, y0, 0.0),
                Point3d(x1, y0, 0.0),
                Point3d(x1, y1, 0.0),
                Point3d(x0, y1, 0.0),
            ]
            center = Point3d((x0 + x1) / 2, (y0 + y1) / 2, 0.0)
            cells.append(Cell(corners=corners, center=center))

    return cells


# ---------------------------------------------------------------------------
# Divide Curve  (mirrors GH Divide Curve component)
# ---------------------------------------------------------------------------

def divide_curve(
    curve_points: List[Point3d],
    count: int,
    closed: bool = True,
) -> List[Point3d]:
    """
    Sample `count` evenly-spaced points along a polyline approximation
    of a curve.  Mirrors GH 'Divide Curve' component.
    """
    pts = list(curve_points)
    if closed and pts[-1] != pts[0]:
        pts.append(pts[0])   # close the loop

    # Build cumulative arc-length parameterisation
    dists = [0.0]
    for a, b in zip(pts[:-1], pts[1:]):
        d = math.sqrt((b.x - a.x)**2 + (b.y - a.y)**2 + (b.z - a.z)**2)
        dists.append(dists[-1] + d)
    total = dists[-1]

    result: List[Point3d] = []
    for k in range(count):
        t = total * k / count
        # find segment
        for idx in range(len(dists) - 1):
            if dists[idx] <= t <= dists[idx + 1]:
                seg_len = dists[idx + 1] - dists[idx]
                frac = (t - dists[idx]) / seg_len if seg_len > 0 else 0.0
                a, b = pts[idx], pts[idx + 1]
                result.append(Point3d(
                    a.x + frac * (b.x - a.x),
                    a.y + frac * (b.y - a.y),
                    a.z + frac * (b.z - a.z),
                ))
                break

    return result


# ---------------------------------------------------------------------------
# Point-in-Curve  (mirrors GH 'Point In Curve' component, 2-D)
# ---------------------------------------------------------------------------

def point_in_curve_2d(
    point: Point3d,
    curve_points: List[Point3d],
) -> bool:
    """
    2-D ray-casting containment test — mirrors GH 'Point In Curve'.
    Works on XY projection; ignores Z.
    Returns True if the point is inside the closed curve.
    """
    px, py = point.x, point.y
    pts = [Point3d(p.x, p.y, 0.0) for p in curve_points]
    if pts[0] != pts[-1]:
        pts.append(pts[0])   # ensure closed

    inside = False
    n = len(pts) - 1
    for i in range(n):
        xi, yi = pts[i].x,     pts[i].y
        xj, yj = pts[i+1].x,  pts[i+1].y
        # Standard ray-cast crossing test
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside

    return inside


def cull_cells_outside_curve(
    cells: List[Cell],
    curve_points: List[Point3d],
) -> List[Cell]:
    """
    Keep only cells whose center lies inside the curve.
    Mirrors GH Cull Pattern driven by Point In Curve results.
    """
    return [c for c in cells if point_in_curve_2d(c.center, curve_points)]


# ---------------------------------------------------------------------------
# Tween Two Planes  (mirrors Pufferfish / GH 'Tween Two Planes')
# ---------------------------------------------------------------------------

def tween_z(z_start: float, z_end: float, factor: float) -> float:
    """Linear interpolation between two Z elevations — mirrors Tween Two Planes."""
    return z_start + (z_end - z_start) * factor


# ---------------------------------------------------------------------------
# Move To Plane  (mirrors GH 'Move To Plane' component)
# ---------------------------------------------------------------------------

def move_cell_to_elevation(cell: Cell, elevation: float) -> List[Point3d]:
    """
    Translate all corners of a cell to a target Z elevation.
    Mirrors GH 'Move To Plane' (XY plane at given origin Z).
    """
    return [Point3d(p.x, p.y, elevation) for p in cell.corners]

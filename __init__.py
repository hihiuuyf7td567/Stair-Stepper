"""
stair_stepper
=============
A standalone Python module that replicates the logic of the
'Stair Stepper for Claude.ghx' Grasshopper definition.

Quick start
-----------
>>> from stair_stepper import StairStepper, StairStepperConfig, Point3d
>>> import math
>>> # Build a circle as a closed polyline
>>> pts = [Point3d(5*math.cos(a), 5*math.sin(a), 0)
...        for a in [i * 2*math.pi/64 for i in range(64)]]
>>> ss = StairStepper(StairStepperConfig(n_x=10, n_y=10, step_height=0.15))
>>> result = ss.run(pts)
>>> print(result.summary())
"""

from .core import StairStepper, StairStepperConfig, StairStepperResult
from .geometry_utils import (
    BoundingBox,
    Cell,
    Point3d,
    Rectangle2d,
    StairSurface,
    compute_bounding_box,
    cull_cells_outside_curve,
    divide_curve,
    parameter_rectangle_grid,
    parameter_series,
    point_in_curve_2d,
)

__all__ = [
    "StairStepper",
    "StairStepperConfig",
    "StairStepperResult",
    "Point3d",
    "BoundingBox",
    "Cell",
    "Rectangle2d",
    "StairSurface",
    "compute_bounding_box",
    "cull_cells_outside_curve",
    "divide_curve",
    "parameter_rectangle_grid",
    "parameter_series",
    "point_in_curve_2d",
]

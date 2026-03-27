"""
core.py
-------
StairStepper — the main class that replicates the full logic of
'Stair Stepper for Claude.ghx' as a standalone, importable Python module.

Grasshopper definition summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Input  : A closed curve in 3-D space (Rhino geometry reference)
Process:
  1. Bounding Box   → get X/Y/Z extents of the curve
  2. Rectangle      → build a flat rect from bbox X/Y at origin
  3. Parameter Rectangle Grid (Pufferfish)
                    → divide rect into n_x × n_y cells using
                      normalised parameter series
  4. Divide Curve   → sample 'curve_sample_count' pts along the curve
  5. Project        → flatten sampled pts to XY
  6. Point In Curve → test each cell centre against the projected curve
  7. Cull Pattern   → keep only cells whose centre is inside
  8. Boundary Srf   → create planar surfaces from kept cells
  9. Tween Planes + Move To Plane
                    → lift each cell to its stair-step elevation

Default slider values from the .ghx file
  n_x               = 10   (X divisions, range 0-50)
  n_y               = 22   (Y divisions, range 0-50)
  curve_sample_count= 100  (Divide Curve count, range 0-100)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .geometry_utils import (
    BoundingBox,
    Cell,
    Point3d,
    Rectangle2d,
    StairSurface,
    compute_bounding_box,
    cull_cells_outside_curve,
    divide_curve,
    move_cell_to_elevation,
    parameter_rectangle_grid,
    parameter_series,
    tween_z,
)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class StairStepperConfig:
    """
    All tunable parameters for the stair stepper.

    n_x / n_y            : number of grid divisions along X and Y
                           (mirrors the two Number Sliders, defaults from .ghx)
    curve_sample_count   : points used for point-in-curve test
                           (mirrors the third Number Slider)
    step_height          : Z increment per step.  When None (default) the
                           total bbox height is divided evenly across the
                           number of inside cells so that the last step
                           reaches bbox.size_z.
    base_elevation       : Z level of the ground floor (default 0)
    sort_steps           : if True, cells are sorted by centroid distance
                           from the curve's lowest point before stepping,
                           creating a radial stair effect; if False they
                           are ordered column-major (left-to-right,
                           bottom-to-top) as GH outputs them.
    """
    n_x: int = 10
    n_y: int = 22
    curve_sample_count: int = 100
    step_height: Optional[float] = None
    base_elevation: float = 0.0
    sort_steps: bool = False


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class StairStepperResult:
    """Returned by StairStepper.run()."""

    # All grid cells (inside + outside the curve)
    all_cells: List[Cell]

    # Only the cells inside the curve
    inside_cells: List[Cell]

    # Final stair surfaces with their elevations
    stair_surfaces: List[StairSurface]

    # Derived geometry metadata
    bounding_box: BoundingBox
    config: StairStepperConfig

    @property
    def step_count(self) -> int:
        return len(self.stair_surfaces)

    def summary(self) -> str:
        lines = [
            "StairStepper result",
            f"  Grid          : {self.config.n_x} × {self.config.n_y}",
            f"  Total cells   : {len(self.all_cells)}",
            f"  Inside cells  : {len(self.inside_cells)}",
            f"  Stair steps   : {self.step_count}",
            f"  BBox X/Y/Z    : "
            f"{self.bounding_box.size_x:.3f} / "
            f"{self.bounding_box.size_y:.3f} / "
            f"{self.bounding_box.size_z:.3f}",
        ]
        if self.stair_surfaces:
            elevs = [s.elevation for s in self.stair_surfaces]
            lines.append(
                f"  Elevations    : {min(elevs):.3f} → {max(elevs):.3f}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class StairStepper:
    """
    Converts a closed 3-D curve into a stair-step geometry.

    Usage
    -----
    >>> pts = [Point3d(x, y, z), ...]   # closed curve control points
    >>> ss = StairStepper(config=StairStepperConfig(n_x=10, n_y=22))
    >>> result = ss.run(curve_points=pts)
    >>> for srf in result.stair_surfaces:
    ...     print(srf.elevation, srf.corners)
    """

    def __init__(self, config: Optional[StairStepperConfig] = None):
        self.config = config or StairStepperConfig()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, curve_points: List[Point3d]) -> StairStepperResult:
        """
        Execute the full stair-stepper pipeline.

        Parameters
        ----------
        curve_points : list of Point3d
            Control / sample points that define the closed boundary curve.
            The curve does not need to be closed (first == last) — the
            module will close it automatically.

        Returns
        -------
        StairStepperResult
        """
        cfg = self.config

        # ── 1. Bounding Box ────────────────────────────────────────────
        bbox = compute_bounding_box(curve_points)

        # ── 2. Build flat rectangle at Z=0 matching bbox X/Y extents ──
        rect = Rectangle2d(
            origin=Point3d(bbox.min_pt.x, bbox.min_pt.y, 0.0),
            width=bbox.size_x,
            height=bbox.size_y,
        )

        # ── 3. Parameter Rectangle Grid ────────────────────────────────
        params_x = parameter_series(cfg.n_x)
        params_y = parameter_series(cfg.n_y)
        all_cells = parameter_rectangle_grid(rect, params_x, params_y)

        # ── 4 + 5. Divide Curve → Project to XY ────────────────────────
        sampled_pts = divide_curve(
            curve_points,
            count=cfg.curve_sample_count,
            closed=True,
        )
        projected_pts = [p.project_to_xy() for p in sampled_pts]

        # ── 6 + 7. Point In Curve → Cull Pattern ───────────────────────
        inside_cells = cull_cells_outside_curve(all_cells, projected_pts)

        # ── 8. Optional sort (radial from curve centroid) ──────────────
        if cfg.sort_steps:
            cx = sum(p.x for p in projected_pts) / len(projected_pts)
            cy = sum(p.y for p in projected_pts) / len(projected_pts)
            inside_cells = sorted(
                inside_cells,
                key=lambda c: math.hypot(c.center.x - cx, c.center.y - cy),
            )

        # ── 9. Stair Steps — Tween Planes + Move To Plane ──────────────
        n_steps = len(inside_cells)
        if n_steps == 0:
            return StairStepperResult(
                all_cells=all_cells,
                inside_cells=[],
                stair_surfaces=[],
                bounding_box=bbox,
                config=cfg,
            )

        # Determine step height and total rise
        z_start = cfg.base_elevation
        if cfg.step_height is not None:
            # Explicit step height: total rise = step_h × (n_steps - 1)
            z_end = cfg.base_elevation + cfg.step_height * (n_steps - 1)
        else:
            # Auto: distribute bbox Z evenly so last step reaches top
            z_end = cfg.base_elevation + bbox.size_z

        stair_surfaces: List[StairSurface] = []
        for idx, cell in enumerate(inside_cells):
            # Factor: 0 → 1 linearly across all steps
            factor = idx / (n_steps - 1) if n_steps > 1 else 0.0
            elevation = tween_z(z_start, z_end, factor)

            lifted_corners = move_cell_to_elevation(cell, elevation)
            stair_surfaces.append(
                StairSurface(
                    corners=lifted_corners,
                    elevation=elevation,
                    step_index=idx,
                )
            )

        return StairStepperResult(
            all_cells=all_cells,
            inside_cells=inside_cells,
            stair_surfaces=stair_surfaces,
            bounding_box=bbox,
            config=cfg,
        )

    # ------------------------------------------------------------------
    # Convenience: export to CSV
    # ------------------------------------------------------------------

    def export_csv(
        self,
        result: StairStepperResult,
        filepath: str,
    ) -> None:
        """
        Write stair surface corner points to a CSV file.

        Columns: step_index, elevation, corner_index, x, y, z
        """
        import csv

        with open(filepath, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["step_index", "elevation", "corner_index", "x", "y", "z"]
            )
            for srf in result.stair_surfaces:
                for ci, pt in enumerate(srf.corners):
                    writer.writerow(
                        [srf.step_index, f"{srf.elevation:.6f}",
                         ci, f"{pt.x:.6f}", f"{pt.y:.6f}", f"{pt.z:.6f}"]
                    )

    # ------------------------------------------------------------------
    # Convenience: export to OBJ (mesh quads)
    # ------------------------------------------------------------------

    def export_obj(
        self,
        result: StairStepperResult,
        filepath: str,
    ) -> None:
        """
        Write stair surfaces as quad faces to a Wavefront .obj file.
        Each stair step becomes one planar quad face.
        """
        vertices: List[Point3d] = []
        faces: List[Tuple[int, int, int, int]] = []

        for srf in result.stair_surfaces:
            base = len(vertices) + 1  # OBJ is 1-indexed
            vertices.extend(srf.corners)
            # Quad: corners 0,1,2,3 (CCW)
            faces.append((base, base + 1, base + 2, base + 3))

        with open(filepath, "w") as fh:
            fh.write("# StairStepper output\n")
            fh.write(f"# {len(result.stair_surfaces)} stair steps\n\n")
            for v in vertices:
                fh.write(f"v {v.x:.6f} {v.y:.6f} {v.z:.6f}\n")
            fh.write("\n")
            for f in faces:
                fh.write(f"f {f[0]} {f[1]} {f[2]} {f[3]}\n")

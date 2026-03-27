# stair_stepper

A standalone Python module that faithfully replicates the **Stair Stepper for Claude.ghx** Grasshopper definition — no Rhino, no Grasshopper runtime required.

## What it does

Given a closed 3-D curve (as a list of `Point3d` objects), the module:

1. Computes the curve's **bounding box** (X/Y/Z extents)
2. Builds a flat **rectangular grid** over the bounding box footprint
3. Tests each grid cell against the curve using a **point-in-polygon** check
4. Keeps only the cells that fall **inside** the curve
5. Lifts each inside cell to a progressively higher **Z elevation**, producing stair-step geometry
6. Exports to **CSV** or **OBJ** for use in any downstream tool

---

## GH → Python component map

| Grasshopper component | Python equivalent |
|---|---|
| Bounding Box | `compute_bounding_box()` |
| Deconstruct Box → Rectangle | `BoundingBox.size_x/y` → `Rectangle2d` |
| Series + Division | `parameter_series(n)` |
| Pufferfish — Parameter Rectangle Grid | `parameter_rectangle_grid()` |
| Divide Curve | `divide_curve()` |
| Project (onto XY) | `Point3d.project_to_xy()` |
| Point In Curve | `point_in_curve_2d()` |
| Cull Pattern | `cull_cells_outside_curve()` |
| Boundary Surfaces | `StairSurface.corners` (quad planar face) |
| Tween Two Planes | `tween_z()` |
| Move To Plane | `move_cell_to_elevation()` |

---

## Default parameters (from .ghx sliders)

| Parameter | Default | Range | Description |
|---|---|---|---|
| `n_x` | 10 | 0–50 | Grid divisions along X |
| `n_y` | 22 | 0–50 | Grid divisions along Y |
| `curve_sample_count` | 100 | 0–100 | Points used for containment test |
| `step_height` | `None` | any | Z per step (auto = bbox_Z / n_steps) |
| `base_elevation` | 0.0 | any | Ground floor Z |

---

## Installation

```bash
pip install numpy          # only hard dependency
# clone or copy stair_stepper/ into your project
```

---

## Quick start

```python
import math
from stair_stepper import StairStepper, StairStepperConfig, Point3d

# 1. Define your closed curve as a list of Point3d
#    Here we use a circle (r=5) at Z=0 with 64 sample points
radius = 5.0
n_pts  = 64
curve_pts = [
    Point3d(
        radius * math.cos(i * 2 * math.pi / n_pts),
        radius * math.sin(i * 2 * math.pi / n_pts),
        0.0,
    )
    for i in range(n_pts)
]

# 2. Configure (mirrors GH sliders)
config = StairStepperConfig(
    n_x=10,
    n_y=10,
    curve_sample_count=100,
    step_height=0.15,      # 150 mm per step
    base_elevation=0.0,
)

# 3. Run
ss     = StairStepper(config=config)
result = ss.run(curve_pts)

print(result.summary())
# StairStepper result
#   Grid          : 10 × 10
#   Total cells   : 100
#   Inside cells  : 76
#   Stair steps   : 76
#   BBox X/Y/Z    : 10.000 / 10.000 / 0.000
#   Elevations    : 0.000 → 0.000   (Z=0 curve → step_height lifts them)

# 4. Inspect a step
srf = result.stair_surfaces[0]
print(f"Step {srf.step_index}  Z={srf.elevation:.3f}  corners={srf.corners}")
```

---

## Export

### CSV
```python
ss.export_csv(result, "stair_steps.csv")
# Columns: step_index, elevation, corner_index, x, y, z
```

### OBJ (meshable in Blender, Rhino, etc.)
```python
ss.export_obj(result, "stair_steps.obj")
```

---

## Using with real Rhino curves

If you already have `rhino3dm` installed and want to feed a real Rhino curve:

```python
import rhino3dm
from stair_stepper import StairStepper, StairStepperConfig, Point3d

model = rhino3dm.File3dm.Read("my_model.3dm")
rhino_curve = model.Objects[0].Geometry          # assumes first obj is a curve

# Sample the curve into Point3d list
t_vals = rhino_curve.DivideByCount(200, True)
pts = [
    Point3d(*rhino_curve.PointAt(t))
    for t in t_vals
]

ss = StairStepper(StairStepperConfig(n_x=10, n_y=22, step_height=0.18))
result = ss.run(pts)
ss.export_obj(result, "stair.obj")
```

---

## Repo structure

```
stair_stepper/
├── __init__.py          # public API
├── core.py              # StairStepper class + config/result dataclasses
├── geometry_utils.py    # pure-Python geometry primitives & algorithms
├── requirements.txt
└── README.md
```

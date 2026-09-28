#!/usr/bin/env python3
"""Two declared edits to GarmentCode shirt_mean (the task-2973 shirt pattern).

1. crew neckline: front V centre raised 31.8 -> 42.0 cm (panel local y);
2. +8 cm body length: every torso-panel hem vertex moved from y=0 to y=-8.
Both edits change mirrored seam pairs identically, so every stitch keeps
matching lengths.  Then the whole pattern is lifted by --y-offset-cm to the
G9 shoulder line (G9 1.508 m vs SMPL 1.393 m acromion -> +11.5 cm).
"""
import argparse, json
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument("input", type=Path); ap.add_argument("output", type=Path)
ap.add_argument("--neck-y", type=float, default=42.0)
ap.add_argument("--extra-length-cm", type=float, default=8.0)
ap.add_argument("--y-offset-cm", type=float, default=11.5)
a = ap.parse_args()
spec = json.loads(a.input.read_text())
P = spec["pattern"]["panels"]
for name, p in P.items():
    if name.endswith("torso"):
        for v in p["vertices"]:
            if abs(v[1]) < 1e-6:
                v[1] = -a.extra_length_cm
    if name.endswith("ftorso"):
        for v in p["vertices"]:
            if abs(v[0]) < 1e-6 and abs(v[1] - 31.8) < 0.05:
                v[1] = a.neck_y
    p["translation"][1] += a.y_offset_cm
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(spec, indent=2) + "\n")
print("EDITED", a.output)

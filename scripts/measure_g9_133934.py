"""Measure the G9 GarmentCode collider (amy_gp_v3) into GarmentCode body params.

task-133934 (dressable-g9 step 15, operator decision #1988251).  The existing
assets/bodies/g9_amy_gp_v3.yaml is the SMPL-average file with height edited to
172; parametric trousers need the real G9 levels/circumferences.  Tape-measure
circumferences = convex-hull perimeter of a 1 cm band of body(+leg) vertices,
arms excluded by the bone-weight segmentation.  Frame: GC metres, +Y up.
"""
import json, sys
import numpy as np
from scipy.spatial import ConvexHull
import yaml

obj, seg_path, base_yaml, out_yaml = sys.argv[1:5]
V = np.array([[float(t) for t in l.split()[1:4]] for l in open(obj) if l.startswith("v ")]) * 100.0
seg = json.load(open(seg_path))
lab = np.full(len(V), "body", dtype=object)
for k, ids in seg.items():
    lab[ids] = k
# Fix the task-133870 segmentation: its ARM regex ^(l|r)_(index|mid|ring|pinky)
# also matches the toe bones l_indextoe/l_midtoe/..., so toe vertices were
# labelled as arms.  Relabel arm-labelled vertices below 60 cm as legs.
for side in ("left", "right"):
    ids = [i for i in seg[side + "_arm"] if V[i, 1] < 60.0]
    seg[side + "_arm"] = [i for i in seg[side + "_arm"] if V[i, 1] >= 60.0]
    seg[side + "_leg"] = seg[side + "_leg"] + ids
    lab[ids] = side + "_leg"
if len(sys.argv) > 5:
    json.dump(seg, open(sys.argv[5], "w"))
floor = V[:, 1].min()
V[:, 1] -= floor
H = V[:, 1].max()
torso = lab == "body"
legs = (lab == "left_leg") | (lab == "right_leg")
noarm = torso | legs


def circ(y, mask, band=0.6, xs=None):
    m = mask & (np.abs(V[:, 1] - y) < band)
    P = V[m][:, [0, 2]]
    if xs is not None:
        P = P[xs(P)]
    if len(P) < 8:
        return 0.0
    h = ConvexHull(P)
    return float(h.area)  # 2D hull "area" attribute is the perimeter


ys = np.arange(0.40 * H, 0.80 * H, 0.5)
# waist: narrowest torso level in 58-68% H
wy = min((y for y in ys if 0.58 * H <= y <= 0.68 * H), key=lambda y: circ(y, torso))
# hips: widest torso+legs level in 45-56% H
hy = max((y for y in ys if 0.45 * H <= y <= 0.56 * H), key=lambda y: circ(y, noarm))
# bust: widest torso level in 70-78% H
by = max((y for y in ys if 0.70 * H <= y <= 0.78 * H), key=lambda y: circ(y, torso))
# crotch: highest level where no non-arm vertex lies within |x|<1.2 cm
cy = None
for y in np.arange(hy, 0.30 * H, -0.25):
    m = noarm & (np.abs(V[:, 1] - y) < 0.25)
    if m.sum() and not np.any(np.abs(V[m][:, 0]) < 1.2):
        cy = float(y)
        break
leg_y = cy - 3.0
leg_c = circ(leg_y, lab == "left_leg")
# arms: angle below horizontal of the left arm's principal axis
A = V[lab == "left_arm"]
c = A - A.mean(0)
d = np.linalg.svd(c, full_matrices=False)[2][0]
arm_angle = float(np.degrees(np.arcsin(abs(d[1]) / np.linalg.norm(d))))
arm_len = float(b_arm_scale := 0)
# shoulder/nape: top of the arm segmentation ~ acromion
acromion = float(A[:, 1].max())
nape = acromion + 0.7  # SMPL-A40 relation (nape ~ acromion + 0.7 cm)
top_shoulder = circ(acromion - 2.0, torso)

base = yaml.safe_load(open(base_yaml))
b = base["body"]
s = H / b["height"]
bust = circ(by, torso)
ub = circ(by - 9.0, torso)
waist = circ(wy, torso)
hips = circ(hy, noarm)
new = dict(b)
new["arm_length"] = round(b["arm_length"] * s, 1)
for k in ("neck_w", "shoulder_w", "armscye_depth", "wrist", "bust_line",
          "waist_over_bust_line", "bust_points", "bum_points"):
    new[k] = round(b[k] * s, 1)
new.update({
    "height": round(H, 1),
    "head_l": round(H - nape, 1),
    "arm_pose_angle": round(arm_angle, 1),
    "waist": round(waist, 1),
    "waist_line": round(nape - wy, 1),
    "bust": round(bust, 1),
    "underbust": round(ub, 1),
    "hips": round(hips, 1),
    "hips_line": round(wy - hy, 1),
    "crotch_hip_diff": round(hy - cy, 1),
    "leg_circ": round(leg_c, 1),
    # widths scale with the measured girths, not with height
    "waist_back_width": round(b["waist_back_width"] * waist / b["waist"], 1),
    "back_width": round(b["back_width"] * bust / b["bust"], 1),
    "hip_back_width": round(b["hip_back_width"] * hips / b["hips"], 1),
})
new = {k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in new.items()}
yaml.safe_dump({"body": new}, open(out_yaml, "w"), sort_keys=False)
print("G9_MEASURED", json.dumps({"height": H, "floor_m": floor / 100, "levels_cm": {
    "waist": wy, "hips": hy, "bust": by, "crotch": cy, "acromion": acromion},
    "body": new}, default=float))

"""Generic, garment-agnostic fabric atlas (dressable-g9 s16, task 142131).

Same pattern-UV rasterisation as the step-15 garment_textures.py (panel id +
3D rest position per texel), but every garment-specific choice comes from a
STYLE JSON, not from code:

  {"kind": "skirt", "base_rgb": [r,g,b], "heather": 0.06, "fade": 0.05,
   "weave": "twill"|"plain"|"knit", "weave_mm": 8.0, "roughness": 0.8,
   "normal_strength": 0.35, "sheen": 0.1,
   "topstitch": {"rgb": [...], "at_mm": [3.0], "width_mm": 0.7, "dash_mm": 2.6},
   "closures": [{"type": "zip", "panels": "ftorso", "rgb": [...], "tape_mm": 9,
                 "teeth_mm": 4, "pull_z_from_top_m": 0.03}],
   "rib_hems": {"panels": "sleeve", "band_mm": 0, "rgb": [...]} }

gcenv python fabric_textures.py --obj X_sim.obj --style style.json --lift-m 0.054874 --out DIR
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("--obj", required=True)
ap.add_argument("--style", required=True)
ap.add_argument("--lift-m", type=float, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--res", type=int, default=4096)
ap.add_argument("--seed", type=int, default=142131)
a = ap.parse_args()
S = json.loads(Path(a.style).read_text())
KIND = S["kind"]
rng = np.random.default_rng(a.seed)
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
obj = Path(a.obj)
labels = [l.strip() for l in (obj.parent / (obj.stem + "_segmentation.txt")).read_text().splitlines()]

V, VT, F, FT = [], [], [], []
for ln in obj.read_text().splitlines():
    if ln.startswith("v "):
        x, y, z = map(float, ln.split()[1:4])
        V.append((x / 100.0, -z / 100.0, y / 100.0 - a.lift_m))
    elif ln.startswith("vt "):
        VT.append(tuple(map(float, ln.split()[1:3])))
    elif ln.startswith("f "):
        t = ln.split()[1:]
        F.append([int(s.split("/")[0]) - 1 for s in t])
        FT.append([int(s.split("/")[1]) - 1 for s in t])
V, VT = np.array(V), np.array(VT)
panels = sorted({l for l in labels if not l.startswith("stitch")})
pid = {p: i + 1 for i, p in enumerate(panels)}


def face_panel(f):
    ls = [labels[i] for i in f if not labels[i].startswith("stitch")]
    return pid[max(set(ls), key=ls.count)] if ls else 0


R = a.res
PAN = np.zeros((R, R), np.int16)
POS = np.zeros((R, R, 3), np.float32)
tris = []
for f, ft in zip(F, FT):
    for k in range(1, len(f) - 1):
        tris.append(((f[0], f[k], f[k + 1]), (ft[0], ft[k], ft[k + 1]), face_panel(f)))
# mm per UV unit (pattern is flat: one global scale)
ratios = []
for (vi, ti, _) in tris[:: max(1, len(tris) // 4000)]:
    for i in range(3):
        a3 = np.linalg.norm(V[vi[i]] - V[vi[(i + 1) % 3]])
        a2 = np.linalg.norm(VT[ti[i]] - VT[ti[(i + 1) % 3]])
        if a2 > 1e-9:
            ratios.append(a3 / a2)
mm_per_uv = float(np.median(ratios)) * 1000.0
mm_px = mm_per_uv / R
print("SCALE mm_per_uv", round(mm_per_uv, 1), "mm_per_px", round(mm_px, 3), flush=True)

for (vi, ti, p) in tris:
    uv = VT[list(ti)] * R
    px = np.stack([uv[:, 0], R - uv[:, 1]], 1)  # image x, y
    x0, y0 = np.floor(px.min(0)).astype(int) - 1
    x1, y1 = np.ceil(px.max(0)).astype(int) + 1
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, R - 1), min(y1, R - 1)
    if x1 < x0 or y1 < y0:
        continue
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    (ax, ay), (bx, by), (cx, cy) = px
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(den) < 1e-12:
        continue
    l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
    l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
    l3 = 1 - l1 - l2
    m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
    if not m.any():
        continue
    P3 = V[list(vi)]
    pos = l1[..., None] * P3[0] + l2[..., None] * P3[1] + l3[..., None] * P3[2]
    sub = PAN[y0:y1 + 1, x0:x1 + 1]
    sub[m] = p
    POS[y0:y1 + 1, x0:x1 + 1][m] = pos[m]

inside = PAN > 0
# distance (mm) to the panel edge, inside each panel
edge = np.zeros((R, R), np.float32)
for p in range(1, len(panels) + 1):
    m = PAN == p
    if m.any():
        d = ndimage.distance_transform_edt(m)
        edge[m] = d[m]
edge *= mm_px
gy_, gx_ = np.gradient(ndimage.gaussian_filter(edge, 2.0))
tn = np.hypot(gx_, gy_) + 1e-9
tx, ty = -gy_ / tn, gx_ / tn  # edge tangent
YY, XX = np.mgrid[0:R, 0:R].astype(np.float32)
s_along = (XX * tx + YY * ty) * mm_px  # arc length along the edge (mm)


def dashed_line(dist_mm, at_mm, width_mm=0.9, dash_mm=3.2, s=None):
    s = s_along if s is None else s
    core = np.clip(1.0 - np.abs(dist_mm - at_mm) / (width_mm / 2), 0, 1)
    dash = ((s / dash_mm) % 1.0) < 0.72
    return core * dash


def lerp(img, col, w):
    col = np.array(col, np.float32) / 255.0
    return img * (1 - w[..., None]) + col * w[..., None]


def vnoise3(P, cell, seed):
    """trilinear value noise sampled at 3D rest positions (m); cell in m
    (scalar or (x, y, z)) -- a SOLID texture, so it does not stretch when the
    tight fit compresses the pattern against its UVs"""
    c = np.asarray(cell, np.float64)
    Q = P.astype(np.float64) / c
    I = np.floor(Q).astype(np.int64)
    F = (Q - I).astype(np.float32)
    F = F * F * (3 - 2 * F)

    def h(ix, iy, iz):
        v = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        v = (v ^ (v >> 13)) * 1274126177
        return ((v ^ (v >> 16)) & 0xFFFF).astype(np.float32) / 65535.0

    out = np.zeros(len(P), np.float32)
    for dx in (0, 1):
        wx = F[:, 0] if dx else 1 - F[:, 0]
        for dy in (0, 1):
            wy = F[:, 1] if dy else 1 - F[:, 1]
            for dz in (0, 1):
                wz = F[:, 2] if dz else 1 - F[:, 2]
                out += wx * wy * wz * h(I[:, 0] + dx, I[:, 1] + dy, I[:, 2] + dz)
    return out * 2 - 1


def fbm(shape, scales, amps):
    acc = np.zeros(shape, np.float32)
    for sc, am in zip(scales, amps):
        n = rng.standard_normal(shape).astype(np.float32)
        acc += am * ndimage.gaussian_filter(n, sc)
    return acc / (np.abs(acc).max() + 1e-9)



X3, Y3, Z3 = POS[..., 0], POS[..., 1], POS[..., 2]
names = {p: panels[p - 1] for p in range(1, len(panels) + 1)}


def panels_matching(rx):
    return np.isin(PAN, [p for p, n in names.items() if re.search(rx, n)])


details = {}
base = np.array(S["base_rgb"], np.float32) / 255.0
img = np.ones((R, R, 3), np.float32) * base
Pin = POS[inside]
h3 = vnoise3(Pin, 0.0009, 11) * 0.6 + vnoise3(Pin, 0.003, 12) * 0.4
f3 = vnoise3(Pin, 0.06, 14) * 0.6 + vnoise3(Pin, 0.15, 15) * 0.4
lum = np.ones((R, R), np.float32)
lum[inside] += S.get("heather", 0.05) * h3 + S.get("fade", 0.05) * f3
img = np.clip(img * lum[..., None], 0, 1)
ts = S.get("topstitch")
if ts:
    w = np.zeros((R, R), np.float32)
    for at in ts.get("at_mm", [3.0]):
        w = np.maximum(w, dashed_line(edge, at, width_mm=ts.get("width_mm", 0.7), dash_mm=ts.get("dash_mm", 2.6)))
    img = lerp(img, ts["rgb"], w * inside)
for c in S.get("closures", []):
    if c["type"] != "zip":
        continue
    m = panels_matching(c["panels"]) & (Y3 < 0)
    if not m.any():
        continue
    # centre-front closure: the zip runs along the seam the matching panels
    # share at x = 0 (the garment's symmetry plane), from its top to its hem
    d = np.abs(X3[m]) * 1000.0
    zt, zb = float(Z3[m].max()), float(Z3[m].min())
    tape = np.clip(1 - (d - c.get("tape_mm", 9) / 2) / 0.6, 0, 1)
    teeth_on = np.clip(1 - (d - c.get("teeth_mm", 4) / 2) / 0.4, 0, 1)
    teeth = teeth_on * (((Z3[m] * 1000.0) / 2.2) % 1.0 < 0.55)
    sub = img[m] * (1 - tape[:, None]) + np.array(c["rgb"], np.float32) / 255 * tape[:, None]
    sub = sub * (1 - 0.45 * teeth[:, None]) + np.array([200, 200, 205], np.float32) / 255 * 0.45 * teeth[:, None]
    pz = zt - c.get("pull_z_from_top_m", 0.03)
    pull = np.clip(1 - (np.hypot((X3[m] + 0.006) / 0.6, (Z3[m] - (pz - 0.012)) / 1.0) * 1000 - 9) / 0.7, 0, 1)
    sub = sub * (1 - pull[:, None]) + np.array([185, 188, 195], np.float32) / 255 * pull[:, None]
    img[m] = sub
    details.setdefault("zips", []).append({"panels": c["panels"], "z_top": round(zt, 3), "z_bottom": round(zb, 3)})
rb = S.get("rib_hems")
if rb:
    m = panels_matching(rb["panels"]) & (edge < rb.get("band_mm", 40))
    ribs = 0.5 + 0.5 * np.sin(2 * np.pi * s_along / 2.5)
    img[m] = img[m] * (1 - 0.12 * ribs[m][:, None])
    details["rib_hems"] = rb["panels"]

img_out = img.copy()
if (~inside).any():
    idx = ndimage.distance_transform_edt(~inside, return_distances=False, return_indices=True)
    img_out = img[idx[0], idx[1]]
Image.fromarray((np.clip(img_out, 0, 1) * 255).astype(np.uint8)).save(out / f"{KIND}_basecolor.png", optimize=True)

T = 512
yy, xx = np.mgrid[0:T, 0:T].astype(np.float32)
weave = S.get("weave", "plain")
if weave == "twill":
    h = (0.5 + 0.5 * np.sin(2 * np.pi * (xx + yy) / (T / 8))) ** 1.5
elif weave == "knit":
    # jersey/fleece knit: columns of V-loops (wales)
    h = np.abs(np.sin(np.pi * xx / (T / 16))) * (0.6 + 0.4 * np.sin(2 * np.pi * (yy + 0.5 * np.abs(((xx / (T / 16)) % 2) - 1) * T / 32) / (T / 24)))
else:
    per = T / 24
    h = (np.sin(2 * np.pi * xx / per) * np.sin(2 * np.pi * yy / per)) * 0.5 + 0.5
strength = S.get("weave_relief", 1.4)
gy2, gx2 = np.gradient(ndimage.gaussian_filter(h, 0.8, mode="wrap"))
n = np.stack([-gx2 * strength, -gy2 * strength, np.ones_like(h)], -1)
n /= np.linalg.norm(n, axis=-1, keepdims=True)
Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(out / f"{KIND}_weave_normal.png")
meta = {"kind": KIND, "obj": str(obj), "style": S, "res": R, "mm_per_uv": mm_per_uv, "mm_per_px": mm_px,
        "weave_tile_mm": S.get("weave_mm", 6.0), "weave_uv_scale": mm_per_uv / S.get("weave_mm", 6.0),
        "roughness": S.get("roughness", 0.8), "normal_strength": S.get("normal_strength", 0.3),
        "sheen": S.get("sheen", 0.1), "display_rgb": S["base_rgb"], "panels": panels, "details": details}
(out / f"{KIND}_textures.json").write_text(json.dumps(meta, indent=2))
print("TEXTURES", json.dumps({k: meta[k] for k in ("kind", "mm_per_uv", "weave_uv_scale", "details")}), flush=True)

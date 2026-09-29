"""task-134122: fabric textures for the dressable-g9 70s outfit from the
GarmentCode pattern UVs (operator decision #1994543: "jeans ... should read
as textured denim").

Inputs are the retargeted sim OBJs (a08 frame via the GC->Blender transform)
whose vt layout is the flattened sewing pattern, plus the per-vertex panel
segmentation.  Every atlas pixel is rasterised with its panel id and its 3D
rest position, so construction details are placed on the BODY (back patch
pockets over the seat, J-stitch fly, scoop front pockets, button stand) and
topstitching follows the real panel seams in the pattern layout.

Outputs per garment: <kind>_basecolor.png (atlas, sRGB), and one tiled
<kind>_weave_normal.png (tangent-space) + <kind>_textures.json with the
mm-per-UV scale the material needs to tile the weave at true size.

gcenv python garment_textures.py --obj rt4/bellbottom_jeans_sim.obj --kind pants --lift-m 0.054874 --out DIR
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("--obj", required=True)
ap.add_argument("--kind", required=True, choices=["pants", "shirt"])
ap.add_argument("--lift-m", type=float, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--res", type=int, default=4096)
ap.add_argument("--seed", type=int, default=134122)
a = ap.parse_args()
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
details = {}
if a.kind == "pants":
    base = np.array([34, 52, 92], np.float32) / 255.0  # rinsed indigo
    img = np.ones((R, R, 3), np.float32) * base
    # warp slub: streaks along the grain (pattern V ~ leg length) + heather
    # solid (3D) yarn texture evaluated at each texel's rest position:
    # warp slub elongated along the leg (z), white weft speckle, broad fade
    Pin = POS[inside]
    slub3 = vnoise3(Pin, (0.0007, 0.0007, 0.005), 11) * 0.6 + vnoise3(Pin, (0.0015, 0.0015, 0.012), 12) * 0.4
    weft3 = vnoise3(Pin, 0.00045, 13)
    fade3 = vnoise3(Pin, 0.05, 14) * 0.6 + vnoise3(Pin, 0.14, 15) * 0.4
    slub = np.zeros((R, R), np.float32); slub[inside] = slub3
    weft = np.zeros((R, R), np.float32); weft[inside] = weft3
    fade = np.zeros((R, R), np.float32); fade[inside] = fade3
    lum = 1.0 + 0.10 * slub + 0.07 * fade
    img = np.ones((R, R, 3), np.float32) * base
    white = np.array([0.80, 0.82, 0.86], np.float32)
    wmix = np.clip(0.12 + 0.10 * weft, 0, 0.3)
    # wear: lighter over the front thighs and the seat, rope-fade at seams
    front = np.clip(-Y3 / 0.06, 0, 1) * (1 - np.clip(np.abs(Z3 - 0.72) / 0.18, 0, 1))
    seat = np.clip(Y3 / 0.06, 0, 1) * (1 - np.clip(np.abs(Z3 - 0.88) / 0.10, 0, 1))
    rope = np.clip(1 - np.abs(edge - 3.0) / 3.0, 0, 1) * (0.5 + 0.5 * ((s_along / 9.0) % 1.0 < 0.5))
    lum += 0.05 * front + 0.05 * seat + 0.12 * rope
    wmix = wmix + 0.03 * front + 0.03 * seat + 0.07 * rope
    img = img * (1 - wmix[..., None]) + white * wmix[..., None]
    img = np.clip(img * lum[..., None], 0, 1)
    gold = (196, 138, 52)
    # topstitching: double needle along every seam, single along hems
    stitch = np.maximum(dashed_line(edge, 2.2), dashed_line(edge, 8.0))
    names = {p: panels[p - 1] for p in range(1, len(panels) + 1)}
    wb = np.isin(PAN, [p for p, n in names.items() if n.startswith("wb")])
    stitch = np.where(wb, np.maximum(dashed_line(edge, 2.2), dashed_line(edge, 10.0)), stitch)
    img = lerp(img, gold, stitch * inside)
    # waistband top edge: darker fold line
    back = np.isin(PAN, [p for p, n in names.items() if n.startswith("pant_b")])
    frontp = np.isin(PAN, [p for p, n in names.items() if n.startswith("pant_f")])
    zmax_legs = float(Z3[back | frontp].max())
    # back patch pockets (pentagon, projected on the body's XZ plane)
    for side in (1, -1):
        m = back & (np.sign(X3) == side)
        cx = side * 0.075
        ztop = zmax_legs - 0.025
        W, H, Hs = 0.130, 0.140, 0.115
        poly = np.array([(cx - W / 2, ztop), (cx + W / 2, ztop), (cx + W / 2 - 0.006, ztop - Hs),
                         (cx, ztop - H), (cx - W / 2 + 0.006, ztop - Hs)])
        px_, pz_ = X3[m], Z3[m]
        dmin = np.full(px_.shape, 1e9, np.float32)
        for i in range(len(poly)):
            p0, p1 = poly[i], poly[(i + 1) % len(poly)]
            d = p1 - p0
            t = np.clip(((px_ - p0[0]) * d[0] + (pz_ - p0[1]) * d[1]) / (d @ d), 0, 1)
            dmin = np.minimum(dmin, np.hypot(px_ - (p0[0] + t * d[0]), pz_ - (p0[1] + t * d[1])))
        # inside test (convex): all cross products same sign
        ins = np.ones(px_.shape, bool)
        for i in range(len(poly)):
            p0, p1 = poly[i], poly[(i + 1) % len(poly)]
            ins &= ((p1[0] - p0[0]) * (pz_ - p0[1]) - (p1[1] - p0[1]) * (px_ - p0[0])) <= 0
        dmm = dmin * 1000.0
        s3 = (px_ + pz_) * 1000.0
        w = np.zeros(px_.shape, np.float32)
        w = np.maximum(w, dashed_line(dmm, 2.0, s=np.abs(px_ - cx) * 1000 + pz_ * 1000) * ins)
        w = np.maximum(w, dashed_line(dmm, 7.0, s=np.abs(px_ - cx) * 1000 + pz_ * 1000) * ins)
        edge_dark = np.clip(1 - dmm / 1.2, 0, 1)
        shade = np.where(ins, 0.97, 1.0) * (1 - 0.35 * edge_dark)
        sub = img[m] * shade[:, None]
        g = np.array(gold, np.float32) / 255
        sub = sub * (1 - w[:, None]) + g * w[:, None]
        # decorative double arc stitch (the 70s "wing" on the pocket)
        u = (px_ - cx) / (W / 2)
        arc = ztop - 0.055 - 0.028 * (1 - u ** 2)
        wa = np.clip(1 - np.abs((pz_ - arc) * 1000) / 0.5, 0, 1) * ins * (np.abs(u) < 0.9) * \
            (((np.abs(px_ - cx) * 1000 / 3.2) % 1.0) < 0.72)
        sub = sub * (1 - wa[:, None]) + g * wa[:, None]
        img[m] = sub
        # rivets at the pocket's top corners
        for rx in (cx - W / 2 + 0.004, cx + W / 2 - 0.004):
            rd = np.hypot(X3[m] - rx, Z3[m] - (ztop - 0.004)) * 1000
            rv = np.clip(1 - (rd - 2.0) / 0.6, 0, 1)
            img[m] = img[m] * (1 - rv[:, None]) + np.array([150, 95, 50], np.float32) / 255 * rv[:, None]
        details[f"back_pocket_{'l' if side > 0 else 'r'}"] = poly.round(4).tolist()
    # J-stitch fly on the wearer's left front, scoop pockets both fronts
    m = frontp & (X3 > 0)
    zc = zmax_legs - 0.15
    ax_, az_ = np.abs(X3[m]), Z3[m]
    r = np.where(az_ >= zc, ax_, np.hypot(ax_, np.minimum(az_ - zc, 0)))
    wj = np.maximum(dashed_line(r * 1000, 32.0, s=az_ * 1000), dashed_line(r * 1000, 38.0, s=az_ * 1000)) * (az_ > zc - 0.035)
    img[m] = img[m] * (1 - wj[:, None]) + np.array(gold, np.float32) / 255 * wj[:, None]
    for side in (1, -1):
        m = frontp & (np.sign(X3) == side)
        ax_, az_ = np.abs(X3[m]), Z3[m]
        # quarter-ellipse from the waist (|x|=0.075) to the side (z=top-0.085)
        e = np.hypot((ax_ - 0.16) / 0.085, (az_ - zmax_legs) / 0.085)
        on = (ax_ < 0.16) & (az_ < zmax_legs)
        emm = (e - 1.0) * 85.0
        wp = np.maximum(dashed_line(emm, 0.0, s=az_ * 1000 - ax_ * 1000),
                        dashed_line(emm, 5.5, s=az_ * 1000 - ax_ * 1000)) * on
        dark = np.clip(1 - np.abs(emm + 1.5) / 1.0, 0, 1) * on
        sub = img[m] * (1 - 0.35 * dark[:, None])
        img[m] = sub * (1 - wp[:, None]) + np.array(gold, np.float32) / 255 * wp[:, None]
    # waist button + copper rivets at the front pocket mouths
    m = frontp | wb
    for (bx, bz, rad, col) in [(0.0, zmax_legs + 0.02, 7.0, (170, 150, 120))] + \
            [(s * 0.155, zmax_legs - 0.004, 2.2, (150, 95, 50)) for s in (1, -1)]:
        rd = np.hypot(X3[m] - bx, Z3[m] - bz) * 1000 * (Y3[m] < 0.02)
        rv = np.clip(1 - (rd - rad) / 0.7, 0, 1) * (Y3[m] < 0.02)
        img[m] = img[m] * (1 - rv[:, None]) + np.array(col, np.float32) / 255 * rv[:, None]
    weave_mm, rough = 14.0, 0.82
else:
    base = np.array([196, 142, 38], np.float32) / 255.0  # mustard
    img = np.ones((R, R, 3), np.float32) * base
    heather = ndimage.gaussian_filter(rng.standard_normal((R, R)).astype(np.float32), 0.8)
    heather /= np.abs(heather).max() + 1e-9
    fade = fbm((R, R), (80, 240), (0.6, 1.0))
    img = np.clip(img * (1 + 0.06 * heather + 0.06 * fade)[..., None], 0, 1)
    tone = (150, 104, 22)
    img = lerp(img, tone, dashed_line(edge, 3.0, width_mm=0.7, dash_mm=2.5) * inside)
    names = {p: panels[p - 1] for p in range(1, len(panels) + 1)}
    col = np.isin(PAN, [p for p, n in names.items() if "collar" in n])
    img = lerp(img, tone, dashed_line(edge, 6.0, width_mm=0.7, dash_mm=2.5) * col)
    # buttons down the centre front below the V
    ft = np.isin(PAN, [p for p, n in names.items() if "ftorso" in n])
    zv = float(Z3[col & (Y3 < 0)].min()) if (col & (Y3 < 0)).any() else 1.25
    zlow = float(Z3[ft].min())
    zs = np.arange(zv - 0.03, zlow + 0.04, -0.085)
    m = ft
    for bz in zs:
        rd = np.hypot(X3[m] - 0.0, Z3[m] - bz) * 1000
        disc = np.clip(1 - (rd - 5.5) / 0.6, 0, 1) * (Y3[m] < 0)
        ring = np.clip(1 - np.abs(rd - 5.5) / 0.6, 0, 1) * (Y3[m] < 0)
        holes = sum(np.clip(1 - (np.hypot(X3[m] - dx, Z3[m] - bz - dz) * 1000 - 0.7) / 0.4, 0, 1)
                    for dx, dz in ((0.0014, 0.0014), (-0.0014, 0.0014), (0.0014, -0.0014), (-0.0014, -0.0014)))
        holes = holes * (Y3[m] < 0)
        sub = img[m] * (1 - disc[:, None]) + np.array([236, 224, 196], np.float32) / 255 * disc[:, None]
        sub = sub * (1 - 0.35 * ring[:, None]) * (1 - 0.6 * holes[:, None])
        img[m] = sub
    details["buttons_z"] = [round(float(z), 3) for z in zs]
    # placket: a darker fold 18 mm right of centre front
    pl = ft & (Y3 < 0)
    dpl = np.abs(X3[pl] + 0.018) * 1000
    img[pl] = img[pl] * (1 - 0.18 * np.clip(1 - dpl / 1.0, 0, 1))[:, None]
    weave_mm, rough = 6.0, 0.7

# bleed the atlas outward so mip-maps do not pull in the background
img_out = img.copy()
if (~inside).any():
    idx = ndimage.distance_transform_edt(~inside, return_distances=False, return_indices=True)
    img_out = img[idx[0], idx[1]]
Image.fromarray((np.clip(img_out, 0, 1) * 255).astype(np.uint8)).save(out / f"{a.kind}_basecolor.png", optimize=True)

# tiled weave normal map (512 px tile = weave_mm)
T = 512
yy, xx = np.mgrid[0:T, 0:T].astype(np.float32)
if a.kind == "pants":
    # 3/1 right-hand twill: diagonal ribs + warp slub
    per = T / 8
    h = 0.5 + 0.5 * np.sin(2 * np.pi * (xx + yy) / per)
    h = h ** 1.5
    h += 0.25 * np.sin(2 * np.pi * xx / (T / 32)) * 0.5
    slubt = ndimage.gaussian_filter(np.random.default_rng(7).standard_normal((T, T)), (6, 1.0), mode="wrap")
    h += 0.12 * slubt / (np.abs(slubt).max() + 1e-9)
    strength = 2.0
else:
    per = T / 24
    h = (np.sin(2 * np.pi * xx / per) * np.sin(2 * np.pi * yy / per)) * 0.5 + 0.5
    strength = 1.2
gy2, gx2 = np.gradient(ndimage.gaussian_filter(h, 0.8, mode="wrap"))
n = np.stack([-gx2 * strength, -gy2 * strength, np.ones_like(h)], -1)
n /= np.linalg.norm(n, axis=-1, keepdims=True)
Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(out / f"{a.kind}_weave_normal.png")
meta = {"kind": a.kind, "obj": str(obj), "res": R, "mm_per_uv": mm_per_uv, "mm_per_px": mm_px,
        "weave_tile_mm": weave_mm, "weave_uv_scale": mm_per_uv / weave_mm, "roughness": rough,
        "panels": panels, "details": details}
(out / f"{a.kind}_textures.json").write_text(json.dumps(meta, indent=2))
print("TEXTURES", json.dumps({k: meta[k] for k in ("kind", "mm_per_uv", "weave_uv_scale")}), flush=True)

"""glb_webfix.py IN.glb OUT.glb [opts] -- chat-view (three.js) calibration of the Amy web GLB (step 51 r3, task 133039).

The Cycles master renders the skin with SSS (weight 0.5, warm radius) under a bright studio; the chat three.js rig
(s53_shots.html / live_alive.html: hemisphere 1.1 + key 1.6 + fill 0.6 + rim 0.5, no env, no tone map) shows the
raw albedo: darker, more orange, and the freckle stamps read as hard dark blotches. This rewrites the skin
base-colour images (amy_{head,body,arms,legs}_D) only:
  --freckle-soft S   compress negative local-contrast (lin - gaussblur_R) by S (0..1)   [SSS stand-in]
  --freckle-r R      blur radius in px at the image's own resolution (default 10 at 4k)
  --skin-gain r,g,b  linear per-channel gain (calibrated against the Cycles stills)
  --skin-rough x     roughnessFactor for the skin materials (exported 0.0)
  --scalp r,g,b      AmyScalpShellMat baseColorFactor (linear)
  --card-mat NAME    card material name (default AmyWaveCardMat) ; --card-factor r,g,b  baseColorFactor multiplier
"""
import io, json, struct, sys
import numpy as np
import cv2
from PIL import Image, ImageFilter
a = sys.argv[1:]
src, dst = a[0], a[1]
def opt(n, d=None):
    return a[a.index(n) + 1] if n in a else d
def vec(s):
    return [float(x) for x in s.split(",")] if s else None
SOFT = float(opt("--freckle-soft", "0"))
FR = float(opt("--freckle-r", "10"))
GAIN = np.array(vec(opt("--skin-gain", "1,1,1")))
HGAIN = np.array(vec(opt("--head-gain")) or GAIN)
ROUGH = opt("--skin-rough")
SCALP = vec(opt("--scalp"))
CARD = opt("--card-mat", "AmyWaveCardMat")
CARDF = vec(opt("--card-factor"))
CUT = opt("--card-cutoff")
SKIN_IMG = ("amy_head_D", "amy_body_D", "amy_arms_D", "amy_legs_D")
SKIN_MAT = ("Head-2", "Body-2", "Arms-2", "Legs-2")

def s2l(c): return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def l2s(c):
    c = np.clip(c, 0, 1); return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)

b = open(src, "rb").read()
magic, ver, _ = struct.unpack("<III", b[:12])
jl, jt = struct.unpack("<II", b[12:20])
g = json.loads(b[20:20 + jl])
p = 20 + jl
bl, bt = struct.unpack("<II", b[p:p + 8])
BIN = b[p + 8:p + 8 + bl]
views = [bytes(BIN[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]) for v in g["bufferViews"]]
rep = []
for im in g["images"]:
    if im.get("name") not in SKIN_IMG:
        continue
    raw = Image.open(io.BytesIO(views[im["bufferView"]])).convert("RGB")
    x = np.asarray(raw).astype(np.float32) / 255.0
    lin = s2l(x)
    if SOFT > 0:
        r = FR * raw.width / 4096.0
        bl_ = cv2.GaussianBlur(lin.astype(np.float32), (0, 0), r)
        # luminance-based deviation so hue of the freckle is kept; only darker-than-local texels are lifted
        Y = lin @ [0.2126, 0.7152, 0.0722]; Yb = bl_ @ [0.2126, 0.7152, 0.0722]
        ratio = np.where(Y < Yb, (Yb / np.maximum(Y, 1e-4)) ** SOFT, 1.0)
        lin = lin * ratio[..., None]
    lin = lin * (HGAIN if im["name"] == "amy_head_D" else GAIN)
    clip = float((lin.max(-1) > 1.0).mean())
    K = 0.75
    lin = np.where(lin > K, K + (1 - K) * np.tanh((lin - K) / (1 - K)), lin)   # soft knee instead of hard clip
    out = Image.fromarray((l2s(lin) * 255 + 0.5).astype(np.uint8))
    buf = io.BytesIO(); out.save(buf, "JPEG", quality=93)
    views[im["bufferView"]] = buf.getvalue()
    rep.append((im["name"], raw.size, round(clip, 4)))
for m in g["materials"]:
    if m["name"] in SKIN_MAT and ROUGH is not None:
        m["pbrMetallicRoughness"]["roughnessFactor"] = float(ROUGH)
    if m["name"] == "AmyScalpShellMat" and SCALP:
        m["pbrMetallicRoughness"]["baseColorFactor"] = SCALP + [1.0]
    if m["name"] == CARD and CUT:
        m["alphaMode"] = "MASK"; m["alphaCutoff"] = float(CUT)
    if m["name"] == CARD and CARDF:
        f = m["pbrMetallicRoughness"].get("baseColorFactor", [1, 1, 1, 1])
        m["pbrMetallicRoughness"]["baseColorFactor"] = [f[0] * CARDF[0], f[1] * CARDF[1], f[2] * CARDF[2], f[3]]
# relayout
nb = bytearray()
for v, data in zip(g["bufferViews"], views):
    while len(nb) % 4: nb.append(0)
    v["byteOffset"] = len(nb); v["byteLength"] = len(data); nb += data
while len(nb) % 4: nb.append(0)
g["buffers"][0]["byteLength"] = len(nb)
js = json.dumps(g, separators=(",", ":")).encode()
js += b" " * ((4 - len(js) % 4) % 4)
out = struct.pack("<III", magic, ver, 12 + 8 + len(js) + 8 + len(nb)) + struct.pack("<II", len(js), jt) + js + struct.pack("<II", len(nb), bt) + bytes(nb)
open(dst, "wb").write(out)
print("GLB_WEBFIX_OK", rep, "gain", GAIN.tolist(), "head", HGAIN.tolist(), "soft", SOFT)

"""Compose the task-134122 review sheets from Cycles renders + references."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

R = Path(sys.argv[1])
out = Path(sys.argv[2])
refs = sys.argv[3:]
try:
    F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    FS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
except Exception:
    F = FS = ImageFont.load_default()


def tile(path, w, h, label):
    im = Image.open(path).convert("RGB")
    im.thumbnail((w, h - 30))
    t = Image.new("RGB", (w, h), (32, 32, 34))
    t.paste(im, ((w - im.width) // 2, 30))
    ImageDraw.Draw(t).text((8, 4), label, fill=(235, 235, 235), font=FS)
    return t


def grid(items, cols, w, h, title):
    rows = (len(items) + cols - 1) // cols
    S = Image.new("RGB", (cols * w, rows * h + 40), (20, 20, 22))
    ImageDraw.Draw(S).text((10, 8), title, fill=(255, 255, 255), font=F)
    for k, (p, lab) in enumerate(items):
        S.paste(tile(p, w, h, lab), ((k % cols) * w, 40 + (k // cols) * h))
    return S


poses = [("rest_front", "rest front"), ("rest_side", "rest side"), ("rest_back", "rest back"),
         ("rest_back34", "back 3/4"), ("walk_front34", "walk (gated)"), ("sit_side", "sit 80 (gated)"),
         ("arms_up45_front", "arms up 45 (gated)"), ("step_twist_front34", "step + twist (gated)")]
grid([(R / f"{n}.png", l) for n, l in poses], 4, 420, 690,
     "dressable-g9 s15 refit (task 134122): amy_a08_v3 + 70s jeans / collar shirt - Cycles").save(out / "s15_134122_posed_sheet.png")
det = [(R / "face_front.png", "face (a08_v3 unchanged)"), (R / "face_34.png", "face 3/4 + collar"),
       (R / "seat_back34.png", "seat: tight denim, patch pockets"),
       (R / "jeans_front_detail.png", "front: fly, scoop pockets")]
grid(det, 4, 420, 560, "details").save(out / "s15_134122_details.png")
if refs:
    items = [(p, "photo target (flux2 via peer-generate-artifact)") for p in refs]
    items += [(R / "rest_front.png", "3D build (Cycles)"), (R / "rest_side.png", "3D build side")]
    grid(items, len(items), 420, 690, "dressed-Amy photo target vs 3D build").save(out / "s15_134122_target_vs_build.png")
print("COMPOSED", out)

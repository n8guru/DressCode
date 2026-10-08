"""Generic: body collider + already-draped inner garment(s) -> a new GarmentCode body
(obj in metres, segmentation json with garment verts labelled 'body', yaml copied),
the same construction as task-133934's g9_amy_m133934_pants.  Usage:
  python make_layer_collider.py BODIES_DIR BASE_NAME NEW_NAME INNER_SIM.obj [...]"""
import json, shutil, sys
from pathlib import Path
bd, base, new = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
V, F = [], []
def rd(p, scale):
    v, f = [], []
    for l in open(p):
        if l.startswith('v '):
            v.append([float(t) * scale for t in l.split()[1:4]])
        elif l.startswith('f '):
            f.append([int(t.split('/')[0]) for t in l.split()[1:]])
    return v, f
v, f = rd(bd / f"{base}.obj", 1.0); V += v; F += f
seg = json.load(open(bd / f"{base}_segmentation.json"))
for inner in sys.argv[4:]:
    v, f = rd(inner, 0.01); off = len(V)
    seg['body'] += list(range(off, off + len(v)))
    V += v; F += [[i + off for i in ff] for ff in f]
with open(bd / f"{new}.obj", 'w') as o:
    for p in V: o.write("v %.6f %.6f %.6f\n" % tuple(p))
    for ff in F: o.write("f " + " ".join(map(str, ff)) + "\n")
json.dump(seg, open(bd / f"{new}_segmentation.json", 'w'))
shutil.copy(bd / f"{base}.yaml", bd / f"{new}.yaml")
print("COLLIDER", new, len(V), len(F))

# Gate measurement for garment fit (dressable-g9 / FoundryClothThickness).
#
# Gates:
#   * boundary edges per garment
#   * body-penetrating verts (+max depth) — closest-point / nrm-dot
#   * rest-pose BVH triangle-overlap pairs (ErrorLog 45648)
#   * exposed_fraction via COVER: body verts in band z 0.96-1.48, |x|<=0.18,
#     80mm ray along vertex normal, miss = exposed.
#
# Interpenetration proof is NOT `inside_verts == 0`. A garment triangle can
# slice the body with every vertex outside (task 3186: 0 inside, 1,544
# BVHTree.overlap pairs). `interpenetration_ok` requires inside_verts == 0
# AND bvh_overlap_pairs == 0. `--fail-closed` (default) exits 1 otherwise.
import json
import os
import sys
from collections import Counter

import bpy
from mathutils.bvhtree import BVHTree

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
try:
    from garment_interpenetration_gate import non_interpenetrating
except ImportError:  # copied next to a blend without the helper
    def non_interpenetrating(*, inside_verts, overlap_pairs):
        return int(inside_verts or 0) == 0 and int(overlap_pairs or 0) == 0

BODY = "Genesis 9 Mesh_baked"
SHIRT = "G9 Base Shirt Mesh_baked"
PATCH = "G9 Base Shirt Mesh FitPatch_baked"
RAY_LEN = 0.080  # 80mm
EPS = 1e-4

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
tag = "baseline"
out_path = None
fail_closed = True
body_name = BODY
garment_names = [SHIRT, PATCH]
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--out" and i + 1 < len(argv):
        out_path = argv[i + 1]
        i += 2
        continue
    if a == "--tag" and i + 1 < len(argv):
        tag = argv[i + 1]
        i += 2
        continue
    if a == "--body" and i + 1 < len(argv):
        body_name = argv[i + 1]
        i += 2
        continue
    if a == "--garment" and i + 1 < len(argv):
        garment_names.append(argv[i + 1])
        i += 2
        continue
    if a == "--fail-closed":
        fail_closed = True
        i += 1
        continue
    if a in ("--report-only", "--no-fail-closed"):
        fail_closed = False
        i += 1
        continue
    if not a.startswith("-") and tag == "baseline":
        tag = a
        i += 1
        continue
    if not a.startswith("-") and out_path is None:
        out_path = a
        i += 1
        continue
    i += 1

dg = bpy.context.evaluated_depsgraph_get()


def mesh_of(name):
    return bpy.data.objects[name].evaluated_get(dg).to_mesh()


def world_polys(ob):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    mw = ob.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return verts, polys


def boundary_edges(me):
    c = Counter()
    for p in me.polygons:
        for ek in p.edge_keys:
            c[ek] += 1
    return sum(1 for v in c.values() if v == 1)


body_ob = bpy.data.objects.get(body_name)
if body_ob is None:
    # Un-baked production name.
    body_ob = bpy.data.objects.get("Genesis 9 Mesh")
if body_ob is None:
    raise SystemExit("GATES_FAIL missing body mesh")

garments = []
seen = set()
for n in garment_names:
    if n in seen:
        continue
    seen.add(n)
    if n in bpy.data.objects:
        garments.append(n)
if not garments:
    garments = [
        o.name for o in bpy.data.objects
        if o.type == "MESH" and o != body_ob
        and any(h in o.name.lower() for h in ("shirt", "dress", "skirt", "short", "fitpatch", "outfit"))
    ]

res = {
    "tag": tag,
    "body": body_ob.name,
    "boundary_edges": {},
    "inside_verts": 0,
    "max_depth_mm": 0.0,
    "bvh_overlap_pairs": 0,
    "overlap_by_garment": {},
    "exposed_fraction": None,
}

# --- boundary edges + vertex-inside (necessary, not sufficient) ---
for name in garments:
    me = mesh_of(name)
    res["boundary_edges"][name] = boundary_edges(me)
    ob = bpy.data.objects[name]
    mw = ob.matrix_world
    bmw_inv = body_ob.matrix_world.inverted()
    depth_max = 0.0
    inside = 0
    for v in me.vertices:
        co_body = bmw_inv @ (mw @ v.co)
        ok, loc, nrm, _ = body_ob.closest_point_on_mesh(co_body, distance=0.05)
        if ok and (co_body - loc).dot(nrm) < 0.0:
            inside += 1
            d = (co_body - loc).length * 1000.0
            depth_max = max(depth_max, d)
    res["inside_verts"] += inside
    res["max_depth_mm"] = max(res["max_depth_mm"], round(depth_max, 3))

# --- rest-pose BVH triangle overlap (the missing half of the proof) ---
bv, bp = world_polys(body_ob)
body_bvh = BVHTree.FromPolygons(bv, bp)
total_pairs = 0
for name in garments:
    ob = bpy.data.objects[name]
    gv, gp = world_polys(ob)
    g_bvh = BVHTree.FromPolygons(gv, gp)
    pairs = body_bvh.overlap(g_bvh) or []
    res["overlap_by_garment"][name] = len(pairs)
    total_pairs += len(pairs)
res["bvh_overlap_pairs"] = total_pairs
res["interpenetration_ok"] = non_interpenetrating(
    inside_verts=res["inside_verts"], overlap_pairs=res["bvh_overlap_pairs"]
)

# --- COVER: exposed fraction ---
verts, polys = [], []
off = 0
for name in garments:
    me = mesh_of(name)
    mw = bpy.data.objects[name].matrix_world
    verts += [mw @ v.co for v in me.vertices]
    polys += [tuple(i + off for i in p.vertices) for p in me.polygons]
    off = len(verts)
bvh = BVHTree.FromPolygons(verts, polys) if verts and polys else None

bme = mesh_of(body_ob.name)
bmw = body_ob.matrix_world
nmat = bmw.to_3x3().inverted().transposed()
total = exposed = 0
exposed_pts = []
if bvh is not None:
    for v in bme.vertices:
        co = bmw @ v.co
        if not (0.96 <= co.z <= 1.48 and abs(co.x) <= 0.18):
            continue
        n = (nmat @ v.normal).normalized()
        total += 1
        hit = bvh.ray_cast(co + n * EPS, n, RAY_LEN)
        if hit[0] is None:
            exposed += 1
            if len(exposed_pts) < 10:
                exposed_pts.append([round(c, 4) for c in co])
res["cover_sampled"] = total
res["cover_exposed"] = exposed
res["exposed_fraction"] = round(exposed / total, 4) if total else None
res["exposed_sample_pts"] = exposed_pts

print("GATES " + json.dumps(res, sort_keys=True))
if not res["interpenetration_ok"]:
    print(
        "INTERPEN_FAIL inside_verts=%d bvh_overlap_pairs=%d "
        "(ray-parity/vertex-inside is not a non-intersection proof)"
        % (res["inside_verts"], res["bvh_overlap_pairs"]),
        flush=True,
    )
if out_path:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
if fail_closed and not res["interpenetration_ok"]:
    sys.exit(1)

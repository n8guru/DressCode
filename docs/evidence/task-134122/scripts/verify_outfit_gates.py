"""Re-measure a SAVED fitted outfit blend (task-134074 reproducibility).

blender -b dressable_g9_outfit.blend --python verify_outfit_gates.py -- --out gates.json
Loads the blend fresh (drivers, correctives, spring bones as saved), measures
rest / ship / every POSES frame with the same BVH gates, plus garment
self-overlap (non-adjacent triangle pairs) for information.
"""
import bpy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import addon_utils; addon_utils.enable("import_daz", default_set=True, persistent=True)
except Exception as e: print("WARN", e)
import fit_native_g9_outfit as F
from mathutils.bvhtree import BVHTree
a = sys.argv[sys.argv.index("--")+1:]
out = Path(a[a.index("--out")+1])
rig = bpy.data.objects[F.RIG]; body = bpy.data.objects[F.BODY]
for m in body.modifiers:
    if m.type == "SUBSURF": m.show_viewport = False
g = {"pants": bpy.data.objects["Dressable Pants"], "shirt": bpy.data.objects["Dressable Shirt"]}
def self_pairs(ob):
    V, T = F.world_tris(ob)
    b = BVHTree.FromPolygons(V, T)
    return sum(1 for i, j in b.overlap(b) if i < j and not set(T[i]) & set(T[j]))
def row(tag):
    m = F.measure(body, g)
    for k, ob in g.items():
        m["per_garment"][k]["self_overlap_pairs_nonadjacent"] = self_pairs(ob)
    r = {k: {x: v[x] for x in ("body_overlap_pairs", "inside_verts_normal_test",
                               "inside_verts_ray_parity_6axis_majority", "max_depth_mm",
                               "boundary_edges", "self_overlap_pairs_nonadjacent",
                               "non_interpenetrating")} for k, v in m["per_garment"].items()}
    res = {"per_garment": r, "garment_garment_overlap_pairs": m["garment_garment_overlap_pairs"],
           "cover": m["cover"]}
    print("VERIFY", tag, json.dumps(res, sort_keys=True), flush=True)
    return res
rep = {"blend": bpy.data.filepath, "frames": {}}
rig.data.pose_position = "REST"; bpy.context.view_layer.update()
rep["frames"]["rest"] = row("rest")
rig.data.pose_position = "POSE"; F.set_pose(rig, {})
rep["frames"]["ship"] = row("ship")
for n, pose in F.POSES.items():
    F.set_pose(rig, pose)
    rep["frames"][n] = row(n)
F.set_pose(rig, {})
def ok(fr): return all(v["non_interpenetrating"] for v in fr["per_garment"].values()) and \
    all(x == 0 for x in fr["garment_garment_overlap_pairs"].values())
rep["gated"] = list(F.GATED)
rep["gated_all_zero"] = all(ok(rep["frames"][n]) for n in ["rest", "ship", *F.GATED])
rep["diagnostic_fail"] = [n for n in F.POSES if n not in F.GATED and not ok(rep["frames"][n])]
out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n")
print("VERIFY_DONE gated_all_zero=%s diagnostic_fail=%s" % (rep["gated_all_zero"], rep["diagnostic_fail"]))

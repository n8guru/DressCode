"""Export an evaluated G9 body (+graft) as a GarmentCode collider body.

GarmentCode bodies are metre OBJs, +Y up, +Z forward, with a
{label: [vertex ids]} segmentation.  G9 Blender is metre, +Z up, -Y forward:
GC (x, y, z) = (X, Z, -Y).  Segmentation comes from each vertex's dominant
G9 bone weight.  Subdivision is disabled so the collider is the base cage.
Usage: blender -b master.blend --python this.py -- --out-dir DIR --name NAME
"""
import bpy, json, sys, argparse, re
from pathlib import Path
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", required=True); ap.add_argument("--name", required=True)
ap.add_argument("--objects", nargs="+", default=["Genesis 9 Mesh", "GoldenPalace_G9 Mesh"])
a = ap.parse_args(argv)
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
ARM = re.compile(r"^(l|r)_(upperarm|forearm|hand|thumb|index|mid|ring|pinky|carpal)")
LEG = re.compile(r"^(l|r)_(thigh|shin|foot|toes|metatarsal|bigtoe|indextoe|midtoe|ringtoe|pinkytoe)")
def label(bone):
    m = ARM.match(bone)
    if m: return ("left_arm" if m.group(1) == "l" else "right_arm")
    m = LEG.match(bone)
    if m: return ("left_leg" if m.group(1) == "l" else "right_leg")
    return "body"
for o in bpy.data.objects:
    if o.type == "MESH":
        for m in o.modifiers:
            if m.type == "SUBSURF": m.show_viewport = False; m.show_render = False
rig = bpy.data.objects["Genesis 9"]
rig.data.pose_position = "REST"
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
V, F = [], []
seg = {k: [] for k in ("body", "left_arm", "right_arm", "left_leg", "right_leg", "face_internal")}
for name in a.objects:
    ob = bpy.data.objects.get(name)
    if ob is None: continue
    ev = ob.evaluated_get(dg); me = ev.to_mesh(); me.calc_loop_triangles()
    base = len(V)
    src = ob.data.vertices
    for i, v in enumerate(me.vertices):
        p = ev.matrix_world @ v.co
        V.append((p.x, p.z, -p.y))
        lab = "body"
        if i < len(src) and src[i].groups and name == "Genesis 9 Mesh":
            g = max(src[i].groups, key=lambda g: g.weight)
            lab = label(ob.vertex_groups[g.group].name)
        seg[lab].append(base + i)
    for t in me.loop_triangles:
        F.append(tuple(base + k for k in t.vertices))
    ev.to_mesh_clear()
obj = out / f"{a.name}.obj"
with obj.open("w") as f:
    for v in V: f.write("v %.6f %.6f %.6f\n" % v)
    for t in F: f.write("f %d %d %d\n" % (t[0]+1, t[1]+1, t[2]+1))
(out / f"{a.name}_segmentation.json").write_text(json.dumps(seg))
ys = [v[1] for v in V]
print("G9_BODY_OK", json.dumps({"obj": str(obj), "verts": len(V), "tris": len(F), "height_m": max(ys) - min(ys),
      "min_y": min(ys), "seg": {k: len(v) for k, v in seg.items()}}), flush=True)

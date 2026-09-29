"""Measure the foundry offline fan-wind bake on a built blend (task-134074).

blender -b with_secondary_motion.blend --python measure_fan_bake.py -- --out sway.json
For each garment: vertices carrying >0.3 spring-bone weight; displacement of
each vs frame 1 over the baked action frames; terminal sway = max over frames.
"""
import bpy, json, sys
a = sys.argv[sys.argv.index("--") + 1:]
out = a[a.index("--out") + 1]
rig = bpy.data.objects["Genesis 9"]
prof = json.loads(rig["foundry_secondary_motion"])
spring = {b for c in prof["chains"] for b in c["bones"]}
sc = bpy.context.scene
res = {"action": rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None,
       "frames": [sc.frame_start, sc.frame_end], "garments": {}}
garments = [o for o in bpy.data.objects if o.type == "MESH" and o.get("foundry_wearable_contract")]
for g in garments:
    names = {vg.index: vg.name for vg in g.vertex_groups}
    idx = [v.index for v in g.data.vertices
           if sum(e.weight for e in v.groups if names[e.group] in spring) > 0.3]
    res["garments"][g.name] = {"tracked_vertices": len(idx)}
def pos(g, idx):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = g.evaluated_get(dg); me = ev.to_mesh()
    P = [(ev.matrix_world @ me.vertices[i].co).copy() for i in idx]
    ev.to_mesh_clear(); return P
track = {g.name: [v.index for v in g.data.vertices
                  if sum(e.weight for e in v.groups if {vg.index: vg.name for vg in g.vertex_groups}[e.group] in spring) > 0.3]
         for g in garments}
sc.frame_set(sc.frame_start)
rest = {g.name: pos(g, track[g.name]) for g in garments}
mx = {g.name: 0.0 for g in garments}
for f in range(sc.frame_start + 1, sc.frame_end + 1):
    sc.frame_set(f)
    for g in garments:
        for p, r in zip(pos(g, track[g.name]), rest[g.name]):
            mx[g.name] = max(mx[g.name], (p - r).length)
for g in garments:
    res["garments"][g.name]["max_sway_mm"] = round(mx[g.name] * 1000, 2)
res["pass_gt_1mm"] = all(v["max_sway_mm"] > 1.0 for v in res["garments"].values())
json.dump(res, open(out, "w"), indent=2)
print("FAN_BAKE", json.dumps(res))

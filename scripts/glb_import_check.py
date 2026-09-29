"""Fresh-import a foundry character.glb and confirm the outfit binding (task-134074).
blender -b --factory-startup --python glb_import_check.py -- <character.glb> <out.json>"""
import bpy, json, sys, struct
a = sys.argv[sys.argv.index("--") + 1:]
glb, out = a[0], a[1]
raw = open(glb, "rb").read()
jlen = struct.unpack("<I", raw[12:16])[0]
gj = json.loads(raw[20:20 + jlen])
extras = ((gj.get("asset") or {}).get("extras") or {}).get("foundry", {})
sm = extras.get("secondary_motion")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
res = {"glb": glb, "skins_in_json": len(gj.get("skins", [])),
       "joints_per_skin": [len(s["joints"]) for s in gj.get("skins", [])],
       "armatures_after_import": [o.name for o in arms], "meshes": {}}
spring = sorted({b for c in (sm or {}).get("chains", []) for b in c["bones"]})
res["secondary_motion_extra"] = {"chains": [c["id"] for c in (sm or {}).get("chains", [])], "bones": spring}
for o in bpy.data.objects:
    if o.type == "MESH" and o.name.lower().startswith("dressable"):
        mods = [m for m in o.modifiers if m.type == "ARMATURE"]
        vg = {g.name for g in o.vertex_groups}
        res["meshes"][o.name] = {
            "vertices": len(o.data.vertices),
            "armature": mods[0].object.name if mods and mods[0].object else None,
            "parent": o.parent.name if o.parent else None,
            "vertex_groups": len(vg),
            "spring_groups": sorted(vg & set(spring)),
            "morph_targets": (len(o.data.shape_keys.key_blocks) - 1) if o.data.shape_keys else 0,
            "unweighted": sum(1 for v in o.data.vertices if not any(e.weight > 0 for e in v.groups)),
        }
bones = {b.name for a_ in arms for b in a_.data.bones}
res["spring_bones_on_armature"] = sorted(set(spring) & bones)
body = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Genesis 9")]
res["body_armature"] = sorted({m.object.name for o in body for m in o.modifiers if m.type == "ARMATURE" and m.object})
res["both_bound_to_body_skin"] = (len(res["meshes"]) == 2 and
    all(m["armature"] in res["body_armature"] and m["unweighted"] == 0 for m in res["meshes"].values()))
json.dump(res, open(out, "w"), indent=2)
print("GLB_CHECK", json.dumps(res))

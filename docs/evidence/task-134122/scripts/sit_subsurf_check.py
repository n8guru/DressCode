import bpy, sys, json
from pathlib import Path
sys.path.insert(0, "/home/n8/cloth_test/task-134122/scripts")
import addon_utils; addon_utils.enable("import_daz", default_set=True, persistent=True)
import fit_native_g9_outfit as F
rig = bpy.data.objects[F.RIG]; body = bpy.data.objects[F.BODY]
g = {"pants": bpy.data.objects["Dressable Pants"], "shirt": bpy.data.objects["Dressable Shirt"]}
rig.data.pose_position = "POSE"
for lv in (0, 1):
    for m in body.modifiers:
        if m.type == "SUBSURF":
            m.show_viewport = lv > 0; m.levels = lv
    F.set_pose(rig, F.POSES["sit"])
    r = F.measure(body, g)
    print("SITCHK subsurf", lv, json.dumps({k: (v["body_overlap_pairs"], v["inside_verts_normal_test"], v["max_depth_mm"]) for k, v in r["per_garment"].items()}))

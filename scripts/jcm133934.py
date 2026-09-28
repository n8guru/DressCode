"""Diagnostic: is the shirt's arm-raise interpenetration caused by DAZ JCM
corrective shape keys on the body (which garments do not carry)?"""
import bpy, json, math, sys
sys.path.insert(0, "/home/n8/cloth_test/task-133934/scripts")
import fit_native_g9_outfit as F
try:
    import addon_utils; addon_utils.enable("import_daz", default_set=True, persistent=True)
except Exception as e:
    print("WARN", e)
body, rig = bpy.data.objects[F.BODY], bpy.data.objects[F.RIG]
for m in body.modifiers:
    if m.type == "SUBSURF": m.show_viewport = False
g = {"pants": bpy.data.objects["Dressable Pants"], "shirt": bpy.data.objects["Dressable Shirt"]}
rig.data.pose_position = "POSE"
out = {}
for mode in ("jcm_on", "jcm_off"):
    if mode == "jcm_off":
        sk = body.data.shape_keys
        if sk:
            if sk.animation_data:
                for d in sk.animation_data.drivers: d.mute = True
            for kb in sk.key_blocks[1:]: kb.mute = True
    for pname in ("arms_up20", "arms_swing15", "arms_up45"):
        F.set_pose(rig, F.POSES[pname])
        r = F.measure(body, g)["per_garment"]["shirt"]
        out[f"{mode}:{pname}"] = {k: r[k] for k in ("body_overlap_pairs", "inside_verts_normal_test", "max_depth_mm")}
        print("JCM_DIAG", mode, pname, json.dumps(out[f"{mode}:{pname}"]), flush=True)
print("JCM_DIAG_DONE " + json.dumps(out))

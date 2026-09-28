import bpy, sys, json
sys.path.insert(0, "/home/n8/cloth_test/task-133934/scripts")
import fit_native_g9_outfit as F
try:
    import addon_utils; addon_utils.enable("import_daz", default_set=True, persistent=True)
except Exception: pass
body, rig = bpy.data.objects[F.BODY], bpy.data.objects[F.RIG]
for m in body.modifiers:
    if m.type == "SUBSURF": m.show_viewport = False
P, S = bpy.data.objects["Dressable Pants"], bpy.data.objects["Dressable Shirt"]
rig.data.pose_position = "POSE"
F.set_pose(rig, F.POSES[sys.argv[-1]])
from mathutils.bvhtree import BVHTree
PV, PT = F.world_tris(P); SV, ST = F.world_tris(S)
pairs = BVHTree.FromPolygons(SV, ST).overlap(BVHTree.FromPolygons(PV, PT))
for a, b in pairs:
    c = sum((SV[i] for i in ST[a]), SV[ST[a][0]] * 0) / 3
    sv = S.data.vertices[ST[a][0]] if ST[a][0] < len(S.data.vertices) else None
    grp = sorted(((S.vertex_groups[e.group].name, round(e.weight, 2)) for e in sv.groups), key=lambda x: -x[1]) if sv else None
    print("GG", [round(x, 3) for x in c], grp)

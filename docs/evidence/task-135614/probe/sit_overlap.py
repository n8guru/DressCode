import bpy, sys, json
from pathlib import Path
sys.path.insert(0, "/home/n8/cloth_test/task-135614/scripts")
import addon_utils; addon_utils.enable("import_daz", default_set=True, persistent=True)
import fit_native_g9_outfit as F
from mathutils.bvhtree import BVHTree
pose = sys.argv[sys.argv.index("--")+1]
rig=bpy.data.objects[F.RIG]; body=bpy.data.objects[F.BODY]
for m in body.modifiers:
    if m.type=="SUBSURF": m.show_viewport=False
rig.data.pose_position="POSE"; F.set_pose(rig, F.POSES[pose])
p=bpy.data.objects["Dressable Pants"]
BV,BT=F.world_tris(body); PV,PT=F.world_tris(p)
bb=BVHTree.FromPolygons(BV,BT); pb=BVHTree.FromPolygons(PV,PT)
prs=pb.overlap(bb)
print("PAIRS",len(prs))
side=[0]*len(p.data.vertices); p.data.attributes["gc_leg_side"].data.foreach_get("value",side)
fl=[0]*len(p.data.vertices); p.data.attributes["gc_flare"].data.foreach_get("value",fl)
R=[v.co for v in p.data.vertices]
for i,j in prs[:40]:
    t=PT[i]; c=sum((PV[k] for k in t), PV[0]*0)/3
    print("OV", tuple(round(x,3) for x in c), "side",[side[k] for k in t],"flare",[fl[k] for k in t], "restz",round((rig.matrix_world@R[t[0]]).z,3))

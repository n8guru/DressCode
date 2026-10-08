import bpy, sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path.home()/"cloth_test/task-142131/scripts"))
import fit_native_g9_outfit as F
from mathutils.bvhtree import BVHTree
rig=bpy.data.objects[F.RIG]; body=bpy.data.objects[F.BODY]
for m in body.modifiers:
    if m.type=="SUBSURF": m.show_viewport=False
rig.data.pose_position="REST"; bpy.context.view_layer.update()
gs=[o for o in bpy.data.objects if o.name.startswith("Dressable ")]
verts,polys,off=[],[],0
for g in gs:
    V,T=F.world_tris(g); verts+=V; polys+=[tuple(i+off for i in t) for t in T]; off=len(verts)
bvh=BVHTree.FromPolygons(verts,polys)
dg=bpy.context.evaluated_depsgraph_get(); ev=body.evaluated_get(dg); me=ev.to_mesh()
nmat=ev.matrix_world.to_3x3().inverted().transposed()
c=Counter(); far=Counter()
for v in me.vertices:
    co=ev.matrix_world@v.co
    if not (0.96<=co.z<=1.48 and abs(co.x)<=0.18): continue
    n=(nmat@v.normal).normalized()
    if bvh.ray_cast(co+n*1e-4,n,0.08)[0] is None:
        side="front" if n.y<-0.3 else ("back" if n.y>0.3 else "side")
        c[(round(co.z,2)//0.04*0.04, side)]+=1
        h=bvh.ray_cast(co+n*1e-4,n,1.0); far[side, None if h[0] is None else round(h[3],2)]+=1
print("COVER_WHERE", sorted(c.items()))
print("FAR", sorted(far.items(), key=lambda x:-x[1])[:20])

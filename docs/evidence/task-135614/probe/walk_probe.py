import bpy, math, numpy as np
from collections import Counter
rig=bpy.data.objects["Genesis 9"]; p=bpy.data.objects["Dressable Pants"]
W={"l_thigh": (-20, 0, 0), "r_thigh": (15, 0, 0), "r_shin": (25, 0, 0),"spine1": (0, 4, 0), "l_upperarm": (-12, 0, 0), "r_upperarm": (12, 0, 0)}
dg=bpy.context.evaluated_depsgraph_get()
def V():
    bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
    e=p.evaluated_get(dg); me=e.to_mesh(); a=np.array([e.matrix_world@v.co for v in me.vertices]); e.to_mesh_clear(); return a
rig.data.pose_position="POSE"
for pb in rig.pose.bones: pb.rotation_mode="XYZ"; pb.rotation_euler=(0,0,0)
R=V()
for n,r in W.items(): rig.pose.bones[n].rotation_euler=tuple(math.radians(x) for x in r)
P=V()
# rigid r_shin transform
pb=rig.pose.bones["r_shin"]; M=rig.matrix_world@pb.matrix@pb.bone.matrix_local.inverted()@rig.matrix_world.inverted()
Rs=np.array([M@__import__('mathutils').Vector(x) for x in R])
d=np.linalg.norm(P-Rs,axis=1)
gn={g.index:g.name for g in p.vertex_groups}
sel=np.where((R[:,2]<0.4)&(R[:,0]<0))[0]
print("RSHIN_LOWER n",len(sel),"dev>3cm",int((d[sel]>0.03).sum()),"max",d[sel].max())
bad=sel[np.argsort(-d[sel])[:8]]
for i in bad:
    print("BAD",i,R[i].round(3),round(d[i],3),sorted([(gn[e.group],round(e.weight,2)) for e in p.data.vertices[i].groups],key=lambda t:-t[1]))
c=Counter()
for i in sel:
    for e in p.data.vertices[i].groups:
        if e.weight>0.05: c[gn[e.group]]+=1
print("GROUPS_RIGHT_LOWER",c)
E=np.array([e.vertices[:] for e in p.data.edges])
lr=np.linalg.norm(R[E[:,0]]-R[E[:,1]],axis=1); lp=np.linalg.norm(P[E[:,0]]-P[E[:,1]],axis=1)
ratio=lp/np.maximum(lr,1e-6)
o=np.argsort(-ratio)[:10]
for k in o:
    a,b=E[k]; print("STRETCH",round(ratio[k],1),R[a].round(3),R[b].round(3),sorted([(gn[e.group],round(e.weight,2)) for e in p.data.vertices[a].groups],key=lambda t:-t[1])[:3],sorted([(gn[e.group],round(e.weight,2)) for e in p.data.vertices[b].groups],key=lambda t:-t[1])[:3])
print("N_STRETCH>2",int((ratio>2).sum()))

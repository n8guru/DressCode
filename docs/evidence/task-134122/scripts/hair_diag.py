import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
rig=bpy.data.objects["Genesis 9"]; body=bpy.data.objects["Genesis 9 Mesh"]
cv=bpy.data.objects["AmyLongWaveGroom"]
print("CURVES mods", [(m.type, m.name, getattr(m,'node_group',None) and m.node_group.name) for m in cv.modifiers], "parent", cv.parent and cv.parent.name, cv.parent_type, cv.parent_bone, "surface", getattr(cv.data,'surface',None) and cv.data.surface.name)
def bvh(ob,dg):
    ev=ob.evaluated_get(dg); me=ev.to_mesh(); me.calc_loop_triangles()
    V=[ev.matrix_world@v.co for v in me.vertices]; T=[tuple(t.vertices) for t in me.loop_triangles]; ev.to_mesh_clear(); return BVHTree.FromPolygons(V,T)
for state in ("REST","POSE"):
    rig.data.pose_position=state; bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
    sh=bvh(bpy.data.objects["Dressable Shirt"],dg); bb=bvh(body,dg)
    ev=cv.evaluated_get(dg)
    P=[ev.matrix_world@Vector(p.vector) for p in ev.data.attributes["position"].data]
    inside=0; zs=[]
    for p in P[::7]:
        bl,bn,_,_=bb.find_nearest(p)
        if bl is None: continue
        d=(p-bl); 
        if d.length<1e-6: continue
        d.normalize(); h=sh.ray_cast(p+d*1e-5,d,0.08)
        loc,_,_,dist=sh.find_nearest(p)
        if h[0] is not None and dist<0.06: inside+=1; zs.append(round(p.z,2))
    from collections import Counter
    print("HAIRDIAG", state, "sampled", len(P[::7]), "under_shirt", inside, sorted(Counter(zs).items())[:12])

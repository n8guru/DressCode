import bpy, sys, json
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path.home()/"cloth_test/task-142131/scripts"))
import fit_native_g9_outfit as F
from mathutils.kdtree import KDTree
a = sys.argv[sys.argv.index("--")+1:]
rig=bpy.data.objects[F.RIG]; body=bpy.data.objects[F.BODY]
for m in body.modifiers:
    if m.type=="SUBSURF": m.show_viewport=False
rig.data.pose_position="REST"; bpy.context.view_layer.update()
bb,_=F.bvh_of(body)
for gname, obj in zip(a[0::2], a[1::2]):
    g=bpy.data.objects[gname]
    lab=[l.strip() for l in open(obj.replace('.obj','_segmentation.txt'))]
    lift=0.054874
    P=[]
    for l in open(obj):
        if l.startswith('v '):
            x,y,z=map(float,l.split()[1:4]); P.append((x/100,-z/100,y/100-lift))
    kd=KDTree(len(P))
    for i,p in enumerate(P): kd.insert(p,i)
    kd.balance()
    V,T=F.world_tris(g)
    gb=__import__('mathutils').bvhtree.BVHTree.FromPolygons(V,T)
    c=Counter(); zs=Counter()
    for i,p in enumerate(V):
        loc,n,_,d=bb.find_nearest(p)
        if (p-loc).dot(n)<0:
            # rest-frame matrix: garments are rig-local but rig at rest; use world p
            j=kd.find(p)[1]; c[lab[j]]+=1; zs[(round(p.z,1),round(p.x,1))]+=1
    pc=Counter()
    for ti,_ in gb.overlap(bb):
        j=kd.find(V[T[ti][0]])[1]; pc[lab[j]]+=1
    print("WHERE",gname,"inside_by_label",dict(c),"pairs_by_label",dict(pc),"zx",sorted(zs.items())[:30])

import bpy, numpy as np, sys, json
from mathutils.bvhtree import BVHTree
rig=bpy.data.objects["Genesis 9"]; body=bpy.data.objects["Genesis 9 Mesh"]
rig.data.pose_position="REST"
for m in body.modifiers:
    if m.type=="SUBSURF": m.show_viewport=False
bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get()
def verts(o):
    e=o.evaluated_get(dg); me=e.to_mesh(); V=np.array([e.matrix_world@v.co for v in me.vertices]); e.to_mesh_clear(); return V
B=verts(body); J=verts(bpy.data.objects["Dressable Pants"])
# body crotch: lowest body point with |x|<0.015 and z between .6 and 1.0 (perineum)
m=(abs(B[:,0])<0.015)&(B[:,2]>0.6)&(B[:,2]<1.0)
bc=B[m][np.argmin(B[m][:,2])]
mj=(abs(J[:,0])<0.015)&(J[:,2]>0.5)&(J[:,2]<1.0)
jc=J[mj][np.argmin(J[mj][:,2])]
print("BODY_CROTCH",bc.round(4),"JEANS_CROTCH",jc.round(4),"drop_mm",round((bc[2]-jc[2])*1000,1))
# offset of jeans from body in crotch/inner-thigh region: nearest-distance
me=body.evaluated_get(dg).to_mesh(); me.calc_loop_triangles()
bvh=BVHTree.FromPolygons([tuple(v) for v in B],[tuple(t.vertices) for t in me.loop_triangles])
for lab,sel in [("crotch_mid",(abs(J[:,0])<0.03)&(J[:,2]>bc[2]-0.06)&(J[:,2]<bc[2]+0.05)),
                ("inner_thigh",(abs(J[:,0])<0.07)&(J[:,2]>bc[2]-0.15)&(J[:,2]<bc[2]-0.03)),
                ("seat",(J[:,1]>0.05)&(J[:,2]>bc[2])&(J[:,2]<bc[2]+0.15))]:
    d=np.array([bvh.find_nearest(tuple(p))[3] for p in J[sel]])
    print("GAP",lab,len(d),"median_mm",round(np.median(d)*1000,1),"p90_mm",round(np.percentile(d,90)*1000,1),"max_mm",round(d.max()*1000,1))
# thigh-gap bridging: heights where jeans have verts at |x|<0.01 (fabric crossing midline) below body crotch
for dz in (0,0.02,0.04,0.06,0.08,0.10):
    z=bc[2]-dz
    print("MIDLINE z",round(z,3),"jeans_verts_|x|<8mm",int(((abs(J[:,0])<0.008)&(abs(J[:,2]-z)<0.005)).sum()),"body",int(((abs(B[:,0])<0.008)&(abs(B[:,2]-z)<0.005)).sum()))
out=sys.argv[sys.argv.index("--")+1] if "--" in sys.argv else "/tmp/xsec.npz"
np.savez(out,B=B,J=J)

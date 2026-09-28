import bpy, math
rig = bpy.data.objects["Genesis 9"]
rig.data.pose_position = "POSE"
def hand(name, rot):
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"; pb.rotation_euler = (0, 0, 0)
    pb = rig.pose.bones[name]; pb.rotation_euler = tuple(math.radians(a) for a in rot)
    bpy.context.view_layer.update()
    tip = {"l_upperarm": "l_hand", "l_thigh": "l_foot", "spine2": "head", "l_forearm": "l_hand", "r_upperarm": "r_hand", "l_shin": "l_foot"}[name]
    return rig.matrix_world @ rig.pose.bones[tip].head
for name in ("r_upperarm", "l_shin"):
    print("PROBE", name, "rest", tuple(round(c, 3) for c in hand(name, (0, 0, 0))))
    for rot in ((30, 0, 0), (-30, 0, 0), (0, 30, 0), (0, 0, 30), (0, 0, -30)):
        print("PROBE", name, rot, tuple(round(c, 3) for c in hand(name, rot)))

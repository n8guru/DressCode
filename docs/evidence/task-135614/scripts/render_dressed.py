"""task-134122: Cycles review renders of the dressed a08 Amy (hair, brows,
skin, eyes as in the identity master) in the gated poses.

blender -b outfit_mat.blend --python render_dressed.py -- --out DIR [--samples 96] [--only a,b]
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
out = Path(argv[argv.index("--out") + 1])
out.mkdir(parents=True, exist_ok=True)
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 96
only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
res_scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0

try:  # DAZ drivers (face/eye/JCM) evaluate only with the importer enabled
    import addon_utils
    addon_utils.enable("import_daz", default_set=True, persistent=True)
except Exception as e:
    print("WARN import_daz", e)
if "--pre" in argv:
    _pre = argv[argv.index("--pre") + 1]
    sys.argv = [sys.argv[0], "--", argv[argv.index("--pre") + 2]]
    exec(open(_pre).read())
    sys.argv = [sys.argv[0], "--"] + argv
sc = bpy.context.scene
rig = bpy.data.objects["Genesis 9"]
# neutral expression + driver kick (render_headshot.py / sheet_bar contract)
for ob in [rig] + [o for o in bpy.data.objects if o.type == "MESH"]:
    for k in list(ob.keys()):
        if k.lower().startswith("facs") and isinstance(ob[k], (int, float)) and not isinstance(ob[k], bool):
            ob[k] = type(ob[k])(0)
for _id in (list(bpy.data.objects) + list(bpy.data.meshes) + list(bpy.data.shape_keys)
            + list(bpy.data.armatures) + list(bpy.data.materials) + list(bpy.data.node_groups)):
    ad = getattr(_id, "animation_data", None)
    if ad:
        for fc in ad.drivers:
            try:
                fc.driver.expression = fc.driver.expression
            except Exception:
                pass
body = bpy.data.objects["Genesis 9 Mesh"]
for ob in list(bpy.data.objects):
    if ob.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(ob, do_unlink=True)
for m in body.modifiers:
    if m.type == "SUBSURF":
        m.show_render = True
        m.render_levels = 1
sc.render.engine = "CYCLES"
if "--cpu" in argv:
    sc.cycles.device = "CPU"
else:
  try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev in ("METAL", "OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = True
                sc.cycles.device = "GPU"
                break
        except Exception:
            continue
  except Exception as e:
    print("WARN gpu", e)
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.cycles.transparent_max_bounces = 32
sc.cycles.blur_glossy = 2.0
sc.cycles.sample_clamp_indirect = 3.0
sc.cycles.sample_clamp_direct = 4.0
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.view_settings.exposure = 0.0
world = sc.world or bpy.data.worlds.new("W")
sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.30, 0.30, 0.30, 1)
bg.inputs["Strength"].default_value = 1.0
sc.render.film_transparent = False


def light(name, loc, energy, size, target=(0, 0, 1.0)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


# the step-47 sheet_bar studio rig the a08 identity was graded under
LIGHTS = [("SB_Key", (-0.8, -3.0, 1.45), 450, 3.0), ("SB_FillR", (2.5, -1.5, 1.05), 200, 3.0),
          ("SB_FillL", (-2.5, 0.5, 1.05), 175, 3.0), ("SB_Back", (0.5, 3.0, 1.45), 300, 3.0)]
rig_lights = [light(*l) for l in LIGHTS]
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.sensor_fit = "VERTICAL"
cam.data.sensor_height = 24


def set_pose(pose):
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
    for name, rot in pose.items():
        pb = rig.pose.bones[name]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = tuple(math.radians(v) for v in rot)
    bpy.context.view_layer.update()


def lights_follow(yaw_deg):
    """keep the key/fill/rim rig fixed relative to the camera"""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    for ob, (_, loc, _, _) in zip(rig_lights, LIGHTS):
        x, y, z = loc
        ob.location = (c * x - s * y, s * x + c * y, z)
        ob.rotation_euler = (Vector((0, 0, 0.87)) - ob.location).to_track_quat("-Z", "Y").to_euler()


def shot(name, pose, yaw, dist, target_z, lens, w, h, zcam=None):
    if only and name not in only:
        return None
    set_pose(pose)
    lights_follow(yaw)
    a = math.radians(yaw)
    zc = target_z if zcam is None else zcam
    cam.location = (math.sin(a) * dist, -math.cos(a) * dist, zc)
    cam.rotation_euler = (Vector((0, 0, target_z)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    sc.render.resolution_x, sc.render.resolution_y = int(w * res_scale), int(h * res_scale)
    p = out / f"{name}.png"
    sc.render.filepath = str(p)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", p, flush=True)
    return str(p)


P = {
    "rest": {},
    "walk": {"l_thigh": (-20, 0, 0), "r_thigh": (15, 0, 0), "r_shin": (25, 0, 0),
             "spine1": (0, 4, 0), "l_upperarm": (-12, 0, 0), "r_upperarm": (12, 0, 0)},
    "sit": {"l_thigh": (-80, 0, 0), "r_thigh": (-80, 0, 0), "l_shin": (80, 0, 0), "r_shin": (80, 0, 0)},
    "arms_up45": {"l_upperarm": (0, 0, 45), "r_upperarm": (0, 0, -45),
                  "l_forearm": (0, 0, 10), "r_forearm": (0, 0, -10)},
    "step_twist": {"l_thigh": (-25, 0, -4), "l_shin": (30, 0, 0), "r_thigh": (10, 0, 0),
                   "spine1": (0, 6, 0), "spine2": (0, 6, 0)},
}
rig.data.pose_position = "POSE"
done = {}
if "--hide-garments" in argv:
    for ob in bpy.data.objects:
        if ob.name.startswith("Dressable"):
            ob.hide_render = True
if "--custom" in argv:  # name:pose:yaw:dist:target_z[:lens[:zcam]],...
    for spec in argv[argv.index("--custom") + 1].split(","):
        f = spec.split(":")
        n, po, yaw, dist, tz = f[0], f[1], float(f[2]), float(f[3]), float(f[4])
        lens = float(f[5]) if len(f) > 5 else 85
        zc = float(f[6]) if len(f) > 6 else None
        only = None
        done[n] = shot(n, P[po], yaw, dist, tz, lens, 900, 900, zc)
    (out / "renders.json").write_text(json.dumps(done, indent=1))
    print("RENDER_DONE", flush=True)
    sys.exit(0)
FB = (5.6, 0.87, 70, 800, 1250)  # full-body: dist, target z, lens, w, h
for name, pose, yaw, spec in (
        ("rest_front", "rest", 0, FB), ("rest_back", "rest", 180, FB), ("rest_side", "rest", 90, FB),
        ("rest_back34", "rest", 145, FB), ("walk_front34", "walk", -30, FB),
        ("sit_side", "sit", 70, (5.0, 0.62, 70, 800, 1250)),
        ("sit_front34", "sit", -35, (5.0, 0.62, 70, 800, 1250)), ("arms_up45_front", "arms_up45", 0, FB),
        ("step_twist_front34", "step_twist", 30, FB)):
    done[name] = shot(name, P[pose], yaw, *spec)
def face_shot(name, yaw, dist=0.65, lens=65, w=800, h=1000):
    if only and name not in only:
        return None
    set_pose({})
    dg = bpy.context.evaluated_depsgraph_get()
    ae = rig.evaluated_get(dg)
    hw = ae.matrix_world @ ((ae.pose.bones["l_eye"].head + ae.pose.bones["r_eye"].head) * 0.5)
    saved = [(o.location.copy(), o.data.energy, o.data.size, o.rotation_euler.copy()) for o in rig_lights]
    spec = [((-0.45, -0.55, 0.30), 22.0, 0.6), ((0.55, -0.50, 0.05), 8.0, 0.8),
            ((0.15, 0.60, 0.40), 16.0, 0.4), ((0, 0, 50), 0.0, 0.1)]
    for o, (off, e, sz) in zip(rig_lights, spec):
        o.location = hw + Vector(off)
        o.data.energy, o.data.size = e, sz
        o.rotation_euler = (hw - o.location).to_track_quat("-Z", "Y").to_euler()
    bg.inputs["Color"].default_value = (0.18, 0.18, 0.18, 1)
    a_ = math.radians(yaw)
    cam.data.sensor_fit = "AUTO"
    cam.data.sensor_width = 36
    cam.data.lens = lens
    cam.location = (hw.x + dist * math.sin(a_), hw.y - dist * math.cos(a_), hw.z + 0.03)
    cam.rotation_euler = (math.pi / 2, 0.0, a_)
    sc.render.resolution_x, sc.render.resolution_y = int(w * res_scale), int(h * res_scale)
    p = out / f"{name}.png"
    sc.render.filepath = str(p)
    bpy.ops.render.render(write_still=True)
    for o, (l, e, sz, r) in zip(rig_lights, saved):
        o.location, o.data.energy, o.data.size, o.rotation_euler = l, e, sz, r
    bg.inputs["Color"].default_value = (0.30, 0.30, 0.30, 1)
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 24
    print("RENDERED", p, flush=True)
    return str(p)


done["face_front"] = face_shot("face_front", 0)
done["face_34"] = face_shot("face_34", -25, dist=0.9, lens=50)
done["seat_back34"] = shot("seat_back34", {}, 150, 1.9, 0.86, 85, 900, 1000)
done["jeans_front_detail"] = shot("jeans_front_detail", {}, -20, 1.7, 0.85, 85, 900, 1000)
# task-135614 (decision #1997482) close-ups: crotch/rise fit and bent knees
done["crotch_front"] = shot("crotch_front", {}, 0, 1.5, 0.80, 85, 900, 1000)
done["crotch_side"] = shot("crotch_side", {}, 90, 1.5, 0.80, 85, 900, 1000)
done["knee_walk_side"] = shot("knee_walk_side", P["walk"], 90, 1.9, 0.55, 85, 900, 1000)
done["knee_sit_side"] = shot("knee_sit_side", P["sit"], 80, 2.0, 0.50, 85, 1000, 900)
done["knee_sit_front34"] = shot("knee_sit_front34", P["sit"], -35, 2.0, 0.50, 85, 1000, 900)
done["shoulders_front"] = shot("shoulders_front", {}, 0, 1.6, 1.30, 85, 1000, 800)
set_pose({})
(out / "renders.json").write_text(json.dumps({k: v for k, v in done.items() if v}, indent=1))
print("RENDER_DONE", flush=True)

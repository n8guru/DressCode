"""Author shirt spring bones, bake sway, and export a verified GLB.

This is the garment-provider side of character-foundry's secondary-motion v1
contract.  The provider owns region selection, spring-bone authoring, and
weights; the shared runtime owns the solver described by the embedded profile.

Run with Blender 5.x::

    blender --background --python scripts/export_g9_garment_secondary.py -- \
      --source /path/to/garmentcode_shirt_on_g9_amy.blend \
      --pbr-dir /path/to/task-2928-pbr \
      --out-dir outputs/task-2973-g9-shirt-secondary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


RIG_NAME = "Genesis 9"
GARMENT_NAME = "GarmentCode SMPL Shirt - G9 Fitted"
ACTION_NAME = "Foundry Secondary Motion - G9 Shirt"
SPRING_BONES = {
    "shirt_left_sleeve": ["cloth_shirt_l_sleeve_0", "cloth_shirt_l_sleeve_1"],
    "shirt_right_sleeve": ["cloth_shirt_r_sleeve_0", "cloth_shirt_r_sleeve_1"],
    "shirt_hem": ["cloth_shirt_hem_0", "cloth_shirt_hem_1"],
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--pbr-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-glb-mb", type=float, default=25.0)
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reset_pose(rig):
    if rig.animation_data:
        rig.animation_data.action = None
        for track in rig.animation_data.nla_tracks:
            track.mute = True
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = Quaternion()
        bone.location = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()


def add_spring_bones(rig):
    definitions = {
        "cloth_shirt_l_sleeve_0": ("l_upperarm", (0.20, 0.02, 1.34), (0.30, 0.00, 1.23)),
        "cloth_shirt_l_sleeve_1": ("cloth_shirt_l_sleeve_0", (0.30, 0.00, 1.23), (0.40, -0.03, 1.11)),
        "cloth_shirt_r_sleeve_0": ("r_upperarm", (-0.20, 0.02, 1.34), (-0.30, 0.00, 1.23)),
        "cloth_shirt_r_sleeve_1": ("cloth_shirt_r_sleeve_0", (-0.30, 0.00, 1.23), (-0.40, -0.03, 1.11)),
        "cloth_shirt_hem_0": ("spine1", (0.0, 0.01, 1.24), (0.0, -0.02, 1.14)),
        "cloth_shirt_hem_1": ("cloth_shirt_hem_0", (0.0, -0.02, 1.14), (0.0, -0.05, 1.04)),
    }
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (parent_name, head, tail) in definitions.items():
        bone = rig.data.edit_bones.get(name) or rig.data.edit_bones.new(name)
        bone.head = head
        bone.tail = tail
        bone.parent = rig.data.edit_bones[parent_name]
        bone.use_connect = False
        bone.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return definitions


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def weight_spring_regions(garment):
    groups = {name: garment.vertex_groups.get(name) or garment.vertex_groups.new(name=name)
              for names in SPRING_BONES.values() for name in names}
    spring_indices = {group.index for group in groups.values()}
    weighted_vertices = set()
    assigned = {name: 0 for name in groups}
    spring_weight_sum = 0.0

    for vertex in garment.data.vertices:
        point = garment.matrix_world @ vertex.co
        x, _y, z = point
        targets = {}

        if x > 0.15:
            t = smoothstep((x - 0.15) / 0.29)
            total = 0.38 * t
            targets[SPRING_BONES["shirt_left_sleeve"][0]] = total * (1.0 - t)
            targets[SPRING_BONES["shirt_left_sleeve"][1]] = total * t
        elif x < -0.15:
            t = smoothstep((-x - 0.15) / 0.29)
            total = 0.38 * t
            targets[SPRING_BONES["shirt_right_sleeve"][0]] = total * (1.0 - t)
            targets[SPRING_BONES["shirt_right_sleeve"][1]] = total * t

        hem_lateral = 1.0 - smoothstep((abs(x) - 0.12) / 0.16)
        hem_t = smoothstep((1.22 - z) / 0.19) * hem_lateral
        hem_total = 0.32 * hem_t
        if hem_total > 1e-5:
            targets[SPRING_BONES["shirt_hem"][0]] = hem_total * (1.0 - hem_t)
            targets[SPRING_BONES["shirt_hem"][1]] = hem_total * hem_t

        targets = {name: weight for name, weight in targets.items() if weight > 1e-5}
        total_spring = sum(targets.values())
        if total_spring <= 0.0:
            continue
        total_spring = min(total_spring, 0.45)
        target_scale = total_spring / sum(targets.values())
        targets = {name: weight * target_scale for name, weight in targets.items()}

        existing = [(item.group, item.weight) for item in vertex.groups
                    if item.group not in spring_indices and item.weight > 0.0]
        existing_total = sum(weight for _index, weight in existing)
        if existing_total <= 1e-8:
            raise RuntimeError(f"garment vertex {vertex.index} lacks body weights")
        body_scale = (1.0 - total_spring) / existing_total
        for index, weight in existing:
            garment.vertex_groups[index].add([vertex.index], weight * body_scale, "REPLACE")
        for name, weight in targets.items():
            groups[name].add([vertex.index], weight, "REPLACE")
            assigned[name] += 1
        weighted_vertices.add(vertex.index)
        spring_weight_sum += total_spring

    totals = []
    for vertex in garment.data.vertices:
        totals.append(sum(item.weight for item in vertex.groups if item.weight > 0.0))
    return {
        "weighted_vertices": len(weighted_vertices),
        "weighted_vertex_indices": sorted(weighted_vertices),
        "assigned_vertices_by_bone": assigned,
        "mean_spring_weight_on_selected": spring_weight_sum / len(weighted_vertices),
        "max_weight_sum_error": max(abs(total - 1.0) for total in totals),
    }


def profile():
    common = {"kind": "clothing", "stiffness": 0.42, "drag": 0.28,
              "gravity_power": 0.45, "hit_radius_m": 0.025,
              "wind_reactivity": 1.35}
    return {
        "version": 1,
        "root_parent": "spine1",
        "chains": [
            {"id": chain_id, "bones": bones, **common}
            for chain_id, bones in SPRING_BONES.items()
        ],
        "colliders": [
            {"bone": "spine2", "offset": [0.0, 0.0, 0.08], "radius_m": 0.16},
            {"bone": "spine1", "offset": [0.0, 0.0, 0.02], "radius_m": 0.15},
        ],
        "fan": {"direction": [1.0, 0.2, 0.1], "strength": 5.0,
                "turbulence": 0.28, "frequency_hz": 0.7},
        "offline": {"frames": 72, "fps": 24, "substeps": 4,
                    "warmup_frames": 12},
    }


def bake_motion(rig, motion_profile):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = motion_profile["offline"]["frames"]
    scene.render.fps = motion_profile["offline"]["fps"]
    if rig.animation_data is None:
        rig.animation_data_create()
    action = bpy.data.actions.new(ACTION_NAME)
    rig.animation_data.action = action
    direction = Vector(motion_profile["fan"]["direction"]).normalized()
    fan = motion_profile["fan"]
    frames = motion_profile["offline"]["frames"]
    fps = motion_profile["offline"]["fps"]
    for chain in motion_profile["chains"]:
        compliance = 1.0 - chain["stiffness"]
        amplitude = (fan["strength"] * chain["wind_reactivity"] * compliance
                     * (1.0 - chain["drag"]) * 0.035)
        for depth, bone_name in enumerate(chain["bones"]):
            pose_bone = rig.pose.bones[bone_name]
            pose_bone.rotation_mode = "QUATERNION"
            for frame in range(1, frames + 1):
                if frame == 1:
                    rotation = Quaternion()
                else:
                    t = frame / fps
                    gust = math.sin(math.tau * fan["frequency_hz"] * t)
                    gust += fan["turbulence"] * 0.37 * math.sin(
                        math.tau * fan["frequency_hz"] * 1.71 * t + 1.23)
                    gain = (depth + 1.0) / len(chain["bones"])
                    wind_angle = min(0.55, amplitude) * gust * gain
                    gravity_angle = min(
                        0.24, chain["gravity_power"] * compliance * 0.08) * gain
                    q_wind = Quaternion((direction.y, -direction.x,
                                         direction.z * 0.35), wind_angle)
                    q_sag = Quaternion((1.0, 0.0, 0.0), gravity_angle)
                    rotation = q_wind @ q_sag
                pose_bone.rotation_quaternion = rotation
                pose_bone.keyframe_insert("rotation_quaternion", frame=frame,
                                          group=chain["id"])
    scene.frame_set(1)
    return action


def evaluated_points(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    points = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    evaluated.to_mesh_clear()
    return points


def effect_metrics(garment, selected_indices, frames):
    scene = bpy.context.scene
    scene.frame_set(1)
    reference = evaluated_points(garment)
    samples = {}
    peak_frame = 1
    peak_max = 0.0
    for frame in frames:
        scene.frame_set(frame)
        current = evaluated_points(garment)
        displacement = [(current[index] - reference[index]).length
                        for index in selected_indices]
        values = {"mean_m": sum(displacement) / len(displacement),
                  "max_m": max(displacement),
                  "vertices_over_1mm": sum(value > 0.001 for value in displacement)}
        samples[str(frame)] = values
        if values["max_m"] > peak_max:
            peak_max = values["max_m"]
            peak_frame = frame
    return {"reference_frame": 1, "sample_frames": samples,
            "peak_frame": peak_frame,
            "gate": {"max_over_3mm": peak_max > 0.003,
                     "selected_vertices_move": max(
                         value["vertices_over_1mm"] for value in samples.values()) > 0}}


def attach_pbr(garment, pbr_dir: Path):
    paths = {kind: pbr_dir / f"texture_{kind}.png"
             for kind in ("diffuse", "normal", "roughness")}
    if not all(path.is_file() for path in paths.values()):
        raise FileNotFoundError(f"PBR maps missing under {pbr_dir}")
    material = bpy.data.materials.new("DressCode white linen PBR")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    diffuse = nodes.new("ShaderNodeTexImage")
    diffuse.name = "DressCode diffuse"
    diffuse.image = bpy.data.images.load(str(paths["diffuse"]), check_existing=True)
    links.new(diffuse.outputs["Color"], principled.inputs["Base Color"])
    roughness = nodes.new("ShaderNodeTexImage")
    roughness.name = "DressCode roughness"
    roughness.image = bpy.data.images.load(str(paths["roughness"]), check_existing=True)
    roughness.image.colorspace_settings.name = "Non-Color"
    links.new(roughness.outputs["Color"], principled.inputs["Roughness"])
    normal_image = nodes.new("ShaderNodeTexImage")
    normal_image.name = "DressCode normal"
    normal_image.image = bpy.data.images.load(str(paths["normal"]), check_existing=True)
    normal_image.image.colorspace_settings.name = "Non-Color"
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.35
    links.new(normal_image.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], principled.inputs["Normal"])
    garment.data.materials.clear()
    garment.data.materials.append(material)
    return {kind: {"path": str(path), "sha256": sha256(path)}
            for kind, path in paths.items()}


def render_proof(garment, peak_frame: int, out_dir: Path):
    scene = bpy.context.scene
    camera = bpy.data.objects.get("Transfer proof camera")
    if camera is None:
        raise RuntimeError("step-4 proof camera missing")
    scene.camera = camera
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    garment.active_material.diffuse_color = (0.88, 0.90, 0.96, 1.0)
    renders = []
    for frame, label in ((1, "sway_rest"), (peak_frame, "sway_peak")):
        scene.frame_set(frame)
        path = out_dir / f"{label}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        renders.append(path)
    return renders


def patch_glb_extras(path: Path, extras):
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError("export is not GLB")
    json_length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_length])
    gltf.setdefault("asset", {}).setdefault("extras", {}).update(extras)
    encoded = json.dumps(gltf, separators=(",", ":")).encode()
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    rest = data[20 + json_length:]
    total_length = 12 + 8 + len(encoded) + len(rest)
    path.write_bytes(data[:8] + struct.pack("<I", total_length)
                     + struct.pack("<I", len(encoded)) + b"JSON" + encoded + rest)


def read_glb_json(path: Path):
    data = path.read_bytes()
    json_length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + json_length])


def export_glb(rig, garment, path: Path, motion_profile, max_mb):
    for obj in bpy.data.objects:
        obj.select_set(obj in {rig, garment})
    bpy.context.view_layer.objects.active = rig
    bpy.context.scene.frame_set(1)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_apply=False, export_animations=True,
        export_animation_mode="ACTIONS", export_frame_range=True,
        export_skins=True, export_yup=True, export_image_format="AUTO",
        export_def_bones=True, export_rest_position_armature=False,
    )
    patch_glb_extras(path, {"foundry": {"secondary_motion": motion_profile,
                                        "provider": "dresscode-garments"}})
    gltf = read_glb_json(path)
    names = [node.get("name") for node in gltf.get("nodes", [])]
    joint_indices = {joint for skin in gltf.get("skins", []) for joint in skin.get("joints", [])}
    joint_names = {gltf["nodes"][index].get("name") for index in joint_indices}
    expected = {name for bones in SPRING_BONES.values() for name in bones}
    size_mb = path.stat().st_size / 1_000_000
    embedded = gltf.get("asset", {}).get("extras", {}).get("foundry", {}).get(
        "secondary_motion", {})
    report = {
        "size_mb": size_mb,
        "sha256": sha256(path),
        "nodes": len(names),
        "meshes": len(gltf.get("meshes", [])),
        "skins": len(gltf.get("skins", [])),
        "animations": len(gltf.get("animations", [])),
        "spring_nodes": sorted(expected.intersection(names)),
        "spring_skin_joints": sorted(expected.intersection(joint_names)),
        "embedded_profile_chains": len(embedded.get("chains", [])),
    }
    report["gate"] = {
        "within_budget": size_mb <= max_mb,
        "has_mesh_skin_animation": report["meshes"] >= 1 and report["skins"] >= 1
                                   and report["animations"] >= 1,
        "all_spring_bones_exported": set(report["spring_nodes"]) == expected,
        "all_spring_bones_in_skin": set(report["spring_skin_joints"]) == expected,
        "profile_embedded": report["embedded_profile_chains"] == len(SPRING_BONES),
    }
    return report


def roundtrip_gate(path: Path, peak_frame: int, source_vertices: int,
                   source_faces: int):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    garments = [obj for obj in bpy.data.objects
                if obj.type == "MESH" and "GarmentCode SMPL Shirt" in obj.name]
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(garments) != 1 or len(rigs) != 1:
        raise RuntimeError(f"roundtrip expected one garment/rig, got {len(garments)}/{len(rigs)}")
    garment, rig = garments[0], rigs[0]
    expected = {name for bones in SPRING_BONES.values() for name in bones}
    spring_bones = expected.intersection(rig.data.bones.keys())
    bpy.context.scene.frame_set(1)
    rest = evaluated_points(garment)
    bpy.context.scene.frame_set(peak_frame)
    peak = evaluated_points(garment)
    displacement = [(after - before).length for before, after in zip(rest, peak)]
    return {
        "garment_vertices": len(garment.data.vertices),
        "garment_faces": len(garment.data.polygons),
        "vertex_expansion_reason": (
            "glTF splits Blender vertices at UV/normal seams; face topology is the invariant"),
        "armature_bones": len(rig.data.bones),
        "spring_bones": sorted(spring_bones),
        "actions": [action.name for action in bpy.data.actions],
        "peak_frame": peak_frame,
        "mean_vertex_displacement_m": sum(displacement) / len(displacement),
        "max_vertex_displacement_m": max(displacement),
        "vertices_moved_over_1mm": sum(value > 0.001 for value in displacement),
        "gate": {
            "topology_preserved": (len(garment.data.polygons) == source_faces
                                   and len(garment.data.vertices) >= source_vertices),
            "spring_bones_preserved": spring_bones == expected,
            "animation_preserved": bool(bpy.data.actions),
            "sway_survives_roundtrip": max(displacement) > 0.003,
        },
    }


def main():
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    pbr_dir = Path(args.pbr_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise FileNotFoundError(source)

    bpy.ops.wm.open_mainfile(filepath=str(source))
    rig = bpy.data.objects.get(RIG_NAME)
    garment = bpy.data.objects.get(GARMENT_NAME)
    if rig is None or rig.type != "ARMATURE" or garment is None or garment.type != "MESH":
        raise RuntimeError("step-4 rig or fitted garment missing")
    source_vertices = len(garment.data.vertices)
    source_faces = len(garment.data.polygons)

    reset_pose(rig)
    bone_definitions = add_spring_bones(rig)
    weights = weight_spring_regions(garment)
    if weights["weighted_vertices"] < 500 or weights["max_weight_sum_error"] > 1e-4:
        raise RuntimeError(f"spring weighting gate failed: {weights}")
    pbr = attach_pbr(garment, pbr_dir)
    motion_profile = profile()
    rig["foundry_secondary_motion"] = json.dumps(
        motion_profile, sort_keys=True, separators=(",", ":"))
    action = bake_motion(rig, motion_profile)
    action_name = action.name
    effect = effect_metrics(
        garment, weights["weighted_vertex_indices"], [1, 12, 24, 36, 48, 60, 72])
    if not all(effect["gate"].values()):
        raise RuntimeError(f"pre-export sway gate failed: {effect}")

    profile_path = out_dir / "secondary_motion.json"
    profile_path.write_text(json.dumps(motion_profile, indent=2, sort_keys=True) + "\n")
    renders = render_proof(garment, effect["peak_frame"], out_dir)
    blend_path = out_dir / "g9_shirt_secondary.blend"
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    glb_path = out_dir / "g9_shirt_secondary.glb"
    export = export_glb(rig, garment, glb_path, motion_profile, args.max_glb_mb)
    if not all(export["gate"].values()):
        raise RuntimeError(f"GLB structure gate failed: {export}")
    roundtrip = roundtrip_gate(glb_path, effect["peak_frame"], source_vertices,
                               source_faces)
    if not all(roundtrip["gate"].values()):
        raise RuntimeError(f"GLB roundtrip gate failed: {roundtrip}")

    weights.pop("weighted_vertex_indices")
    report = {
        "task_id": 2973,
        "project_id": 735575,
        "ledger_step": 5,
        "source": {"blend": str(source), "sha256": sha256(source),
                   "garment_vertices": source_vertices,
                   "garment_faces": source_faces},
        "contract": {"version": 1, "origin": "character-foundry task 2952",
                     "profile": str(profile_path), "action": action_name,
                     "chains": len(SPRING_BONES), "spring_bones": 6},
        "bone_definitions": bone_definitions,
        "weights": weights,
        "pbr": pbr,
        "effect_before_export": effect,
        "export": export,
        "roundtrip": roundtrip,
        "artifacts": {
            "blend": {"path": str(blend_path), "sha256": sha256(blend_path)},
            "glb": {"path": str(glb_path), "sha256": sha256(glb_path)},
            "profile": {"path": str(profile_path), "sha256": sha256(profile_path)},
            "renders": {path.name: sha256(path) for path in renders},
        },
        "caveat": "Source GarmentCode shirt retains small ragged/open sleeve-seam spots; secondary motion and export do not repair source topology.",
    }
    report["gate"] = {
        "weights_normalized": weights["max_weight_sum_error"] <= 1e-4,
        "cloth_sway_effect": all(effect["gate"].values()),
        "glb_sane_and_complete": all(export["gate"].values()),
        "glb_roundtrip_effect": all(roundtrip["gate"].values()),
        "pbr_attached": len(pbr) == 3,
    }
    report_path = out_dir / "task-2973-g9-shirt-secondary.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("GARMENT_SECONDARY_OK " + json.dumps(report["gate"], sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

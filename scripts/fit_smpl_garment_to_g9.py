"""Fit a GarmentCode/SMPL drape to a Genesis 9 character in Blender.

The input OBJ uses GarmentCode's centimetre-scale SMPL frame (+Y up, +Z
forward).  The target G9 blend uses metres with +Z up and -Y forward.  This
script preserves the simulated garment topology, bridges those frames, clears
body penetrations, transfers G9 skin weights, poses the rig, and writes machine
checkable evidence plus rest/posed renders.

Run with Blender 5.x::

    blender --background --python scripts/fit_smpl_garment_to_g9.py -- \
      --garment /path/to/shirt_mean_sim.obj \
      --g9 /path/to/amy.blend \
      --out-dir outputs/task-2964-g9-transfer
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


SOURCE_SMPL_HEIGHT_M = 1.658395
RIG_NAME = "Genesis 9"
BODY_NAME = "Genesis 9 Mesh"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--garment", required=True)
    parser.add_argument("--g9", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--body", default=BODY_NAME)
    parser.add_argument("--rig", default=RIG_NAME)
    parser.add_argument("--margin-mm", type=float, default=4.0)
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def world_points(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def bounds(obj):
    points = world_points(obj)
    return {
        "min": [min(point[axis] for point in points) for axis in range(3)],
        "max": [max(point[axis] for point in points) for axis in range(3)],
    }


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def make_material(name, rgba):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = rgba
    return material


def configure_render(body, garment):
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
        elif obj.type == "MESH" and obj not in {body, garment}:
            obj.hide_render = True
            obj.hide_viewport = True

    body.data.materials.clear()
    body.data.materials.append(make_material("G9 Amy proof", (0.52, 0.31, 0.22, 1.0)))
    garment.data.materials.clear()
    garment.data.materials.append(make_material("GarmentCode shirt", (0.90, 0.92, 0.96, 1.0)))

    camera_data = bpy.data.cameras.new("Transfer proof camera")
    camera = bpy.data.objects.new("Transfer proof camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.data.lens = 64
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.045, 0.045, 0.045)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.show_specular_highlight = True
    return camera


def render(camera, path, location, target=(0.0, 0.0, 1.12)):
    camera.location = location
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def import_obj(path: Path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=str(path), forward_axis="NEGATIVE_Z", up_axis="Y")
    meshes = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"expected one imported garment mesh, got {len(meshes)}")
    garment = meshes[0]
    garment.name = "GarmentCode SMPL Shirt - G9 Fitted"
    return garment


def bridge_smpl_to_g9(garment, body):
    # Blender's OBJ importer performs the SMPL Y-up -> Blender Z-up axis bridge.
    # GarmentCode writes centimetres while its body asset is in metres.
    target = bounds(body)
    target_height = target["max"][2] - target["min"][2]
    uniform_scale = target_height / (SOURCE_SMPL_HEIGHT_M * 100.0)
    garment.scale = (uniform_scale,) * 3
    bpy.context.view_layer.objects.active = garment
    garment.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Both source and target bodies are centred at X=0 and grounded at 0.  Use
    # measured target ground rather than assuming an exact zero.
    fitted = bounds(garment)
    garment.location.x -= (fitted["min"][0] + fitted["max"][0]) / 2.0
    garment.location.z += target["min"][2]
    return {"source_smpl_height_m": SOURCE_SMPL_HEIGHT_M,
            "target_g9_height_m": target_height,
            "uniform_scale_from_obj_cm": uniform_scale,
            "axis_bridge": "SMPL +X,+Y,+Z -> Blender +X,+Z,-Y"}


def collision_state(garment, body):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, depsgraph, epsilon=0.0)
    inside = []
    distances = []
    for index, vertex in enumerate(garment.data.vertices):
        point = garment.matrix_world @ vertex.co
        nearest = bvh.find_nearest(point)
        distances.append(nearest[3] if nearest else math.inf)
        origin = point + Vector((1e-6, 0.0, 0.0))
        hits = 0
        for _ in range(64):
            hit = bvh.ray_cast(origin, Vector((1.0, 0.0, 0.0)), 4.0)
            if hit[0] is None:
                break
            hits += 1
            origin = hit[0] + Vector((1e-5, 0.0, 0.0))
        if hits % 2:
            inside.append(index)
    return bvh, inside, distances


def surface_overlap_pairs(garment, body):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    garment_bvh = BVHTree.FromObject(garment, depsgraph, epsilon=0.0)
    body_bvh = BVHTree.FromObject(body, depsgraph, epsilon=0.0)
    return len(garment_bvh.overlap(body_bvh))


def clear_body_collisions(garment, body, margin):
    bvh, inside, before_distances = collision_state(garment, body)
    original_inside = list(inside)
    overlaps_before = surface_overlap_pairs(garment, body)
    inverse = garment.matrix_world.inverted()
    # First establish explicit clearance for every garment vertex close enough
    # to let an incident triangle cross the body. A vertex-only inside test is
    # insufficient because an edge can intersect while both endpoints remain
    # outside.
    close = {index for index, distance in enumerate(before_distances)
             if distance < margin}
    for index in set(inside) | close:
        point = garment.matrix_world @ garment.data.vertices[index].co
        nearest = bvh.find_nearest(point)
        if nearest:
            location, normal = nearest[0], nearest[1].normalized()
            garment.data.vertices[index].co = inverse @ (location + normal * margin)
    garment.data.update()
    _, inside, _ = collision_state(garment, body)
    passes = 0
    while inside and passes < 6:
        passes += 1
        for index in inside:
            point = garment.matrix_world @ garment.data.vertices[index].co
            nearest = bvh.find_nearest(point)
            if nearest:
                location, normal = nearest[0], nearest[1].normalized()
                # Genesis 9's body winding is outward. Project along its
                # nearest surface normal; choosing solely by unsigned distance
                # can select the equally distant inward candidate.
                garment.data.vertices[index].co = inverse @ (
                    location + normal * margin * passes)
        garment.data.update()
        _, inside, _ = collision_state(garment, body)

    _, remaining, after_distances = collision_state(garment, body)
    overlaps_after = surface_overlap_pairs(garment, body)
    return {"inside_vertices_before": len(original_inside),
            "inside_vertices_after": len(remaining),
            "surface_overlap_pairs_before": overlaps_before,
            "surface_overlap_pairs_after": overlaps_after,
            "vertices_projected_to_clearance": len(set(original_inside) | close),
            "min_surface_distance_before_m": min(before_distances),
            "min_surface_distance_after_m": min(after_distances),
            "margin_m": margin,
            "passes": passes}


def transfer_weights(garment, body, rig):
    for group in body.vertex_groups:
        garment.vertex_groups.new(name=group.name)
    bpy.ops.object.select_all(action="DESELECT")
    garment.select_set(True)
    bpy.context.view_layer.objects.active = garment
    transfer = garment.modifiers.new("G9 nearest-surface weights", "DATA_TRANSFER")
    transfer.object = body
    transfer.use_vert_data = True
    transfer.data_types_verts = {"VGROUP_WEIGHTS"}
    transfer.vert_mapping = "POLYINTERP_NEAREST"
    transfer.layers_vgroup_select_src = "ALL"
    transfer.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.modifier_apply(modifier=transfer.name)

    # Normalize explicitly; interpolation can leave small floating-point drift.
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    armature = garment.modifiers.new("Genesis 9 Armature", "ARMATURE")
    armature.object = rig
    garment.parent = rig
    weighted = normalized = 0
    used_groups = set()
    for vertex in garment.data.vertices:
        total = sum(item.weight for item in vertex.groups if item.weight > 0.0)
        if total > 1e-8:
            weighted += 1
            used_groups.update(item.group for item in vertex.groups if item.weight > 0.0)
        if abs(total - 1.0) <= 1e-3:
            normalized += 1
    return {"vertices": len(garment.data.vertices),
            "weighted_vertices": weighted,
            "normalized_vertices": normalized,
            "available_g9_groups": len(garment.vertex_groups),
            "used_g9_groups": len(used_groups)}


def pose_follow_gate(garment, rig):
    rest_positions = world_points(garment)
    pose = {
        "l_upperarm": (math.radians(12), math.radians(-14), math.radians(-18)),
        "r_upperarm": (math.radians(-9), math.radians(11), math.radians(21)),
        "l_forearm": (math.radians(-18), 0.0, math.radians(-8)),
        "r_forearm": (math.radians(14), 0.0, math.radians(7)),
        "spine2": (0.0, math.radians(7), math.radians(4)),
    }
    for name, rotation in pose.items():
        bone = rig.pose.bones.get(name)
        if bone is None:
            raise RuntimeError(f"target pose bone is absent: {name}")
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = rotation
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = garment.evaluated_get(depsgraph)
    posed_mesh = evaluated.to_mesh()
    posed_positions = [evaluated.matrix_world @ vertex.co for vertex in posed_mesh.vertices]
    displacement = [(posed - rest).length for posed, rest in zip(posed_positions, rest_positions)]
    evaluated.to_mesh_clear()
    return {"bones": list(pose),
            "vertices": len(displacement),
            "vertices_moved_over_1mm": sum(value > 0.001 for value in displacement),
            "mean_vertex_displacement_m": sum(displacement) / len(displacement),
            "max_vertex_displacement_m": max(displacement)}


def main():
    args = parse_args()
    garment_path = Path(args.garment).expanduser().resolve()
    g9_path = Path(args.g9).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not garment_path.is_file() or not g9_path.is_file():
        raise FileNotFoundError("garment and G9 source files must exist")

    bpy.ops.wm.open_mainfile(filepath=str(g9_path))
    body = bpy.data.objects.get(args.body)
    rig = bpy.data.objects.get(args.rig)
    if body is None or body.type != "MESH":
        raise RuntimeError(f"G9 body mesh absent: {args.body}")
    if rig is None or rig.type != "ARMATURE":
        raise RuntimeError(f"G9 rig absent: {args.rig}")

    garment = import_obj(garment_path)
    source_counts = {"vertices": len(garment.data.vertices),
                     "faces": len(garment.data.polygons)}
    coordinate_fit = bridge_smpl_to_g9(garment, body)
    collision = clear_body_collisions(garment, body, args.margin_mm / 1000.0)
    weights = transfer_weights(garment, body, rig)
    rest_bounds = bounds(garment)

    camera = configure_render(body, garment)
    rest_front = out_dir / "rest_front.png"
    rest_back = out_dir / "rest_back.png"
    render(camera, rest_front, (0.0, -3.7, 1.15))
    render(camera, rest_back, (0.0, 3.7, 1.15))

    pose = pose_follow_gate(garment, rig)
    posed_front = out_dir / "posed_front.png"
    posed_back = out_dir / "posed_back.png"
    render(camera, posed_front, (0.0, -3.7, 1.15))
    render(camera, posed_back, (0.0, 3.7, 1.15))

    blend_path = out_dir / "garmentcode_shirt_on_g9_amy.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    report_path = out_dir / "task-2964-g9-transfer.json"
    report = {
        "task_id": 2964,
        "project_id": 735575,
        "ledger_step": 4,
        "source": {"garment": str(garment_path), "sha256": sha256(garment_path),
                   "g9": str(g9_path), "source_counts": source_counts},
        "coordinate_fit": coordinate_fit,
        "rest_bounds_m": rest_bounds,
        "collision": collision,
        "weights": weights,
        "pose_follow": pose,
        "artifacts": {"blend": str(blend_path),
                      "renders": [str(rest_front), str(rest_back),
                                  str(posed_front), str(posed_back)]},
        "gate": {"no_body_interpenetration": (
                     collision["inside_vertices_after"] == 0
                     and collision["surface_overlap_pairs_after"] == 0),
                 "all_vertices_weighted": weights["weighted_vertices"] == weights["vertices"],
                 "all_weights_normalized": weights["normalized_vertices"] == weights["vertices"],
                 "follows_g9_pose": pose["vertices_moved_over_1mm"] > 0},
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report["artifacts"]["blend_sha256"] = sha256(blend_path)
    report["artifacts"]["render_sha256"] = {
        path.name: sha256(path) for path in (rest_front, rest_back, posed_front, posed_back)
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("G9_TRANSFER_OK " + json.dumps(report["gate"], sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

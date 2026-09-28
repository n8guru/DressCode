"""Bind GarmentCode garments draped NATIVELY on a G9 body into that G9 rig.

The drapes were simulated by GarmentCode's Warp solver against the G9 body
itself (exported with export_g9_body_for_garmentcode.py), so no SMPL->G9
registration is needed: the only transform is the exact inverse of the export
frame (cm -> m, GC (x,y,z) -> Blender (x,-z,y), minus the grounding lift).

Per garment (listed inner layer first):
  1. import the sim OBJ in the G9 frame;
  2. FoundryClothThickness route (character-foundry agents/forge/task-93317
     @f760c487): shrinkwrap OUTSIDE 2 mm -> 4 mm GN slab -> OUTSIDE 0.5 mm,
     body as target; outer layers additionally shrinkwrap OUTSIDE 2 mm over
     every already-thickened inner layer;
  3. G9 weights by nearest-surface DataTransfer, restricted for skirts to the
     pelvis/thigh/spine groups and smoothed so the hem does not split between
     the legs; normalized, Armature modifier to the G9 rig;
  4. gates: inside verts (closest-point normal test AND ray parity), BVH
     triangle-overlap pairs vs body and vs every other garment, boundary
     edges, torso COVER (foundry band), pose-follow.

blender -b master.blend --python fit_native_g9_outfit.py -- \
   --garment skirt:/path/skirt_sim.obj --garment shirt:/path/shirt_sim.obj \
   --lift-m 0.054874 --out-dir DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from foundry_cloth_thickness import apply_thickness_route  # noqa: E402

RIG, BODY = "Genesis 9", "Genesis 9 Mesh"
SKIRT_GROUP_PREFIXES = ("pelvis", "hip", "abdomen", "spine1", "spine2",
                        "l_thigh", "r_thigh")
COLORS = {"shirt": (0.86, 0.87, 0.90, 1.0), "skirt": (0.09, 0.13, 0.30, 1.0)}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--garment", action="append", required=True,
                    help="kind:path  (inner layer first)")
    ap.add_argument("--lift-m", type=float, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-thickness", action="store_true")
    return ap.parse_args(argv)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def import_gc_obj(path: Path, name: str, lift: float):
    verts, faces = [], []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            x, y, z = map(float, line.split()[1:4])
            verts.append((x / 100.0, -z / 100.0, y / 100.0 - lift))
        elif line.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def world_tris(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    V = [ev.matrix_world @ v.co for v in me.vertices]
    T = [tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    return V, T


def bvh_of(ob):
    V, T = world_tris(ob)
    return BVHTree.FromPolygons(V, T), V


def boundary_edges(ob):
    c = Counter()
    for p in ob.data.polygons:
        for ek in p.edge_keys:
            c[ek] += 1
    return sum(1 for v in c.values() if v == 1)


def inside_stats(garment, body_bvh):
    V, _ = world_tris(garment)
    nrm_inside = parity_inside = 0
    depth = 0.0
    for p in V:
        loc, nrm, _, dist = body_bvh.find_nearest(p)
        if loc is not None and (p - loc).dot(nrm) < 0.0:
            nrm_inside += 1
            depth = max(depth, dist)
        origin, hits = p + Vector((1e-6, 0, 0)), 0
        for _ in range(64):
            hit = body_bvh.ray_cast(origin, Vector((1, 0, 0)), 4.0)
            if hit[0] is None:
                break
            hits += 1
            origin = hit[0] + Vector((1e-5, 0, 0))
        parity_inside += hits % 2
    return {"inside_verts_normal_test": nrm_inside,
            "inside_verts_ray_parity": parity_inside,
            "max_depth_mm": round(depth * 1000, 3)}


def cover(body, garments):
    verts, polys, off = [], [], 0
    for g in garments:
        V, T = world_tris(g)
        verts += V
        polys += [tuple(i + off for i in t) for t in T]
        off = len(verts)
    bvh = BVHTree.FromPolygons(verts, polys)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    nmat = ev.matrix_world.to_3x3().inverted().transposed()
    total = exposed = 0
    for v in me.vertices:
        co = ev.matrix_world @ v.co
        if not (0.96 <= co.z <= 1.48 and abs(co.x) <= 0.18):
            continue
        n = (nmat @ v.normal).normalized()
        total += 1
        if bvh.ray_cast(co + n * 1e-4, n, 0.08)[0] is None:
            exposed += 1
    ev.to_mesh_clear()
    return {"cover_sampled": total, "cover_exposed": exposed,
            "exposed_fraction": round(exposed / total, 4) if total else None}


def material(kind):
    m = bpy.data.materials.new(f"Dressable {kind.title()} Cloth")
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = COLORS[kind]
    bsdf.inputs["Roughness"].default_value = 0.85
    m.diffuse_color = COLORS[kind]
    return m


def transfer_weights(garment, body, rig, kind):
    for g in body.vertex_groups:
        garment.vertex_groups.new(name=g.name)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = garment
    garment.select_set(True)
    dt = garment.modifiers.new("G9 weights", "DATA_TRANSFER")
    dt.object = body
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.modifier_apply(modifier=dt.name)
    if kind == "skirt":
        # A skirt must not follow each leg rigidly: keep only lower-trunk
        # and thigh influences, then smooth them across the panel so the hem
        # between the legs blends instead of splitting.
        for g in list(garment.vertex_groups):
            if not g.name.startswith(SKIRT_GROUP_PREFIXES):
                garment.vertex_groups.remove(g)
        pelvis = garment.vertex_groups.get("pelvis")
        for v in garment.data.vertices:
            if not any(e.weight > 0 for e in v.groups):
                pelvis.add([v.index], 1.0, "REPLACE")
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL",
                                           factor=0.5, repeat=40, expand=0.0)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=0.001)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # drop empty groups so the wearable only names bones it actually uses
    used_idx = {e.group for v in garment.data.vertices for e in v.groups if e.weight > 0}
    unused = [g.name for g in garment.vertex_groups if g.index not in used_idx]
    for name in unused:  # by name: removal re-indexes the remaining groups
        garment.vertex_groups.remove(garment.vertex_groups[name])
    arm = garment.modifiers.new("Genesis 9 Armature", "ARMATURE")
    arm.object = rig
    # Foundry apply_outfit re-parents with `ob.parent = rig`, which leaves an
    # identity parent-inverse: the wearable must already live in RIG-LOCAL
    # coordinates (the G9 rig carries a 0.938 object scale).  Bake that.
    from mathutils import Matrix
    garment.data.transform(rig.matrix_world.inverted() @ garment.matrix_world)
    garment.parent = rig
    garment.matrix_parent_inverse = Matrix.Identity(4)
    garment.matrix_basis = Matrix.Identity(4)
    garment.data.update()
    weighted = normalized = 0
    for v in garment.data.vertices:
        t = sum(e.weight for e in v.groups if e.weight > 0)
        weighted += t > 1e-8
        normalized += abs(t - 1.0) <= 1e-3
    return {"vertices": len(garment.data.vertices), "weighted": weighted,
            "normalized": normalized, "groups": sorted(g.name for g in garment.vertex_groups)}


def resolve_overlaps(garment, target, step=0.001, iters=40):
    """Push garment verts of every triangle crossing `target` outward.

    Vertex-inside tests miss triangles that slice the target with all three
    corners outside (insight 56023); this clears BVH triangle overlap pairs,
    the sound gate, by moving only the offending triangles' corners along the
    target's nearest-surface normal.
    """
    tb, _ = bvh_of(target)
    mw = garment.matrix_world
    inv = mw.inverted()
    moved = set()
    for it in range(iters):
        me = garment.data
        V = [mw @ v.co for v in me.vertices]
        gb = BVHTree.FromPolygons(V, [tuple(p.vertices) for p in me.polygons])
        pairs = gb.overlap(tb)
        if not pairs:
            return {"iterations": it, "verts_moved": len(moved), "remaining_pairs": 0}
        idx = {vi for pi, _ in pairs for vi in me.polygons[pi].vertices}
        for vi in idx:
            p = V[vi]
            loc, nrm, _, dist = tb.find_nearest(p)
            if loc is None:
                continue
            # push along the target normal by one step; never relocate the
            # vertex onto the nearest point (that tears creases into spikes)
            me.vertices[vi].co = inv @ (p + nrm.normalized() * step)
            moved.add(vi)
        me.update()
    me = garment.data
    V = [mw @ v.co for v in me.vertices]
    gb = BVHTree.FromPolygons(V, [tuple(p.vertices) for p in me.polygons])
    return {"iterations": iters, "verts_moved": len(moved), "remaining_pairs": len(gb.overlap(tb))}


def overlap_pairs(a_bvh, b_bvh):
    return len(a_bvh.overlap(b_bvh))


def measure(body, garments):
    body_bvh, _ = bvh_of(body)
    res = {"per_garment": {}, "garment_garment_overlap_pairs": {}}
    bvhs = {}
    for kind, g in garments.items():
        gb, _ = bvh_of(g)
        bvhs[kind] = gb
        row = inside_stats(g, body_bvh)
        row["body_overlap_pairs"] = overlap_pairs(gb, body_bvh)
        row["boundary_edges"] = boundary_edges(g)
        row["non_interpenetrating"] = (row["inside_verts_normal_test"] == 0
                                       and row["inside_verts_ray_parity"] == 0
                                       and row["body_overlap_pairs"] == 0)
        res["per_garment"][kind] = row
    kinds = list(garments)
    for i in range(len(kinds)):
        for j in range(i + 1, len(kinds)):
            res["garment_garment_overlap_pairs"][f"{kinds[i]}|{kinds[j]}"] = \
                overlap_pairs(bvhs[kinds[i]], bvhs[kinds[j]])
    res["cover"] = cover(body, list(garments.values()))
    return res


def set_pose(rig, pose):
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
    for name, rot in pose.items():
        pb = rig.pose.bones.get(name)
        if pb is None:
            raise RuntimeError(f"pose bone absent: {name}")
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = tuple(math.radians(a) for a in rot)
    bpy.context.view_layer.update()


POSE = {"l_upperarm": (12, -14, -18), "r_upperarm": (-9, 11, 21),
        "l_forearm": (-18, 0, -8), "r_forearm": (14, 0, 7),
        "spine2": (0, 7, 4), "l_thigh": (-12, 0, 0), "r_thigh": (8, 0, 0)}


def render_setup(body, garments):
    for ob in list(bpy.data.objects):
        if ob.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(ob, do_unlink=True)
    keep = {body.name, *[g.name for g in garments], "GoldenPalace_G9 Mesh"}
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.name not in keep:
            ob.hide_render = True
    body.data.materials.clear()
    skin = bpy.data.materials.new("proof skin")
    skin.diffuse_color = (0.62, 0.42, 0.33, 1)
    body.data.materials.append(skin)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = 55
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 700, 1000
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = True
    sc.world.color = (0.05, 0.05, 0.05)
    return cam


def render(cam, path, loc, target=(0, 0, 0.95)):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    a = parse_args()
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        import addon_utils
        addon_utils.enable("import_daz", default_set=True, persistent=True)
    except Exception as e:  # measurement still valid without drivers
        print("WARN import_daz:", e)
    body, rig = bpy.data.objects[BODY], bpy.data.objects[RIG]
    ship_pose_position = rig.data.pose_position  # the state a build ships in
    # Measure against what ships: the GLB export carries the base cage (no
    # subdivision) at rest.  The drape collider was exported the same way.
    for m in body.modifiers:
        if m.type == "SUBSURF":
            m.show_viewport = False
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    garments, sources = {}, {}
    for spec in a.garment:
        kind, path = spec.split(":", 1)
        path = Path(path).resolve()
        name = f"Dressable {kind.title()}"
        garments[kind] = import_gc_obj(path, name, a.lift_m)
        sources[kind] = {"obj": str(path), "sha256": sha256(path),
                         "vertices": len(garments[kind].data.vertices),
                         "faces": len(garments[kind].data.polygons)}
    report = {"sources": sources, "lift_m": a.lift_m,
              "frame": "GC (x,y,z) cm -> Blender (x/100, -z/100, y/100 - lift)"}
    report["before"] = measure(body, garments)
    print("GATES_BEFORE " + json.dumps(report["before"], sort_keys=True), flush=True)
    done = []
    for kind, g in garments.items():
        if not a.no_thickness:
            apply_thickness_route(g, body)
        # Outer layers are NOT shrinkwrapped over inner garments: a closed
        # slab's rim has ambiguous normals, and OUTSIDE mode snapped chest
        # verts onto the skirt waist rim (long spikes).  Only triangles that
        # truly cross an inner layer are pushed, by resolve_overlaps.
        clear = []
        for _round in range(3):
            clear.append({"vs": "body", **resolve_overlaps(g, body)})
            for inner in done:
                clear.append({"vs": inner.name, **resolve_overlaps(g, inner)})
            if all(c["remaining_pairs"] == 0 for c in clear[-(1 + len(done)):]):
                break
        report.setdefault("overlap_clearance", {})[kind] = clear
        done.append(g)
        g.data.materials.clear()  # GN apply leaves an empty slot 0
        g.data.materials.append(material(kind))
    report["after_thickness"] = measure(body, garments)
    print("GATES_AFTER " + json.dumps(report["after_thickness"], sort_keys=True), flush=True)
    report["weights"] = {k: transfer_weights(g, body, rig, k) for k, g in garments.items()}
    for k, g in garments.items():
        g.name = f"Dressable {k.title()}"
        g.data.name = g.name
    report["rest_after_bind"] = measure(body, garments)
    cam = render_setup(body, list(garments.values()))
    renders = {}
    renders["rest_front"] = out / "rest_front.png"
    render(cam, renders["rest_front"], (0, -3.9, 1.0))
    rest = {k: world_tris(g)[0] for k, g in garments.items()}
    # Ship state: the master's own saved pose (DAZ driver bones lift the hip
    # ~57 mm and drive JCMs).  This is what the foundry cover gate and the
    # exported GLB see, so it is gated too.
    rig.data.pose_position = ship_pose_position
    bpy.context.view_layer.update()
    report["ship_state"] = {"pose_position": ship_pose_position,
                            **measure(body, garments)}
    print("GATES_SHIP " + json.dumps(report["ship_state"], sort_keys=True), flush=True)
    for tag, loc in (("ship_front", (0, -3.9, 1.05)), ("ship_back", (0, 3.9, 1.05)),
                     ("ship_side", (3.9, -0.4, 1.05))):
        renders[tag] = out / f"{tag}.png"
        render(cam, renders[tag], loc)
    rig.data.pose_position = "POSE"
    set_pose(rig, POSE)
    moved = {}
    for k, g in garments.items():
        posed = world_tris(g)[0]
        d = [(p - r).length for p, r in zip(posed, rest[k])]
        moved[k] = {"vertices_moved_over_1mm": sum(x > 1e-3 for x in d),
                    "max_displacement_m": round(max(d), 4)}
    report["pose_follow"] = {"pose": POSE, "garments": moved,
                             "posed_gates": measure(body, garments)}
    for tag, loc in (("posed_front", (0, -3.9, 1.0)), ("posed_side", (3.9, -0.4, 1.0))):
        renders[tag] = out / f"{tag}.png"
        render(cam, renders[tag], loc)
    set_pose(rig, {})
    rig.data.pose_position = "REST"
    blend = out / "dressable_g9_outfit.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    rt = report["after_thickness"]
    sh = report["ship_state"]
    report["gate"] = {
        "ship_non_interpenetrating": all(r["non_interpenetrating"] for r in sh["per_garment"].values()),
        "ship_no_garment_garment_overlap": all(v == 0 for v in sh["garment_garment_overlap_pairs"].values()),
        "ship_cover_ok": (sh["cover"]["exposed_fraction"] or 1) <= 0.12,
        "all_non_interpenetrating_rest": all(r["non_interpenetrating"] for r in rt["per_garment"].values()),
        "no_garment_garment_overlap_rest": all(v == 0 for v in rt["garment_garment_overlap_pairs"].values()),
        "closed_slabs": all(r["boundary_edges"] == 0 for r in rt["per_garment"].values()),
        "cover_ok": (rt["cover"]["exposed_fraction"] or 1) <= 0.12,
        "all_weighted_normalized": all(w["weighted"] == w["vertices"] == w["normalized"]
                                       for w in report["weights"].values()),
        "follows_pose": all(m["vertices_moved_over_1mm"] > 0 for m in moved.values()),
    }
    report["artifacts"] = {"blend": str(blend), "blend_sha256": sha256(blend),
                           "renders": {k: {"path": str(p), "sha256": sha256(p)} for k, p in renders.items()}}
    (out / "outfit_fit_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("OUTFIT_FIT_DONE " + json.dumps(report["gate"], sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

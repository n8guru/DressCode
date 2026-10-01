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
import os
import re
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
COLORS = {"shirt": (0.80, 0.52, 0.16, 1.0), "skirt": (0.09, 0.13, 0.30, 1.0),
          "pants": (0.11, 0.19, 0.38, 1.0)}
# task-133934 (operator decision #1988251: "70's bellbottom jeans, and a large
# collar 70's shirt"): trousers follow each leg, so they keep ONLY lower-body
# G9 groups (no hand/forearm pick-up from nearest-surface transfer) and are NOT
# smoothed -- identical-to-body weights keep the fabric offset under any stride.
PANTS_GROUP_PREFIXES = ("pelvis", "hip", "abdomen", "spine1", "l_thigh",
                        "r_thigh", "l_shin", "r_shin", "l_foot", "r_foot",
                        "l_toes", "r_toes", "l_metatarsals", "r_metatarsals")
SHIRT_DROP_PREFIXES = ("l_thigh", "r_thigh", "l_shin", "r_shin", "l_foot",
                       "r_foot", "l_toes", "r_toes", "l_metatarsals",
                       "r_metatarsals")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--garment", action="append", required=True,
                    help="kind:path  (inner layer first)")
    ap.add_argument("--lift-m", type=float, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-thickness", action="store_true")
    # skin clearance before the slab (FoundryClothThickness pre_offset);
    # the step-12 default is 2 mm.  task-133934 uses 5 mm so LBS-vs-JCM skin
    # deviations under pose stay on the outside of the fabric.
    ap.add_argument("--clearance-mm", type=float, default=2.0)
    return ap.parse_args(argv)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def import_gc_obj(path: Path, name: str, lift: float):
    verts, faces, uvs, fuv = [], [], [], []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            x, y, z = map(float, line.split()[1:4])
            verts.append((x / 100.0, -z / 100.0, y / 100.0 - lift))
        elif line.startswith("vt "):
            uvs.append(tuple(map(float, line.split()[1:3])))
        elif line.startswith("f "):
            toks = line.split()[1:]
            faces.append([int(t.split("/")[0]) - 1 for t in toks])
            fuv.append([int(t.split("/")[1]) - 1 if "/" in t and t.split("/")[1] else -1
                        for t in toks])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    # task-134122: keep the GarmentCode pattern UVs (grain-aligned panel
    # layout) so the garments can carry denim / shirting textures.
    if uvs and all(i >= 0 for f in fuv for i in f):
        uvl = me.uv_layers.new(name="UVMap")
        k = 0
        for poly, fu in zip(me.polygons, fuv):
            for li, ui in zip(poly.loop_indices, fu):
                uvl.data[li].uv = uvs[ui]
            k += 1
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
    nrm_inside = parity_inside = parity_majority = 0
    parity_at = []
    depth = 0.0
    for p in V:
        loc, nrm, _, dist = body_bvh.find_nearest(p)
        if loc is not None and (p - loc).dot(nrm) < 0.0:
            nrm_inside += 1
            depth = max(depth, dist)
        hits = ray_hits(body_bvh, p, Vector((1, 0, 0)))
        parity_inside += hits % 2
        if hits % 2:
            # The G9 base cage is OPEN (graft opening, eye/mouth holes), so a
            # single +X ray through an opening flips parity for a point that
            # is outside.  Vote 6 axis rays; a true inside point is odd on
            # (nearly) all of them.
            votes = sum(ray_hits(body_bvh, p, d) % 2 for d in AXES)
            parity_majority += votes >= 4
            if len(parity_at) < 8:
                loc, nrm, _, dist = body_bvh.find_nearest(p)
                parity_at.append({"co": [round(c, 4) for c in p], "hits_+x": hits,
                                  "odd_axis_votes_of_6": votes,
                                  "nearest_body_mm": round(dist * 1000, 2),
                                  "outside_by_normal": bool((p - loc).dot(nrm) >= 0)})
    return {"inside_verts_normal_test": nrm_inside,
            "inside_verts_ray_parity": parity_inside,
            "inside_verts_ray_parity_6axis_majority": parity_majority,
            "ray_parity_inside_samples": parity_at,
            "max_depth_mm": round(depth * 1000, 3)}


AXES = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]


def ray_hits(bvh, p, d):
    origin, hits = p + d * 1e-6, 0
    for _ in range(64):
        hit = bvh.ray_cast(origin, d, 4.0)
        if hit[0] is None:
            break
        hits += 1
        origin = hit[0] + d * 1e-5
    return hits


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


ARM_RE = re.compile(r"^(l|r)_(upperarm|forearm|hand|thumb|index\d|mid\d|ring\d|pinky\d|carpal)")
LEG_RE = re.compile(r"^(l|r)_(thigh|shin|foot|toes|metatarsal|bigtoe|indextoe|midtoe|ringtoe|pinkytoe)")
SIM_LABELS = {}  # garment object name -> (rest world coords, panel labels)


def body_region(body):
    """Per body vertex: 'l_arm' / 'r_arm' / 'leg' / 'torso' by dominant bone."""
    names = {g.index: g.name for g in body.vertex_groups}
    out = []
    for v in body.data.vertices:
        if not v.groups:
            out.append("torso")
            continue
        n = names[max(v.groups, key=lambda e: e.weight).group]
        m = ARM_RE.match(n)
        out.append(f"{m.group(1)}_arm" if m else ("leg" if LEG_RE.match(n) else "torso"))
    return out


def panel_aware_weights(garment, body):
    """Shirt skinning by sewing panel (task-133934).

    Nearest-surface transfer gave loose underarm sleeve fabric TORSO weights
    (the ribs are nearer than the arm in the A-pose rest), so raising or
    swinging the arm dragged sleeve fabric into the arm.  The Warp sim labels
    every vertex with its panel: sleeve-panel vertices now copy the weights of
    the nearest skin vertex of THAT arm; every other panel (torso, collar,
    seams) copies the nearest torso skin vertex.
    """
    from mathutils.kdtree import KDTree
    rest, labels = SIM_LABELS[garment.name]
    lk = KDTree(len(rest))
    for i, p in enumerate(rest):
        lk.insert(p, i)
    lk.balance()
    BV, _ = world_tris(body)
    region = body_region(body)
    trees = {}
    for reg in ("l_arm", "r_arm", "torso"):
        idx = [i for i, r in enumerate(region) if r == reg]
        t = KDTree(len(idx))
        for k, i in enumerate(idx):
            t.insert(BV[i], k)
        t.balance()
        trees[reg] = (t, idx)
    bnames = {g.index: g.name for g in body.vertex_groups}
    gnames = {g.index: g.name for g in garment.vertex_groups}
    gw = garment.matrix_world
    counts = {"l_arm": 0, "r_arm": 0, "torso_override": 0, "kept_interp": 0}
    for v in garment.data.vertices:
        p = gw @ v.co
        lab = labels[lk.find(p)[1]]
        if "sleeve" in lab:
            side = "l" if lab.startswith("left") else "r"
            reg = f"{side}_arm"
            t, idx = trees[reg]
            src = body.data.vertices[idx[t.find(p)[1]]]
            surf = {bnames[e.group]: e.weight for e in src.groups if e.weight > 0}
            tube, f = tube_weights(rig_of(body), side, p)
            mixed = {n: (1 - f) * surf.get(n, 0.0) + f * tube.get(n, 0.0)
                     for n in set(surf) | set(tube)}
            for e in list(v.groups):
                garment.vertex_groups[gnames[e.group]].remove([v.index])
            for n, val in mixed.items():
                if val > 1e-6:
                    (garment.vertex_groups.get(n) or garment.vertex_groups.new(name=n)).add(
                        [v.index], val, "REPLACE")
            counts[reg] += 1
            counts["tube_full"] = counts.get("tube_full", 0) + (f >= 0.999)
            continue
        else:
            # torso/collar/seam fabric keeps the smooth POLYINTERP weights
            # unless they are arm-dominated (underarm fabric nearest the arm)
            arm_w = sum(e.weight for e in v.groups if ARM_RE.match(gnames[e.group]))
            if arm_w <= 0.5:
                counts["kept_interp"] += 1
                continue
            reg = "torso"
        t, idx = trees[reg]
        src = body.data.vertices[idx[t.find(p)[1]]]
        counts["torso_override" if reg == "torso" else reg] += 1
        for e in list(v.groups):
            garment.vertex_groups[gnames[e.group]].remove([v.index])
        for e in src.groups:
            if e.weight > 0:
                garment.vertex_groups[bnames[e.group]].add([v.index], e.weight, "REPLACE")
    return counts


def rig_of(body):
    return bpy.data.objects[RIG]


def _smooth(x, a, b):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def tube_weights(rig, side, p):
    """Loose-sleeve skinning along the ARM AXIS (task-134074).

    Surface-nearest weights gave hanging bell-sleeve fabric the mixed
    shoulder/chest weights of the underarm skin it happens to be nearest, so
    under arms-up the lower sleeve stayed behind as a wing and the sleeve seam
    cut into the arm (task-133934 arms_up20/45: 1011/1501 overlap pairs).  A
    loose sleeve is a tube around the bone chain: its weights depend on WHERE
    ALONG the arm it hangs, not on which skin vertex happens to be closest.
    Returns (tube weights, blend factor): the factor ramps from 0 at the
    shoulder cap (keep the surface weights that match the deltoid skin) to 1
    a third of the way down the upper arm.
    """
    mw = rig.matrix_world
    b = rig.data.bones
    P = [mw @ b[f"{side}_upperarm"].head_local, mw @ b[f"{side}_forearm"].head_local,
         mw @ b[f"{side}_hand"].head_local]
    best = None
    for si in range(2):
        a, c = P[si], P[si + 1]
        ab = c - a
        u = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        d = (a + ab * u - p).length
        if best is None or d < best[0]:
            best = (d, si, u)
    _, si, u = best
    ua, ut1, ut2 = f"{side}_upperarm", f"{side}_upperarmtwist1", f"{side}_upperarmtwist2"
    ft1, ft2 = f"{side}_forearmtwist1", f"{side}_forearmtwist2"
    w = {}
    if si == 0:
        k = _smooth(u, 0.35, 0.75)
        w[ut1] = 1 - k
        w[ut2] = k
        e = _smooth(u, 0.85, 1.0) * 0.5  # elbow: half into the forearm
        if e > 0:
            w = {n: x * (1 - e) for n, x in w.items()}
            w[ft1] = e
        f = _smooth(u, 0.08, 0.35)
    else:
        e = 0.5 * (1 - _smooth(u, 0.0, 0.15))  # elbow: half from the upper arm
        k = _smooth(u, 0.3, 0.8)
        w[ft1] = (1 - k) * (1 - e)
        w[ft2] = k * (1 - e)
        w[ut2] = e
        f = 1.0
    return {n: x for n, x in w.items() if x > 1e-6}, f


def resolve_stitch_labels(ob, labels):
    """Seam vertices carry 'stitch_N' labels; give each the majority panel
    label of its (up to 3-ring) neighbours so the sleeve's underarm seam is
    skinned as sleeve, not torso (task-133934 left it on torso weights)."""
    adj = [[] for _ in ob.data.vertices]
    for e in ob.data.edges:
        a, c = e.vertices
        adj[a].append(c)
        adj[c].append(a)
    out = list(labels)
    for i, lab in enumerate(labels):
        if not lab.startswith("stitch"):
            continue
        ring, seen = {i}, {i}
        for _ in range(3):
            ring = {n for r in ring for n in adj[r]} - seen
            seen |= ring
            votes = Counter(labels[n] for n in ring if not labels[n].startswith("stitch"))
            if votes:
                sleeve = [l for l in votes if "sleeve" in l]
                out[i] = sleeve[0] if sleeve else votes.most_common(1)[0][0]
                break
    return out


def _pant_side(label):
    if label.startswith(("pant_l", "pant_f_l", "pant_b_l")):
        return 1
    if label.startswith(("pant_r", "pant_f_r", "pant_b_r")):
        return -1
    return 0


def tag_leg_sides(ob, raw_labels, resolved):
    """task-135614: stamp each pants vertex with its LEG (+1 l / -1 r / 0
    shared) and whether it is bell-flare fabric, as point attributes, BEFORE
    the thickness slab.  GN extrude + merge and the shrinkwraps carry point
    attributes, so the slab's second shell keeps its leg.  (A nearest-label
    lookup after the slab cannot: the two bells hang 2-3 mm apart at the
    midline, less than the 4 mm slab.)  Seam vertices take their neighbours'
    side unless the seam joins the two legs (crotch / rise seams) -> 0."""
    adj = [set() for _ in ob.data.vertices]
    for e in ob.data.edges:
        a, c = e.vertices
        adj[a].add(c)
        adj[c].add(a)
    side = []
    for i, lab in enumerate(raw_labels):
        s = _pant_side(lab)
        if s == 0 and lab.startswith("stitch"):
            nb = {_pant_side(raw_labels[j]) for j in adj[i]} - {0}
            s = nb.pop() if len(nb) == 1 else 0
        side.append(s)
    flare = [1 if "cuff_skirt" in l else 0 for l in resolved]
    for name, vals in (("gc_leg_side", side), ("gc_flare", flare)):
        at = ob.data.attributes.new(name, "INT", "POINT")
        at.data.foreach_set("value", vals)
    return {"l": side.count(1), "r": side.count(-1), "shared": side.count(0), "flare": sum(flare)}


def _mirror(name):
    return ("r_" + name[2:]) if name.startswith("l_") else ("l_" + name[2:]) if name.startswith("r_") else name


def pants_leg_weights(garment, rig, knee_band=0.07):
    """task-135614 (decision #1997482: 'the knees look funny when bent').

    Nearest-skin transfer let the INNER face of one bell take the OTHER
    leg's calf weights (the bells hang 2-3 mm apart between the ankles) and
    the spring chains split the flare by the sign of x, so in walk/step the
    two bells were sewn together by a stretched sheet, and the hem followed
    the foot.  Now, by the leg each vertex was sewn into:
      * any weight on the other leg's bones moves to the mirror bone;
      * foot/toe weights move to the shin (a hem does not flex with the ankle);
      * bell-flare fabric is a rigid tube on its shin below the knee, blending
        into the surface weights over `knee_band` m above the knee joint, so
        the bent knee folds at the joint instead of shearing the bell.
    """
    gw = garment.matrix_world
    side = [0] * len(garment.data.vertices)
    flare = [0] * len(garment.data.vertices)
    garment.data.attributes["gc_leg_side"].data.foreach_get("value", side)
    garment.data.attributes["gc_flare"].data.foreach_get("value", flare)
    knee = {s: (rig.matrix_world @ rig.data.bones[f"{s}_shin"].head_local).z for s in ("l", "r")}
    names = {g.index: g.name for g in garment.vertex_groups}
    st = Counter()
    for v in garment.data.vertices:
        s = side[v.index]
        cur = {names[e.group]: e.weight for e in v.groups if e.weight > 0}
        new = {}
        sp = "l" if s == 1 else "r" if s == -1 else None
        for n, w in cur.items():
            if sp and n[:2] in ("l_", "r_") and not n.startswith(sp + "_"):
                n = _mirror(n)
                st["mirrored"] += 1
            if re.match(r"^(l|r)_(foot|toes|metatarsals)", n):
                n = n[:2] + "shin"
                st["foot_to_shin"] += 1
            new[n] = new.get(n, 0.0) + w
        if sp and flare[v.index]:
            z = (gw @ v.co).z
            t = 1.0 - _smooth(z, knee[sp] - 0.5 * knee_band, knee[sp] + 0.5 * knee_band)
            if t > 0:
                new = {n: (1 - t) * w for n, w in new.items()}
                new[sp + "_shin"] = new.get(sp + "_shin", 0.0) + t
                st["flare_tube"] += 1
        if new != cur:
            for e in list(v.groups):
                garment.vertex_groups[e.group].remove([v.index])
            for n, w in new.items():
                if w > 1e-6:
                    (garment.vertex_groups.get(n) or garment.vertex_groups.new(name=n)).add(
                        [v.index], w, "REPLACE")
            st["changed"] += 1
    return dict(st)


def blend_over_inner(garment, inner, band=0.02, reach=0.10, above=0.04):
    """Outer layer over an inner garment moves WITH that garment.

    Shirt verts below the inner garment's top take (ramped over `band` m)
    the skin weights of the nearest inner-garment vertex, so under torso twist
    or stride the shirt hem keeps its rest offset over the trousers instead of
    following the body on a different blend and cutting into them.
    """
    from mathutils.kdtree import KDTree
    src = inner[-1]
    sw = src.matrix_world
    SV = [sw @ v.co for v in src.data.vertices]
    top = max(p.z for p in SV)
    kd = KDTree(len(SV))
    for i, p in enumerate(SV):
        kd.insert(p, i)
    kd.balance()
    sname = {g.index: g.name for g in src.vertex_groups}
    gw = garment.matrix_world
    touched = 0
    for v in garment.data.vertices:
        z = (gw @ v.co).z
        # ramp straddles the waistband rim: full inner weights `band` below
        # the rim, fading to body weights `above` it, so fabric just above
        # the rim cannot twist through it
        w = min(1.0, max(0.0, (top + above - z) / (above + band)))
        if w <= 0.0:
            continue
        _, j, dist = kd.find(gw @ v.co)
        if dist > reach:  # only fabric actually lying over the trousers
            continue
        inner_w = {sname[e.group]: e.weight for e in src.data.vertices[j].groups if e.weight > 0}
        cur = {garment.vertex_groups[e.group].name: e.weight for e in v.groups}
        mixed = {n: (1 - w) * cur.get(n, 0.0) + w * inner_w.get(n, 0.0)
                 for n in set(cur) | set(inner_w)}
        for n, val in mixed.items():
            grp = garment.vertex_groups.get(n) or garment.vertex_groups.new(name=n)
            if val > 1e-6:
                grp.add([v.index], val, "REPLACE")
            elif n in cur:
                grp.remove([v.index])
        touched += 1
    return touched


def transfer_weights(garment, body, rig, kind, inner=()):
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
    if kind == "shirt" and garment.name in SIM_LABELS:
        panel_counts = panel_aware_weights(garment, body)
        print("SHIRT_PANEL_WEIGHTS", panel_counts, flush=True)
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
    elif kind in ("pants", "shirt"):
        for g in list(garment.vertex_groups):
            drop = (not g.name.startswith(PANTS_GROUP_PREFIXES)) if kind == "pants" \
                else g.name.startswith(SHIRT_DROP_PREFIXES)
            if drop:
                garment.vertex_groups.remove(g)
        fallback = garment.vertex_groups.get("pelvis")
        for v in garment.data.vertices:
            if not any(e.weight > 0 for e in v.groups):
                fallback.add([v.index], 1.0, "REPLACE")
        if kind == "pants" and "gc_leg_side" in garment.data.attributes:
            print("PANTS_LEG_WEIGHTS " + json.dumps(pants_leg_weights(garment, rig)), flush=True)
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        lim = int(os.environ.get("FIT_LIMIT", "4"))
        if lim:
            bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=lim)
        bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=0.001)
        bpy.ops.object.mode_set(mode="OBJECT")
        if kind == "shirt" and inner:
            blend_over_inner(garment, inner)
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
            bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
            bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # drop empty groups so the wearable only names bones it actually uses
    used_idx = {e.group for v in garment.data.vertices for e in v.groups if e.weight > 0}
    unused = [g.name for g in garment.vertex_groups if g.index not in used_idx]
    for name in unused:  # by name: removal re-indexes the remaining groups
        garment.vertex_groups.remove(garment.vertex_groups[name])
    # Amy's active pose correctives: none of the 171 *_cbs_* keys is non-zero
    # in any gated pose (they belong to BodyHeavy/Pear/... shape morphs set to
    # 0), so transfer is opt-in to keep the wearable free of dead morphs.
    correctives = (transfer_correctives(garment, body)
                   if os.environ.get("FIT_CORRECTIVES") else {"transferred": 0,
                                                              "note": "opt-in; no active body correctives"})
    arm = garment.modifiers.new("Genesis 9 Armature", "ARMATURE")
    arm.object = rig
    # The G9 body's SkinBinding deforms with Preserve Volume (dual quaternion).
    # task-133934 bound the garments LBS: identical weights, different
    # blending, so at 80 deg hip flex the LBS-collapsed jeans sat 30 mm inside
    # the DQS glutes.  Match the body's skinning mode (task-134074).
    body_arm = next(m for m in body.modifiers if m.type == "ARMATURE")
    arm.use_deform_preserve_volume = body_arm.use_deform_preserve_volume
    # Foundry apply_outfit re-parents with `ob.parent = rig`, which leaves an
    # identity parent-inverse: the wearable must already live in RIG-LOCAL
    # coordinates (the G9 rig carries a 0.938 object scale).  Bake that.
    from mathutils import Matrix
    garment.data.transform(rig.matrix_world.inverted() @ garment.matrix_world,
                           shape_keys=True)
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
            "normalized": normalized, "correctives": correctives, "groups": sorted(g.name for g in garment.vertex_groups)}


CORRECTIVE_TAG = "_cbs_"


def transfer_correctives(garment, body, min_mm=0.5):
    """DAZ-style auto-follow of the body's pose correctives (task-134074).

    G9 carries driven corrective shape keys (*_cbs_*: thigh_x115n, shoulder
    _z55, upperarm_z90 ...) that reshape glutes / hip crease / deltoid under
    pose.  A garment skinned with LBS alone does not get them, so sitting put
    the glutes 30 mm through the jeans.  Each garment vertex is bound to its
    nearest body triangle at rest; every corrective whose barycentric delta
    moves some garment vertex >= min_mm becomes a garment shape key with the
    SAME driver, so the fabric keeps its rest offset over the corrected skin.
    """
    sk = body.data.shape_keys
    if not sk or not sk.animation_data:
        return {"transferred": 0}
    drivers = {d.data_path: d for d in sk.animation_data.drivers}
    keys = [kb for kb in sk.key_blocks[1:] if CORRECTIVE_TAG in kb.name
            and f'key_blocks["{kb.name}"].value' in drivers]
    basis = sk.reference_key
    me = body.data
    me.calc_loop_triangles()
    bw = body.matrix_world
    RV = [bw @ v.co for v in basis.data]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    bvh = BVHTree.FromPolygons(RV, tris)
    from mathutils.geometry import barycentric_transform  # noqa: F401
    from mathutils.geometry import intersect_point_tri
    gw = garment.matrix_world
    ginv3 = gw.to_3x3().inverted()
    bind = []
    for v in garment.data.vertices:
        loc, _, fi, _ = bvh.find_nearest(gw @ v.co)
        a, b, c = tris[fi]
        pa, pb, pc = RV[a], RV[b], RV[c]
        # barycentric of loc in (pa, pb, pc)
        v0, v1, v2 = pb - pa, pc - pa, loc - pa
        d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
        d20, d21 = v2.dot(v0), v2.dot(v1)
        den = d00 * d11 - d01 * d01 or 1e-12
        wb = (d11 * d20 - d01 * d21) / den
        wc = (d00 * d21 - d01 * d20) / den
        bind.append((a, b, c, 1 - wb - wc, wb, wc))
    b3 = bw.to_3x3()
    if garment.data.shape_keys is None:
        garment.shape_key_add(name="Basis", from_mix=False)
    gsk = garment.data.shape_keys
    made = []
    for kb in keys:
        D = [b3 @ (kb.data[i].co - basis.data[i].co) for i in range(len(basis.data))]
        deltas = []
        mx = 0.0
        for a, b, c, wa, wb, wc in bind:
            d = D[a] * wa + D[b] * wb + D[c] * wc
            deltas.append(d)
            mx = max(mx, d.length)
        if mx * 1000 < min_mm:
            continue
        nk = garment.shape_key_add(name=kb.name, from_mix=False)
        nk.slider_min, nk.slider_max = kb.slider_min, kb.slider_max
        for gv, d in zip(nk.data, deltas):
            gv.co = gv.co + ginv3 @ d
        if gsk.animation_data is None:
            gsk.animation_data_create()
        gsk.animation_data.drivers.from_existing(src_driver=drivers[f'key_blocks["{kb.name}"].value'])
        made.append({"key": kb.name, "max_mm": round(mx * 1000, 2)})
    return {"candidates": len(keys), "transferred": len(made),
            "keys": sorted(made, key=lambda r: -r["max_mm"])[:40]}


SPRING_PREFIX = "cloth_"


def add_spring_chains(rig, garments, shirt_labels):
    """Provider-authored secondary-motion bones (task-134074, criterion 4).

    Foundry assets.secondary_motion can only drive bones that exist on the
    build rig; the jeans' bell flares and the shirt's big collar points are
    the loose regions, so the wearable brings its own chains:
      cloth_pants_{l,r}_flare_{0,1}  children of {l,r}_shin (knee -> hem)
      cloth_shirt_{l,r}_collar_{0,1} children of spine4 (collar root -> tip)
    Every spring bone is a child of the G9 bone whose weight it replaces, so
    with the spring at rest (identity) the skinning is identical and every
    posed gate is unchanged; wind rotates only the spring.
    """
    from mathutils.kdtree import KDTree
    mwi = rig.matrix_world.inverted()
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    chains = {}
    plans = []
    # --- jeans flares -----------------------------------------------------
    pants = garments.get("pants")
    if pants is not None:
        for side in ("l", "r"):
            shin = rig.data.bones[f"{side}_shin"]
            a = rig.matrix_world @ shin.head_local
            b = rig.matrix_world @ shin.tail_local
            def at(z):
                t = (a.z - z) / (a.z - b.z)
                return a.lerp(b, t)
            z0, z1, z2 = 0.30, 0.17, 0.04
            names = [f"{SPRING_PREFIX}pants_{side}_flare_0", f"{SPRING_PREFIX}pants_{side}_flare_1"]
            plans.append((names[0], f"{side}_shin", at(z0), at(z1)))
            plans.append((names[1], names[0], at(z1), at(z2)))
            chains[f"jeans_flare_{side}"] = {"bones": names, "garment": "pants",
                                             "zone": (side, z0, z1, z2, f"{side}_shin")}
    # --- shirt collar points ---------------------------------------------
    shirt = garments.get("shirt")
    if shirt is not None and shirt_labels is not None:
        rest, labels = shirt_labels
        for side, lab in (("l", "left_collar_front"), ("r", "right_collar_front")):
            pts = [p for p, l in zip(rest, labels) if l == lab]
            zs = sorted(p.z for p in pts)
            ztop, ztip = zs[-1], zs[0]
            def band(lo, hi):
                sel = [p for p in pts if lo <= p.z <= hi] or pts
                c = Vector()
                for p in sel:
                    c += p
                return c / len(sel)
            h = ztop - ztip
            root = band(ztop - 0.25 * h, ztop)
            mid = band(ztip + 0.35 * h, ztip + 0.55 * h)
            tip = band(ztip, ztip + 0.12 * h)
            names = [f"{SPRING_PREFIX}shirt_{side}_collar_0", f"{SPRING_PREFIX}shirt_{side}_collar_1"]
            plans.append((names[0], "spine4", root, mid))
            plans.append((names[1], names[0], mid, tip))
            chains[f"shirt_collar_{side}"] = {"bones": names, "garment": "shirt",
                                              "zone": (side, lab, root, mid, tip)}
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    for name, parent, h, t in plans:
        bone = eb.get(name) or eb.new(name)
        bone.head = mwi @ h
        bone.tail = mwi @ t
        bone.roll = 0.0
        bone.parent = eb[parent]
        bone.use_connect = False
        bone.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    # --- weights ------------------------------------------------------------
    stats = {}
    if pants is not None:
        names = {g.index: g.name for g in pants.vertex_groups}
        pw = pants.matrix_world
        for cid in ("jeans_flare_l", "jeans_flare_r"):
            side, z0, z1, z2, shin = chains[cid]["zone"]
            b0, b1 = chains[cid]["bones"]
            g0 = pants.vertex_groups.get(b0) or pants.vertex_groups.new(name=b0)
            g1 = pants.vertex_groups.get(b1) or pants.vertex_groups.new(name=b1)
            gs = pants.vertex_groups[shin]
            n = 0
            legs = None
            if "gc_leg_side" in pants.data.attributes:  # task-135614: sewn leg, not sign of x
                legs = [0] * len(pants.data.vertices)
                pants.data.attributes["gc_leg_side"].data.foreach_get("value", legs)
            for v in pants.data.vertices:
                p = pw @ v.co
                on_side = (legs[v.index] == (1 if side == "l" else -1)) if legs and legs[v.index] \
                    else ((p.x > 0) == (side == "l"))
                if p.z > z0 or not on_side:
                    continue
                w_shin = sum(e.weight for e in v.groups if names[e.group] == shin)
                if w_shin <= 0:
                    continue
                f = 0.85 * _smooth(z0 - p.z, 0.0, z0 - z1)  # 0 at knee band
                k = _smooth(z1 - p.z, 0.0, z1 - z2)         # share on the tip bone
                moved = w_shin * f
                gs.add([v.index], w_shin - moved, "REPLACE")
                if moved * (1 - k) > 1e-6:
                    g0.add([v.index], moved * (1 - k), "REPLACE")
                if moved * k > 1e-6:
                    g1.add([v.index], moved * k, "REPLACE")
                n += 1
            stats[cid] = n
    if shirt is not None and shirt_labels is not None:
        rest, labels = shirt_labels
        kd = KDTree(len(rest))
        for i, p in enumerate(rest):
            kd.insert(p, i)
        kd.balance()
        sw = shirt.matrix_world
        for cid in ("shirt_collar_l", "shirt_collar_r"):
            side, lab, root, mid, tip = chains[cid]["zone"]
            b0, b1 = chains[cid]["bones"]
            g0 = shirt.vertex_groups.get(b0) or shirt.vertex_groups.new(name=b0)
            g1 = shirt.vertex_groups.get(b1) or shirt.vertex_groups.new(name=b1)
            axis = tip - root
            n = 0
            for v in shirt.data.vertices:
                p = sw @ v.co
                _, j, d = kd.find(p)
                if labels[j] != lab or d > 0.02:
                    continue
                u = max(0.0, min(1.0, (p - root).dot(axis) / axis.length_squared))
                f = 0.8 * _smooth(u, 0.15, 0.6)
                if f <= 1e-4:
                    continue
                k = _smooth(u, 0.45, 0.9)
                for e in list(v.groups):
                    shirt.vertex_groups[e.group].add([v.index], e.weight * (1 - f), "REPLACE")
                g0.add([v.index], f * (1 - k), "ADD")
                if f * k > 1e-6:
                    g1.add([v.index], f * k, "ADD")
                n += 1
            stats[cid] = n
    return {cid: {"bones": c["bones"], "garment": c["garment"],
                  "weighted_vertices": stats.get(cid, 0)} for cid, c in chains.items()}


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


def ensure_margin(garment, target, margin=0.003):
    """Outer layer: keep >= `margin` from an inner garment at rest (task-133934).

    resolve_overlaps stops at "touching"; a zero rest gap lets tiny skin-weight
    differences under pose re-cross.  Only vertices already outside and closer
    than `margin` move, along the inner surface normal, by the shortfall.
    """
    tb, _ = bvh_of(target)
    mw = garment.matrix_world
    inv = mw.inverted()
    moved = 0
    for v in garment.data.vertices:
        p = mw @ v.co
        loc, nrm, _, dist = tb.find_nearest(p)
        if loc is None or dist >= margin or (p - loc).dot(nrm) < 0:
            continue
        v.co = inv @ (loc + nrm.normalized() * margin)
        moved += 1
    garment.data.update()
    return moved


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
        # +X single-ray parity is kept verbatim for comparability; the gate
        # uses the 6-axis majority (the G9 cage is open -- see inside_stats).
        row["non_interpenetrating"] = (row["inside_verts_normal_test"] == 0
                                       and row["inside_verts_ray_parity_6axis_majority"] == 0
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
# >=3 independent posed frames (pass criterion 2).  Bone axes probed on this
# rig (scripts/probe133934.py): upperarm X+ = swing forward, l Z+ / r Z- =
# raise; thigh X- = forward, shin X+ = knee flex; spine Y = twist.
# "stride_133870" is the exact task-133870 recorded pose (thighs -12/+8 AND
# both upper arms ADDUCTED 18-21 deg toward the ribs) that failed the skirt.
POSES = {
    # GATED frames (pass criterion 2 names walk / sit / arms-up):
    "walk": {"l_thigh": (-20, 0, 0), "r_thigh": (15, 0, 0), "r_shin": (25, 0, 0),
             "spine1": (0, 4, 0), "l_upperarm": (-12, 0, 0), "r_upperarm": (12, 0, 0)},
    "sit": {"l_thigh": (-80, 0, 0), "r_thigh": (-80, 0, 0),
            "l_shin": (80, 0, 0), "r_shin": (80, 0, 0)},
    "arms_up45": {"l_upperarm": (0, 0, 45), "r_upperarm": (0, 0, -45),
                  "l_forearm": (0, 0, 10), "r_forearm": (0, 0, -10)},
    "arms_up20": {"l_upperarm": (0, 0, 20), "r_upperarm": (0, 0, -20)},
    "arms_swing15": {"l_upperarm": (15, 0, 0), "r_upperarm": (-15, 0, 0)},
    "arms_swing15b": {"l_upperarm": (-15, 0, 0), "r_upperarm": (15, 0, 0)},
    "step_twist": {"l_thigh": (-25, 0, -4), "l_shin": (30, 0, 0),
                   "r_thigh": (10, 0, 0), "spine1": (0, 6, 0), "spine2": (0, 6, 0)},
    "weight_shift": {"l_thigh": (0, 0, -8), "r_thigh": (-6, 0, 4),
                     "r_shin": (12, 0, 0)},
    # DIAGNOSTIC: sit angles the fit_sit corrective was NOT authored at
    "sit55": {"l_thigh": (-55, 0, 0), "r_thigh": (-55, 0, 0),
              "l_shin": (65, 0, 0), "r_shin": (65, 0, 0)},
    "sit70": {"l_thigh": (-70, 0, 0), "r_thigh": (-70, 0, 0),
              "l_shin": (75, 0, 0), "r_shin": (75, 0, 0)},
    "sit40": {"l_thigh": (-40, 0, 0), "r_thigh": (-40, 0, 0),
              "l_shin": (50, 0, 0), "r_shin": (50, 0, 0)},
    "sit47": {"l_thigh": (-47, 0, 0), "r_thigh": (-47, 0, 0),
              "l_shin": (55, 0, 0), "r_shin": (55, 0, 0)},
    "sit60": {"l_thigh": (-60, 0, 0), "r_thigh": (-60, 0, 0),
              "l_shin": (70, 0, 0), "r_shin": (70, 0, 0)},
    "sit95": {"l_thigh": (-95, 0, 0), "r_thigh": (-95, 0, 0),
              "l_shin": (90, 0, 0), "r_shin": (90, 0, 0)},
    # DIAGNOSTIC (reported, not gated): the task-133870 stride with both upper
    # arms ADDUCTED 18-21 deg into the ribs -- a loose sleeve there needs
    # cloth collision, which LBS cannot express.
    "stride_133870": POSE,
}
GATED = ("walk", "sit", "arms_up45", "arms_up20", "arms_swing15", "arms_swing15b",
         "step_twist", "weight_shift", "sit40", "sit55", "sit70")


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
    if os.environ.get("FIT_NORENDER"):
        return
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
        seg = path.parent / (path.stem + "_segmentation.txt")
        if seg.exists():
            labels = [l.strip() for l in seg.read_text().splitlines()]
            if len(labels) == len(garments[kind].data.vertices):
                raw = labels
                labels = resolve_stitch_labels(garments[kind], labels)
                if kind == "pants":
                    print("LEG_SIDES " + json.dumps(tag_leg_sides(garments[kind], raw, labels)), flush=True)
                SIM_LABELS[garments[kind].name] = (
                    [v.co.copy() for v in garments[kind].data.vertices], labels)
        sources[kind] = {"obj": str(path), "sha256": sha256(path),
                         "vertices": len(garments[kind].data.vertices),
                         "faces": len(garments[kind].data.polygons)}
    report = {"sources": sources, "lift_m": a.lift_m, "clearance_mm": a.clearance_mm,
              "frame": "GC (x,y,z) cm -> Blender (x/100, -z/100, y/100 - lift)"}
    report["before"] = measure(body, garments)
    print("GATES_BEFORE " + json.dumps(report["before"], sort_keys=True), flush=True)
    done = []
    for kind, g in garments.items():
        if not a.no_thickness:
            apply_thickness_route(g, body, pre_offset=a.clearance_mm / 1000.0)
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
        for inner in done:
            clear.append({"vs": inner.name, "margin_mm": 3,
                          "margin_verts_moved": ensure_margin(g, inner)})
            clear.append({"vs": inner.name, **resolve_overlaps(g, inner)})
        report.setdefault("overlap_clearance", {})[kind] = clear
        done.append(g)
        g.data.materials.clear()  # GN apply leaves an empty slot 0
        g.data.materials.append(material(kind))
    report["after_thickness"] = measure(body, garments)
    print("GATES_AFTER " + json.dumps(report["after_thickness"], sort_keys=True), flush=True)
    report["weights"] = {}
    bound = []
    for k, g in garments.items():
        report["weights"][k] = transfer_weights(g, body, rig, k, inner=list(bound))
        bound.append(g)
    for k, g in garments.items():
        g.name = f"Dressable {k.title()}"
        g.data.name = g.name
    shirt_labels = SIM_LABELS.get(garments["shirt"].name) if "shirt" in garments else None
    if shirt_labels is None and "shirt" in garments:
        shirt_labels = next(iter(v for k2, v in SIM_LABELS.items() if "Shirt" in k2), None)
    report["secondary_bones"] = add_spring_chains(rig, garments, shirt_labels)
    print("SECONDARY_BONES " + json.dumps(report["secondary_bones"]), flush=True)
    import pose_correctives as PC
    rig.data.pose_position = "POSE"
    report["pose_correctives"] = {"sit": PC.author(
        rig, body, garments, set_pose, POSES["sit"],
        {"name": "fit_sit", "drivers": {"l": ("l_thigh", "X", 80, "-"),
                                        "r": ("r_thigh", "X", 80, "-")}})}
    # in-between at 55 deg (a chair-height sit): fit_sit is half on there and
    # this key, a hat peaking at 55 and zero at 30 / 80, closes the gap.
    report["pose_correctives"]["sit55"] = PC.author(
        rig, body, garments, set_pose, POSES["sit55"],
        {"name": "fit_sit55", "hat": 25, "drivers": {"l": ("l_thigh", "X", 55, "-"),
                                                     "r": ("r_thigh", "X", 55, "-")}})
    report["pose_correctives"]["sit40"] = PC.author(
        rig, body, garments, set_pose, POSES["sit40"],
        {"name": "fit_sit40", "hat": 12, "drivers": {"l": ("l_thigh", "X", 40, "-"),
                                                     "r": ("r_thigh", "X", 40, "-")}})
    # arm swing (walk cycle): upper arm swinging forward / back past ~5 deg
    # presses the loose sleeve's inner face into the lat; one key per side and
    # direction.  Upperarm X+ = forward on l, X- = forward on r (probe).
    report["pose_correctives"]["swing_a"] = PC.author(
        rig, body, garments, set_pose, POSES["arms_swing15"],
        {"name": "fit_swing_a", "onset": 5, "drivers": {"l": ("l_upperarm", "X", 15, "+"),
                                                        "r": ("r_upperarm", "X", 15, "-")}})
    report["pose_correctives"]["swing_b"] = PC.author(
        rig, body, garments, set_pose, POSES["arms_swing15b"],
        {"name": "fit_swing_b", "onset": 5, "drivers": {"l": ("l_upperarm", "X", 15, "-"),
                                                        "r": ("r_upperarm", "X", 15, "+")}})
    print("POSE_CORRECTIVES " + json.dumps({k: v["keys"] for k, v in report["pose_correctives"].items()}), flush=True)
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    report["rest_after_bind"] = measure(body, garments)
    print("GATES_REST_AFTER_BIND " + json.dumps(report["rest_after_bind"], sort_keys=True), flush=True)
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
    report["posed_frames"] = {}
    moved = {}
    only = [x for x in os.environ.get("FIT_POSES", "").split(",") if x]
    for pname, pose in POSES.items():
        if only and pname not in only:
            continue
        set_pose(rig, pose)
        pm = {}
        for k, g in garments.items():
            posed = world_tris(g)[0]
            d = [(p - r).length for p, r in zip(posed, rest[k])]
            pm[k] = {"vertices_moved_over_1mm": sum(x > 1e-3 for x in d),
                     "max_displacement_m": round(max(d), 4)}
        moved[pname] = pm
        gates = measure(body, garments)
        report["posed_frames"][pname] = {"pose": pose, "garments_moved": pm,
                                         "gates": gates}
        print(f"GATES_POSED_{pname} " + json.dumps(gates, sort_keys=True), flush=True)
        for tag, loc in ((f"posed_{pname}_front", (0, -3.9, 1.0)),
                         (f"posed_{pname}_side", (3.9, -0.4, 1.0))):
            renders[tag] = out / f"{tag}.png"
            render(cam, renders[tag], loc)
    moved = {k: {"vertices_moved_over_1mm": max(moved[p][k]["vertices_moved_over_1mm"] for p in moved)}
             for k in garments}
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
        "gated_posed_frames": list(GATED),
        "posed_non_interpenetrating_gated_frames": all(
            r["non_interpenetrating"] for n, f in report["posed_frames"].items() if n in GATED
            for r in f["gates"]["per_garment"].values()),
        "posed_no_garment_garment_overlap_gated_frames": all(
            v == 0 for n, f in report["posed_frames"].items() if n in GATED
            for v in f["gates"]["garment_garment_overlap_pairs"].values()),
        "diagnostic_frames_non_interpenetrating": {
            n: {k: r["non_interpenetrating"] for k, r in f["gates"]["per_garment"].items()}
            for n, f in report["posed_frames"].items() if n not in GATED},
    }
    report["artifacts"] = {"blend": str(blend), "blend_sha256": sha256(blend),
                           "renders": {k: {"path": str(p), "sha256": sha256(p)} for k, p in renders.items()
                                       if p.exists()}}
    (out / "outfit_fit_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("OUTFIT_FIT_DONE " + json.dumps(report["gate"], sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

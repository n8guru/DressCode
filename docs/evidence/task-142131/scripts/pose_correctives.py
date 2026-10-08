"""Garment pose-space correctives (task-134074, dressable-g9 step 15).

DAZ ships its own garments with pose-driven corrective morphs ("auto-follow"
JCMs) because skinning alone cannot keep cloth outside a folding joint.  The
generated wearables have none, so a deep hip flex (sit) pushed the glutes and
the thigh backs through the jeans even with identical, dual-quaternion
weights.  This authors the equivalent: at a named key pose the garment is
pushed out of the body (and outer layers out of inner layers) to a margin,
the displacement is softened over a radius so no vertex spikes, mapped back
through the per-vertex skinning matrix into rest space, split left/right,
and stored as shape keys driven by the SAME bone rotation that makes the
pose.  At rest the drivers are 0 and the wearable is bit-identical.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def _posed(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    V = [ev.matrix_world @ v.co for v in me.vertices]
    me.calc_loop_triangles()
    T = [tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    return V, T


def _skin_matrices(garment, rig):
    """Per-vertex armature-space LBS matrix (rest -> pose)."""
    S = {}
    for pb in rig.pose.bones:
        S[pb.name] = pb.matrix @ pb.bone.matrix_local.inverted()
    names = {g.index: g.name for g in garment.vertex_groups}
    out = []
    for v in garment.data.vertices:
        m = Matrix(((0, 0, 0, 0),) * 4)
        tot = 0.0
        for e in v.groups:
            n = names[e.group]
            if e.weight > 0 and n in S:
                m = m + S[n] * e.weight
                tot += e.weight
        out.append(m if tot > 0 else Matrix.Identity(4))
    return out


def _required_push(V, T, body_bvh, inner_bvhs, margin, rest_clear, overshoot=1.5):
    """Posed-space push per offending vertex.

    Body: a vertex closer than its allowance (min(margin, its own rest
    clearance - 0.5 mm)) moves out along the body normal.  Inner garments:
    a closed 4 mm slab has an inner face whose normal points at the body, so
    nearest-surface normals are ambiguous; instead cast along the OUTWARD
    BODY normal and, if any inner-garment surface lies further out, move
    past the last one + 2 mm.
    """
    push = {}
    gb = BVHTree.FromPolygons(V, T)
    nrm = {}
    for i, p in enumerate(V):
        loc, n, _, d = body_bvh.find_nearest(p)
        if loc is None:
            continue
        n = n.normalized()
        nrm[i] = n
        s = (p - loc).dot(n)
        allow = min(margin, max(0.0005, rest_clear[i] - 0.0005))
        if s < allow:
            push[i] = n * ((allow - s) * overshoot)
    for tb in inner_bvhs:
        for i, p in enumerate(V):
            n = nrm.get(i)
            if n is None:
                continue
            o, last = p + n * 1e-5, None
            for _ in range(16):
                hit = tb.ray_cast(o, n, 0.05)
                if hit[0] is None:
                    break
                last = hit[0]
                o = hit[0] + n * 1e-5
            if last is not None:
                need = (last - p) + n * 0.002 * overshoot
                if i not in push or need.length > push[i].length:
                    push[i] = need
    for tb in [body_bvh, *inner_bvhs]:
        for ti, _ in gb.overlap(tb):
            for i in T[ti]:
                if i not in push and i in nrm:
                    push[i] = nrm[i] * 0.002
    return push


def _soften(V, push, radius):
    """Every vertex within `radius` of an offender takes the offender's push,
    faded by a smooth falloff; the strongest contribution wins (no averaging
    down of the required clearance)."""
    if not push:
        return {}
    kd = KDTree(len(push))
    keys = list(push)
    for k, i in enumerate(keys):
        kd.insert(V[i], k)
    kd.balance()
    out = {}
    for j, p in enumerate(V):
        best = None
        for _, k, d in kd.find_range(p, radius):
            f = 1.0 - d / radius
            f = f * f * (3 - 2 * f)
            c = push[keys[k]] * f
            if best is None or c.length > best.length:
                best = c
        if best is not None and best.length > 1e-6:
            out[j] = best
    return out


def _relax(g, k, passes):
    """Laplacian-relax the corrective's delta field over mesh edges so a push
    is carried by the surrounding cloth instead of tenting single vertices
    (the un-relaxed field left crumpled spikes on the shirt hem at the lap).
    Relaxing can re-open clearance; the author loop re-pushes, so the loop
    converges to a smooth field that clears."""
    if passes <= 0:
        return
    basis = g.data.shape_keys.reference_key
    n = len(basis.data)
    D = [k.data[i].co - basis.data[i].co for i in range(n)]
    adj = [[] for _ in range(n)]
    for e in g.data.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    for _ in range(passes):
        N = []
        for i in range(n):
            if not adj[i]:
                N.append(D[i])
                continue
            m = Vector()
            for j in adj[i]:
                m += D[j]
            m /= len(adj[i])
            N.append(D[i] * 0.5 + m * 0.5)
        D = N
    for i in range(n):
        k.data[i].co = basis.data[i].co + D[i]


def _driver(key_block, rig, bone, axis, full_deg, sign, onset_deg=30.0, hat=None):
    fc = key_block.driver_add("value")
    drv = fc.driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "a"
    var.type = "TRANSFORMS"
    t = var.targets[0]
    t.id = rig
    t.bone_target = bone
    t.transform_type = f"ROT_{axis}"
    t.transform_space = "LOCAL_SPACE"
    t.rotation_mode = "XYZ"
    # onset: below `onset_deg` (walking strides) the corrective is fully off,
    # so everyday poses keep the plain skinned fit that already clears.
    lo, hi = math.radians(onset_deg), math.radians(full_deg)
    drv.expression = f"max(0.0, min(1.0, ({sign}a - {lo:.6f}) / {hi - lo:.6f}))"
    if hat:  # in-between corrective: 1 at full_deg, 0 at full_deg +- hat
        drv.expression = (f"max(0.0, 1.0 - abs({sign}a - {hi:.6f}) / "
                          f"{math.radians(hat):.6f})")
    return drv.expression


def author(rig, body, garments, set_pose, pose, spec, margin=0.004, radius=0.03,
           iters=int(__import__('os').environ.get('PC_ITERS', '6'))):
    """spec: {"name": "fit_sit", "split_x": True,
              "drivers": {"l": ("l_thigh", "X", 80, "-"), "r": (...)}}
    garments: ordered inner -> outer dict kind -> object."""
    rig.data.pose_position = "POSE"
    set_pose(rig, pose)
    keys = {}
    for kind, g in garments.items():
        if g.data.shape_keys is None:
            g.shape_key_add(name="Basis", from_mix=False)
        k = g.shape_key_add(name=spec["name"], from_mix=False)
        k.value = 1.0
        keys[kind] = k
    bpy.context.view_layer.update()
    log = []
    done = []
    # rest clearance per vertex (drivers off: pose_position REST)
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    for k in keys.values():
        k.value = 0.0
    RB, RT = _posed(body)
    rbvh = BVHTree.FromPolygons(RB, RT)
    rest_clear = {}
    for kind, g in garments.items():
        rest_clear[kind] = [rbvh.find_nearest(p)[3] for p in _posed(g)[0]]
    for k in keys.values():
        k.value = 1.0
    rig.data.pose_position = "POSE"
    set_pose(rig, pose)
    for kind, g in garments.items():
        k = keys[kind]
        inv3 = rig.matrix_world.inverted().to_3x3()
        for it in range(iters):
            BV, BT = _posed(body)
            inner_bvhs = []
            for inner in done:
                IV, IT = _posed(inner)
                inner_bvhs.append(BVHTree.FromPolygons(IV, IT))
            V, T = _posed(g)
            push = _required_push(V, T, BVHTree.FromPolygons(BV, BT), inner_bvhs,
                                  margin, rest_clear[kind])
            from collections import Counter
            hist = Counter((round(V[i].z, 1), "back" if V[i].y > 0.05 else ("front" if V[i].y < -0.05 else "mid"))
                           for i in push)
            log.append({"garment": kind, "iter": it, "offenders": len(push),
                        "where": sorted(hist.items())})
            if not push:
                break
            soft = _soften(V, push, radius)
            M = _skin_matrices(g, rig)
            for j, d in soft.items():
                d_arm = inv3 @ d
                try:
                    d_rest = M[j].to_3x3().inverted() @ d_arm
                except ValueError:
                    d_rest = d_arm
                k.data[j].co = k.data[j].co + d_rest
            # relax while the field forms; the last 40% are pure local pushes
            if it < 0.6 * iters:
                _relax(g, k, int(__import__("os").environ.get("PC_RELAX", "4")))
            g.data.update()
            bpy.context.view_layer.update()
        done.append(g)
    # split left/right and drive
    out = {"pose": {b: list(r) for b, r in pose.items()}, "margin_mm": margin * 1000,
           "radius_mm": radius * 1000, "log": log, "keys": {}}
    for kind, g in garments.items():
        k = keys[kind]
        basis = g.data.shape_keys.reference_key
        deltas = [k.data[i].co - basis.data[i].co for i in range(len(basis.data))]
        moved = sum(d.length > 1e-4 for d in deltas)
        mx = max((d.length for d in deltas), default=0.0)
        g.shape_key_remove(k)
        made = []
        if moved:
            for side, (bone, axis, full, sign) in spec["drivers"].items():
                nk = g.shape_key_add(name=f"{spec['name']}_{side}", from_mix=False)
                for i, d in enumerate(deltas):
                    x = basis.data[i].co.x
                    t = min(1.0, max(0.0, (x + 0.02) / 0.04))
                    w = t * t * (3 - 2 * t)
                    w = w if side == "l" else 1.0 - w
                    nk.data[i].co = basis.data[i].co + d * w
                expr = _driver(nk, rig, bone, axis, full, sign, hat=spec.get("hat"),
                               onset_deg=spec.get("onset", 30.0))
                made.append({"key": nk.name, "driver": f"{bone}.ROT_{axis} {expr}"})
        out["keys"][kind] = {"vertices_moved": moved, "max_mm": round(mx * 1000, 2),
                             "shape_keys": made}
    set_pose(rig, {})
    bpy.context.view_layer.update()
    return out

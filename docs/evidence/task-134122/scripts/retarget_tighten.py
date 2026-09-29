"""task-134122 (dressable-g9 s15, operator decision #1994543): retarget the
task-133934 GarmentCode drapes from the amy_gp_v3 body onto the amy_a08_v3
identity master (the current best Amy: face A08, sheet-fit body, dense
copper groom) and take in the fit the operator asked for:

  * jeans skin-tight through the waistband, hips, butt and upper legs down
    to the knee; the bell flare below the knee is kept as draped;
  * shirt taken in at the torso and sleeves (fitted 70s shirt), collar kept.

Deterministic, no re-simulation.  Every drape vertex is bound to its nearest
gp_v3 body triangle (barycentric + signed normal offset).  Both bodies are
the same Genesis 9 cage (25182 verts, same triangles), so the binding is
replayed on the a08 body.  The offset is compressed in the tight zone, then
a Laplacian relax (weighted by the tight zone) with a minimum-offset clamp
bridges the gluteal cleft / crotch the way stretch denim does, instead of
following every concavity.  Vertex order, faces and UVs are unchanged, so
the GarmentCode panel segmentation and pattern UVs stay valid.

blender -b amy_a08_v3_master.blend --python retarget_tighten.py -- \
   --gp-blend amy_gp_v3_master.blend --lift-m 0.054874 --out-dir DIR \
   --garment pants:jeans_sim.obj --garment shirt:shirt_sim.obj
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

RIG, BODY = "Genesis 9", "Genesis 9 Mesh"


def args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--gp-blend", required=True)
    ap.add_argument("--lift-m", type=float, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--garment", action="append", required=True)
    ap.add_argument("--jeans-ease-mm", type=float, default=2.5)
    ap.add_argument("--jeans-keep", type=float, default=0.06)
    ap.add_argument("--shirt-ease-mm", type=float, default=9.0)
    ap.add_argument("--shirt-keep", type=float, default=0.35)
    ap.add_argument("--sleeve-ease-mm", type=float, default=12.0)
    ap.add_argument("--sleeve-keep", type=float, default=0.5)
    ap.add_argument("--relax-iters", type=int, default=12)
    ap.add_argument("--shirt-relax", type=float, default=0.3)
    ap.add_argument("--jeans-relax-iters", type=int, default=4)
    ap.add_argument("--flare-smooth", type=float, default=0.35)
    ap.add_argument("--flare-iters", type=int, default=8)
    ap.add_argument("--fill-iters", type=int, default=0,
                    help="fill body concavities (gluteal cleft, crotch) before placing tight fabric")
    ap.add_argument("--over-jeans-ease-mm", type=float, default=24.0)
    return ap.parse_args(argv)


def rest_cage(body, rig):
    for m in body.modifiers:
        if m.type == "SUBSURF":
            m.show_viewport = False
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    V = [ev.matrix_world @ v.co for v in me.vertices]
    T = [tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    return V, T


def load_gp(path):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in (BODY, RIG)]
    body = next(o for o in dst.objects if o.type == "MESH")
    rig = next(o for o in dst.objects if o.type == "ARMATURE")
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
    for m in body.modifiers:
        if m.type == "ARMATURE":
            m.object = rig
    return body, rig


def read_obj(path):
    lines = path.read_text().splitlines()
    V, faces = [], []
    for ln in lines:
        if ln.startswith("v "):
            V.append([float(t) for t in ln.split()[1:4]])
        elif ln.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in ln.split()[1:]])
    return lines, np.array(V), faces


def gc_to_bl(V, lift):
    return np.stack([V[:, 0] / 100.0, -V[:, 2] / 100.0, V[:, 1] / 100.0 - lift], 1)


def bl_to_gc(P, lift):
    return np.stack([P[:, 0] * 100.0, (P[:, 2] + lift) * 100.0, -P[:, 1] * 100.0], 1)


def bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01 or 1e-12
    wb = (d11 * d20 - d01 * d21) / den
    wc = (d00 * d21 - d01 * d20) / den
    return 1 - wb - wc, wb, wc


def tri_normal(a, b, c):
    return (b - a).cross(c - a).normalized()


def adjacency(n, faces):
    adj = [set() for _ in range(n)]
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            adj[a].add(b)
            adj[b].add(a)
    return [np.array(sorted(s)) for s in adj]


def diffuse(w, adj, iters):
    w = w.copy()
    for _ in range(iters):
        w = np.array([0.5 * w[i] + 0.5 * w[a].mean() if len(a) else w[i]
                      for i, a in enumerate(adj)])
    return w


def zone_weights(kind, labels, adj):
    """1 = tight zone, 0 = keep the drape.  Labels: GarmentCode panels."""
    if kind == "pants":
        # pant_{f,b}_{l,r}: hip-to-knee panels; wb_*: waistband;
        # pant_*_cuff_skirt_*: the bell flare below the knee (kept).
        base = np.array([0.0 if "cuff_skirt" in l else 1.0 for l in labels])
        sleeve = None
    else:
        base = np.array([0.5 if "collar" in l else 1.0 for l in labels])
        sleeve = np.array([1.0 if "sleeve" in l else 0.0 for l in labels])
    # stitch labels sit on seams: majority of their neighbours
    for i, l in enumerate(labels):
        if l.startswith("stitch") and len(adj[i]):
            nb = [base[j] for j in adj[i] if not labels[j].startswith("stitch")]
            if nb:
                base[i] = float(np.mean(nb) >= 0.5)
    w = diffuse(base, adj, 25)
    if sleeve is not None:
        sleeve = diffuse(sleeve, adj, 10)
    return w, sleeve


def main():
    a = args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    body, rig = bpy.data.objects[BODY], bpy.data.objects[RIG]
    A, T = rest_cage(body, rig)
    gbody, grig = load_gp(a.gp_blend)
    G, T2 = rest_cage(gbody, grig)
    assert len(A) == len(G), "bodies are not the same G9 cage"
    same = sum(1 for x, y in zip(T, T2) if x == y)
    print("CAGE tris", len(T), len(T2), "identical", same, flush=True)
    pa = [tuple(p.vertices) for p in body.data.polygons]
    pg = [tuple(p.vertices) for p in gbody.data.polygons]
    print("CAGE polys equal", pa == pg, len(pa), len(pg), flush=True)
    assert pa == pg
    gbvh = BVHTree.FromPolygons(G, T)
    abvh = BVHTree.FromPolygons(A, T)
    # Stretch denim spans concavities instead of following them: the tight
    # fabric is placed on a FILLED copy of the a08 body whose concave regions
    # (gluteal cleft, crotch, lumbar dip) are raised to a Laplacian-smoothed
    # hull; convex regions keep the true surface.  Penetration is still
    # clamped against the true body.
    Af = A
    if a.fill_iters:
        nb = [set() for _ in A]
        for t in T:
            for i in range(3):
                nb[t[i]].update((t[(i + 1) % 3], t[(i + 2) % 3]))
        nb = [np.array(sorted(x)) for x in nb]
        An = np.array([tuple(v) for v in A])
        body.data.calc_normals_split() if hasattr(body.data, "calc_normals_split") else None
        # vertex normals of the rest cage (area-weighted from triangles)
        N = np.zeros_like(An)
        for t in T:
            n = np.cross(An[t[1]] - An[t[0]], An[t[2]] - An[t[0]])
            for i in t:
                N[i] += n
        N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
        S = An.copy()
        zone = (An[:, 2] > 0.55) & (An[:, 2] < 1.12)
        for _ in range(a.fill_iters):
            avg = np.array([S[n].mean(0) if len(n) else S[i] for i, n in enumerate(nb)])
            S[zone] = 0.5 * S[zone] + 0.5 * avg[zone]
        d = np.einsum("ij,ij->i", S - An, N)
        fill = np.where(zone & (d > 0), d, 0.0)
        Af = [Vector(tuple(v)) for v in An + N * fill[:, None]]
        report_fill = {"verts_raised": int((fill > 0.0005).sum()), "max_fill_mm": round(float(fill.max()) * 1000, 1)}
        print("FILL", report_fill, flush=True)
    jeans_top = None
    report = {"target_body": bpy.data.filepath, "gp_body": a.gp_blend, "params": vars(a),
              "garments": {}}
    for spec in a.garment:
        kind, path = spec.split(":", 1)
        path = Path(path)
        lines, Vgc, faces = read_obj(path)
        P = gc_to_bl(Vgc, a.lift_m)
        seg = path.parent / (path.stem + "_segmentation.txt")
        labels = [l.strip() for l in seg.read_text().splitlines()]
        assert len(labels) == len(P)
        adj = adjacency(len(P), faces)
        w, sleeve = zone_weights(kind, labels, adj)
        if kind == "pants":
            ease = np.full(len(P), a.jeans_ease_mm / 1000.0)
            keep = np.full(len(P), a.jeans_keep)
        else:
            s = sleeve
            ease = (1 - s) * a.shirt_ease_mm / 1000.0 + s * a.sleeve_ease_mm / 1000.0
            keep = (1 - s) * a.shirt_keep + s * a.sleeve_keep
            if jeans_top is not None:
                # shirt fabric lying over the jeans keeps room for the
                # jeans slab (5 mm clearance + 4 mm slab) plus a margin
                zj = P[:, 2]
                ramp = np.clip((jeans_top + 0.04 - zj) / 0.05, 0.0, 1.0) * (1 - s)
                ease = np.maximum(ease, ramp * a.over_jeans_ease_mm / 1000.0)
        Q = np.zeros_like(P)
        off0 = np.zeros(len(P))
        off1 = np.zeros(len(P))
        for i, p in enumerate(P):
            pv = Vector(p)
            loc, _n, fi, _d = gbvh.find_nearest(pv)
            ta, tb, tc = T[fi]
            ga, gb, gc = G[ta], G[tb], G[tc]
            ba, bb, bc = bary(loc, ga, gb, gc)
            s0 = (pv - loc).dot(tri_normal(ga, gb, gc))
            s_t = ease[i] + max(0.0, s0 - ease[i]) * keep[i] if s0 > ease[i] else s0
            s1 = (1 - w[i]) * s0 + w[i] * s_t
            if w[i] > 0.02 and Af is not A:
                fa, fb, fc = Af[ta], Af[tb], Af[tc]
                qf = fa * ba + fb * bb + fc * bc + tri_normal(fa, fb, fc) * s1
                aa, ab, ac = A[ta], A[tb], A[tc]
                qa = aa * ba + ab * bb + ac * bc + tri_normal(aa, ab, ac) * s1
                q = qa.lerp(qf, w[i])
            else:
                aa, ab, ac = A[ta], A[tb], A[tc]
                q = aa * ba + ab * bb + ac * bc + tri_normal(aa, ab, ac) * s1
            Q[i] = q
            off0[i], off1[i] = s0, s1
        # relax: bridge concavities (cleft, crotch, spine) in the tight zone
        min_off = np.minimum(ease, 0.002) if kind == "pants" else 0.85 * ease
        lam = 0.5 * w * (1.0 if kind == "pants" else a.shirt_relax)
        # open hems/cuffs/collar edges must not contract (a Laplacian on a
        # boundary ring pulls it inward through the body)
        from collections import Counter
        ec = Counter()
        for f in faces:
            for k in range(len(f)):
                ec[tuple(sorted((f[k], f[(k + 1) % len(f)])))] += 1
        bnd = {v for e, c in ec.items() if c == 1 for v in e}
        for v in bnd:
            lam[v] = 0.0
        Q_pre = Q.copy()
        iters = a.jeans_relax_iters if kind == "pants" else a.relax_iters
        if kind == "pants":
            # the bell flare below the knee: light Laplacian smoothing takes
            # out the small drape lumps and keeps the large hanging folds
            lf = a.flare_smooth * (1 - w)
            for v in bnd:
                lf[v] = 0.0
            for _ in range(a.flare_iters):
                avg = np.array([Q[n].mean(0) if len(n) else Q[i] for i, n in enumerate(adj)])
                Q = Q + lf[:, None] * (avg - Q)
            Q_pre = Q.copy()
        for _ in range(iters):
            avg = np.array([Q[n].mean(0) if len(n) else Q[i] for i, n in enumerate(adj)])
            Q = Q + lam[:, None] * (avg - Q)
            for i in np.nonzero(w > 0.02)[0]:
                qv = Vector(Q[i])
                loc, nrm, _, _ = abvh.find_nearest(qv)
                s = (qv - loc).dot(nrm)
                if s < min_off[i]:
                    Q[i] = np.array(loc + nrm * min_off[i])
        # guard: any vertex the relax (or the replay) left INSIDE the body by
        # 6-axis ray-parity majority is restored to its pre-relax position
        axes = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
        def hits(p, d):
            o, h = p + d * 1e-6, 0
            for _ in range(64):
                r = abvh.ray_cast(o, d, 4.0)
                if r[0] is None:
                    break
                h += 1
                o = r[0] + d * 1e-5
            return h
        restored = 0
        for i in range(len(Q)):
            qv = Vector(Q[i])
            if sum(hits(qv, d) % 2 for d in axes) >= 4:
                Q[i] = Q_pre[i]
                restored += 1
        still = sum(1 for q in Q if sum(hits(Vector(q), d) % 2 for d in axes) >= 4)
        print("GUARD", kind, "restored", restored, "still_inside", still, flush=True)
        # final signed offsets on the a08 body
        fin = []
        for q in Q:
            qv = Vector(q)
            loc, nrm, _, _ = abvh.find_nearest(qv)
            fin.append((qv - loc).dot(nrm))
        fin = np.array(fin)
        tight = w > 0.9
        if kind == "pants":
            jeans_top = float(Q[:, 2].max())
            report["jeans_top_z"] = jeans_top
        Vout = bl_to_gc(Q, a.lift_m)
        vi = 0
        dst = out / path.name
        with dst.open("w") as f:
            for ln in lines:
                if ln.startswith("v "):
                    x, y, z = Vout[vi]
                    f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
                    vi += 1
                elif ln.startswith("mtllib"):
                    continue
                else:
                    f.write(ln + "\n")
        shutil.copy(seg, out / seg.name)
        report["garments"][kind] = {
            "source_obj": str(path), "out_obj": str(dst), "vertices": len(P),
            "tight_zone_vertices": int(tight.sum()),
            "offset_mm_tight_zone_before": {"median": round(float(np.median(off0[tight])) * 1000, 2),
                                            "p90": round(float(np.percentile(off0[tight], 90)) * 1000, 2)},
            "offset_mm_tight_zone_after": {"median": round(float(np.median(fin[tight])) * 1000, 2),
                                           "p90": round(float(np.percentile(fin[tight], 90)) * 1000, 2),
                                           "min": round(float(fin[tight].min()) * 1000, 2)},
            "offset_mm_rest_after": {"median": round(float(np.median(fin[~tight])) * 1000, 2)
                                     if (~tight).any() else None},
        }
        print("RETARGET", kind, json.dumps(report["garments"][kind]), flush=True)
    (out / "retarget_report.json").write_text(json.dumps(report, indent=2))
    print("RETARGET_DONE", flush=True)


main()

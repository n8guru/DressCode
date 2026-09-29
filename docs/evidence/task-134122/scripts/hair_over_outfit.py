"""Lay the character's hair OVER an applied outfit (dressable-g9 s15, task-134122).

A groom authored on the nude body passes UNDER any collar / yoke that is
added later: long hair falling over the shoulders ends up inside the shirt.
Run after apply_outfit.py on the build blend; edits in place.

In the REST pose, every hair point / hair-card vertex lying inside the shell
of an outfit garment (between the skin and the garment's outer surface, below
the head bone) is moved out along the skin-to-point ray to `--clear-mm` over
the outer surface.  Native Curves strands carry the push down the strand with
decay so they bend instead of kinking; card meshes move per vertex.  Nothing
above the head bone (scalp, parting, crown) moves.  Garments are untouched.

Marker: ``HAIR_CLEAR_OK curves_points=<n> strands=<n> card_verts=<n>``
(``curves_points=0 card_verts=0`` is a valid no-op for short hair).

blender -b with_outfit.blend --python hair_over_outfit.py -- \
    --object "Dressable Shirt" [--object ...] [--clear-mm 3] [--report r.json]
"""
import argparse
import json
import re
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

RIG, BODY = "Genesis 9", "Genesis 9 Mesh"
HAIR_RE = re.compile(r"hair|groom|lock|wave|card|fringe|bang|ponytail", re.I)
NOT_HAIR_RE = re.compile(r"eyebrow|eyelash|brow|scalp", re.I)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--object", action="append", dest="objects", required=True)
    ap.add_argument("--clear-mm", type=float, default=3.0)
    ap.add_argument("--report", default=None)
    return ap.parse_args(argv)


def bvh(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    V = [ev.matrix_world @ v.co for v in me.vertices]
    T = [tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    return BVHTree.FromPolygons(V, T) if T else None


def main():
    a = parse()
    clear = a.clear_mm / 1000.0
    rig = bpy.data.objects[RIG]
    body = bpy.data.objects[BODY]
    prev = rig.data.pose_position
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    shells = [b for b in (bvh(bpy.data.objects[n], dg) for n in a.objects
                          if n in bpy.data.objects) if b is not None]
    bodyb = bvh(body, dg)
    # nothing above the garments' top moves (scalp, parting, crown)
    zlim = -1e9
    for n in a.objects:
        ob_ = bpy.data.objects.get(n)
        if ob_ is not None:
            zlim = max(zlim, max((ob_.matrix_world @ v.co).z for v in ob_.data.vertices) + 0.01)

    def crossing(p0, p1):
        """segment p0->p1 enters a garment: return push for p1 (to p0's side)"""
        seg = p1 - p0
        L = seg.length
        if L < 1e-7 or p1.z > zlim:
            return None
        dv = seg / L
        for sh in shells:
            hit = sh.ray_cast(p0 + dv * 1e-6, dv, L)
            if hit[0] is not None:
                n = hit[1]
                side = 1.0 if (p0 - hit[0]).dot(n) >= 0 else -1.0
                target = hit[0] + n * side * clear
                # place p1 on p0's side of the fabric, keep its tangential position
                off = (p1 - hit[0]).dot(n)
                return n * (side * clear - off) if side * off < clear else None
        return None

    def push(p):
        if p.z > zlim:
            return None
        bl, bn, _, _ = bodyb.find_nearest(p)
        if bl is None:
            return None
        dirv = p - bl
        dirv = bn.copy() if dirv.length < 1e-6 else dirv.normalized()
        best = None
        for sh in shells:
            loc, _, _, d = sh.find_nearest(p)
            if loc is None or d > 0.06:
                continue
            far, o = None, p + dirv * 1e-5
            for _ in range(8):
                hit = sh.ray_cast(o, dirv, 0.08)
                if hit[0] is None:
                    break
                far = hit[0]
                o = hit[0] + dirv * 1e-5
            if far is not None:
                d_ = (far + dirv * clear) - p
                if best is None or d_.length > best.length:
                    best = d_
        return best

    rep = {"garments": a.objects, "clear_mm": a.clear_mm, "curves": {}, "cards": {}}
    for ob in bpy.data.objects:
        if ob.hide_viewport and ob.hide_render:
            continue
        if ob.type == "CURVES":
            mw, mi = ob.matrix_world, ob.matrix_world.inverted()
            pos = ob.data.attributes["position"].data
            offs = ob.data.curve_offset_data
            moved = strands = 0
            mx = 0.0
            for c in range(len(ob.data.curves)):
                s0, s1 = offs[c].value, offs[c + 1].value
                carry, hit = Vector(), False
                prevp = None
                for i in range(s0, s1):
                    p = mw @ Vector(pos[i].vector) + carry
                    d = push(p)
                    if d is None and prevp is not None:
                        d = crossing(prevp, p)
                    if d is not None:
                        carry = carry + d
                        p = p + d
                        moved += 1
                        hit = True
                        mx = max(mx, carry.length)
                    else:
                        carry = carry * 0.85
                    pos[i].vector = mi @ p
                    prevp = p
                strands += hit
            ob.data.update_tag()
            rep["curves"][ob.name] = {"points_moved": moved, "strands_touched": strands,
                                      "max_push_mm": round(mx * 1000, 1)}
        elif ob.type == "MESH" and ob.parent is rig and HAIR_RE.search(ob.name) \
                and not NOT_HAIR_RE.search(ob.name) and ob.name not in a.objects:
            mw, mi = ob.matrix_world, ob.matrix_world.inverted()
            sk = ob.data.shape_keys
            n = 0
            for v in ob.data.vertices:
                p = mw @ v.co
                d = push(p)
                if d is not None:
                    dl = mi.to_3x3() @ d
                    v.co = v.co + dl
                    if sk:
                        for kb in sk.key_blocks:
                            kb.data[v.index].co = kb.data[v.index].co + dl
                    n += 1
            ob.data.update()
            rep["cards"][ob.name] = {"verts_moved": n, "verts": len(ob.data.vertices)}
    rig.data.pose_position = prev
    bpy.ops.wm.save_mainfile()
    cp = sum(r["points_moved"] for r in rep["curves"].values())
    st = sum(r["strands_touched"] for r in rep["curves"].values())
    cv = sum(r["verts_moved"] for r in rep["cards"].values())
    if a.report:
        with open(a.report, "w") as fh:
            json.dump(rep, fh, indent=2)
    print("HAIR_CLEAR_OK curves_points=%d strands=%d card_verts=%d" % (cp, st, cv), flush=True)


if __name__ == "__main__":
    main()

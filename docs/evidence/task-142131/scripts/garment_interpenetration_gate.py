"""Sound garment/body interpenetration verdict.

ErrorLog 45648 / dressable-g9 step 4: a 0-inside-vertices ray-parity (or
closest-point) test can PASS while garment and body triangles still cross.
Task 3186 measured this on the task-2909 rest-pose: 0 inside verts, 1,544
BVHTree.overlap pairs. The same class still reproduces on the current
FoundryClothThickness after.blend (0 inside, 24 overlap pairs).

Ray parity / vertex-inside is necessary but not sufficient. A garment
triangle can slice the body with every corner outside. The proof of
non-interpenetration is:

    inside_verts == 0 AND triangle_overlap_pairs == 0

``triangle_overlap_pairs`` is what Blender's BVHTree.overlap counts. This
module is the blender-free contract the pytest suite pins; the Blender
measurement script (measure_garment_gates.py) reports the same verdict.
"""
from __future__ import annotations

from typing import Iterable, Sequence


Vec3 = tuple[float, float, float]
Tri = tuple[Vec3, Vec3, Vec3]


def non_interpenetrating(*, inside_verts: int, overlap_pairs: int) -> bool:
    """True only when no verts are inside AND no triangles cross.

    The legacy step-4 gate used ``inside_verts == 0`` alone. That is the
    unsound predicate this helper exists to replace.
    """
    return int(inside_verts or 0) == 0 and int(overlap_pairs or 0) == 0


def legacy_inside_only_ok(*, inside_verts: int) -> bool:
    """The unsound gate: 0 inside verts, ignoring surface crossings."""
    return int(inside_verts or 0) == 0


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _seg_hits_tri(p0: Vec3, p1: Vec3, tri: Tri, eps: float = 1e-10) -> bool:
    """Möller–Trumbore: open segment (p0, p1) vs triangle. Endpoints excluded."""
    v0, v1, v2 = tri
    edge1 = _sub(v1, v0)
    edge2 = _sub(v2, v0)
    direction = _sub(p1, p0)
    pvec = _cross(direction, edge2)
    det = _dot(edge1, pvec)
    if abs(det) < eps:
        return False
    inv = 1.0 / det
    tvec = _sub(p0, v0)
    u = _dot(tvec, pvec) * inv
    if u < -eps or u > 1.0 + eps:
        return False
    qvec = _cross(tvec, edge1)
    v = _dot(direction, qvec) * inv
    if v < -eps or u + v > 1.0 + eps:
        return False
    t = _dot(edge2, qvec) * inv
    return eps < t < 1.0 - eps


def _orient2(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proj2(p: Vec3, axis: int) -> tuple[float, float]:
    if axis == 0:
        return (p[1], p[2])
    if axis == 1:
        return (p[0], p[2])
    return (p[0], p[1])


def _point_in_tri2(p, a, b, c, eps: float = 1e-12) -> bool:
    o1 = _orient2(a, b, p)
    o2 = _orient2(b, c, p)
    o3 = _orient2(c, a, p)
    has_neg = (o1 < -eps) or (o2 < -eps) or (o3 < -eps)
    has_pos = (o1 > eps) or (o2 > eps) or (o3 > eps)
    return not (has_neg and has_pos)


def _seg_seg2(a, b, c, d, eps: float = 1e-12) -> bool:
    o1 = _orient2(a, b, c)
    o2 = _orient2(a, b, d)
    o3 = _orient2(c, d, a)
    o4 = _orient2(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    ):
        return True
    return False


def _coplanar_overlap(a: Tri, b: Tri, normal: Vec3) -> bool:
    axis = max(range(3), key=lambda i: abs(normal[i]))
    a2 = [_proj2(p, axis) for p in a]
    b2 = [_proj2(p, axis) for p in b]
    for i in range(3):
        if _seg_seg2(a2[i], a2[(i + 1) % 3], b2[i % 3], b2[(i + 1) % 3]):
            return True
        for j in range(3):
            if _seg_seg2(a2[i], a2[(i + 1) % 3], b2[j], b2[(j + 1) % 3]):
                return True
    if any(_point_in_tri2(p, *b2) for p in a2):
        return True
    if any(_point_in_tri2(p, *a2) for p in b2):
        return True
    return False


def triangles_intersect(a: Sequence[Vec3], b: Sequence[Vec3], eps: float = 1e-10) -> bool:
    """True when two triangles cross, including coplanar area overlap."""
    ta: Tri = (tuple(a[0]), tuple(a[1]), tuple(a[2]))  # type: ignore[assignment]
    tb: Tri = (tuple(b[0]), tuple(b[1]), tuple(b[2]))  # type: ignore[assignment]
    for i in range(3):
        if _seg_hits_tri(ta[i], ta[(i + 1) % 3], tb, eps=eps):
            return True
        if _seg_hits_tri(tb[i], tb[(i + 1) % 3], ta, eps=eps):
            return True
    n = _cross(_sub(ta[1], ta[0]), _sub(ta[2], ta[0]))
    if _dot(n, n) < eps * eps:
        return False
    d0 = _dot(n, _sub(tb[0], ta[0]))
    d1 = _dot(n, _sub(tb[1], ta[0]))
    d2 = _dot(n, _sub(tb[2], ta[0]))
    if abs(d0) < 1e-8 and abs(d1) < 1e-8 and abs(d2) < 1e-8:
        return _coplanar_overlap(ta, tb, n)
    return False


def count_triangle_overlaps(
    verts_a: Sequence[Vec3],
    faces_a: Iterable[Sequence[int]],
    verts_b: Sequence[Vec3],
    faces_b: Iterable[Sequence[int]],
) -> int:
    """Brute-force triangle/triangle overlap count (small test meshes)."""
    tris_a = [tuple(verts_a[i] for i in face) for face in faces_a]
    tris_b = [tuple(verts_b[i] for i in face) for face in faces_b]
    n = 0
    for ta in tris_a:
        for tb in tris_b:
            if triangles_intersect(ta, tb):
                n += 1
    return n


def point_in_aabb(p: Vec3, lo: Vec3, hi: Vec3, eps: float = 1e-12) -> bool:
    return all(lo[i] + eps < p[i] < hi[i] - eps for i in range(3))


def unit_cube_mesh() -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    """Axis-aligned unit cube [0,1]^3 as 12 triangles."""
    v = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
    ]
    faces = [
        (0, 1, 2), (0, 2, 3),
        (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1),
        (2, 6, 7), (2, 7, 3),
        (0, 3, 7), (0, 7, 4),
        (1, 5, 6), (1, 6, 2),
    ]
    return v, faces


def slicing_quad_through_unit_cube() -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    """Four vertices ALL outside the cube; the quad still slices z=0.5.

    This is the task-3186 class: 0 inside vertices, positive triangle overlap.
    """
    v = [
        (-0.25, -0.25, 0.5),
        (1.25, -0.25, 0.5),
        (1.25, 1.25, 0.5),
        (-0.25, 1.25, 0.5),
    ]
    faces = [(0, 1, 2), (0, 2, 3)]
    return v, faces

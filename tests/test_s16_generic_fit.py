"""dressable-g9 step 16 (task 142131): the generic fit-code changes.

Pure helpers run under any python; the resolve_overlaps direction test runs
inside headless Blender when `blender` is on PATH (skipped otherwise)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "docs/evidence/task-142131/scripts"
sys.path.insert(0, str(SCRIPTS))
import garment_chain_math as M  # noqa: E402


class ChainMath(unittest.TestCase):
    def test_hem_plan_from_extent(self):
        z0, z1, z2 = M.skirt_hem_plan(1.10, 0.50)
        self.assertAlmostEqual(z0, 0.80)
        self.assertAlmostEqual(z1, 0.65)
        self.assertAlmostEqual(z2, 0.50)
        with self.assertRaises(ValueError):
            M.skirt_hem_plan(0.5, 0.5)

    def test_shift_conserves_weight(self):
        z0, z1, z2 = M.skirt_hem_plan(1.10, 0.50)
        for w in (0.0, 0.3, 1.0):
            for z in (1.0, 0.8, 0.7, 0.65, 0.55, 0.5):
                p, a, b = M.chain_shift(w, z, z0, z1, z2)
                self.assertAlmostEqual(p + a + b, w, places=12)
                self.assertGreaterEqual(min(p, a, b), 0.0)
        self.assertEqual(M.chain_shift(1.0, 0.9, z0, z1, z2), (1.0, 0.0, 0.0))
        p, a, b = M.chain_shift(1.0, z2, z0, z1, z2)
        self.assertAlmostEqual(a, 0.0)
        self.assertAlmostEqual(b, 0.85)

    def test_chain_labels_default_is_step15(self):
        self.assertEqual(M.parse_chain_labels(None),
                         {"l": "left_collar_front", "r": "right_collar_front"})
        self.assertEqual(M.parse_chain_labels(["l=left_hood", "r=right_hood"]),
                         {"l": "left_hood", "r": "right_hood"})
        with self.assertRaises(ValueError):
            M.parse_chain_labels(["x=foo"])


BLENDER_PROBE = r'''
import bpy, bmesh, json, sys
sys.path.insert(0, sys.argv[-1])
import fit_native_g9_outfit as F
def sphere(name, r, flip=False):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=r)
    if flip:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob
body = sphere("body", 0.100)
# an inner garment SLAB: outer shell r=.110 (normals out) + inner shell r=.104 (normals in)
outer = sphere("slab_o", 0.110); inner = sphere("slab_i", 0.104, flip=True)
bpy.ops.object.select_all(action="DESELECT")
for o in (outer, inner): o.select_set(True)
bpy.context.view_layer.objects.active = outer; bpy.ops.object.join()
slab = outer
def run(use_body):
    g = sphere("garment", 0.107)  # off-centre: crosses BOTH slab shells
    for v in g.data.vertices:
        v.co.x += 0.004
    r0 = [v.co.length for v in g.data.vertices]
    res = F.resolve_overlaps(g, slab, body=body if use_body else None, iters=120)
    r1 = [v.co.length for v in g.data.vertices]
    out = {"res": res, "moved_inward": sum(b < a - 1e-6 for a, b in zip(r0, r1)),
           "min_r": min(r1)}
    bpy.data.objects.remove(g)
    return out
print("PROBE", json.dumps({"new": run(True), "old": run(False)}))
'''


@unittest.skipUnless(shutil.which("blender"), "blender not on PATH")
class ResolveOverlapsAgainstSlab(unittest.TestCase):
    def test_pushes_outward_along_body_normal(self):
        with tempfile.TemporaryDirectory() as d:
            probe = Path(d) / "probe.py"
            probe.write_text(BLENDER_PROBE)
            out = subprocess.run(["blender", "-b", "--factory-startup", "--python", str(probe),
                                  "--", str(SCRIPTS)], capture_output=True, text=True, timeout=600)
            line = next(l for l in out.stdout.splitlines() if l.startswith("PROBE "))
            r = json.loads(line[6:])
            new = r["new"]
            self.assertEqual(new["res"]["remaining_pairs"], 0)
            self.assertEqual(new["moved_inward"], 0)  # never pushed toward the body
            self.assertGreater(new["min_r"], 0.1095)  # cleared to the slab outside
            # the step-15 behaviour (target-normal push) drives verts inward here
            self.assertGreater(r["old"]["moved_inward"], 0)


if __name__ == "__main__":
    unittest.main()

# FoundryClothThickness — procedural garment thickness for the foundry
# outfit pipeline (dressable-g9). Validated on mesh tasks 93257 + 93317.
#
# Why: single-surface garments leave open boundary edges at every hem/cuff
# (bright slivers in three.js) that cannot be fixed by pushing vertices.
# Thickness is authored, not patched (insight 55533). Bystedt addon Solidify
# is brittle in 5.2 (1mm weld leaves holes at 4mm) — we own this GN group.
#
# Route (per garment, body as shrinkwrap target):
#   1. shrinkwrap OUTSIDE 2mm over body   (lift garment clear of skin)
#   2. FoundryClothThickness GN group, 4mm outward:
#        Join(FlipFaces(orig), ExtrudeFaces(orig, t, individual=False))
#        + MergeByDistance 1e-5           (closed solid slab, welded rim)
#   3. shrinkwrap OUTSIDE 0.5mm safety    (push inner shell back off skin)
#
# Known residual: seams BETWEEN garment pieces become gaps between two
# closed slabs (not open edges) — needs its own seam-bridging gate
# (insight 55541).
#
# CLI: blender -b scene.blend --python foundry_cloth_thickness.py -- \
#        --body "Genesis 9 Mesh_baked" --garment "Shirt" --garment "Patch"
import bpy


def build_thickness_group(name="FoundryClothThickness", thickness=0.004):
    """6-node GN group: Join(FlipFaces(in), ExtrudeFaces(in, t)) + Merge."""
    g = bpy.data.node_groups.get(name)
    if g:
        return g
    g = bpy.data.node_groups.new(name, "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    s = g.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    s.default_value = thickness
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n_in = g.nodes.new("NodeGroupInput")
    n_out = g.nodes.new("NodeGroupOutput")
    flip = g.nodes.new("GeometryNodeFlipFaces")
    ext = g.nodes.new("GeometryNodeExtrudeMesh")
    ext.mode = "FACES"
    ext.inputs["Individual"].default_value = False
    join = g.nodes.new("GeometryNodeJoinGeometry")
    merge = g.nodes.new("GeometryNodeMergeByDistance")
    merge.inputs["Distance"].default_value = 1e-5
    lk = g.links.new
    lk(n_in.outputs["Geometry"], flip.inputs["Mesh"])
    lk(n_in.outputs["Geometry"], ext.inputs["Mesh"])
    lk(n_in.outputs["Thickness"], ext.inputs["Offset Scale"])
    lk(flip.outputs["Mesh"], join.inputs["Geometry"])
    lk(ext.outputs["Mesh"], join.inputs["Geometry"])
    lk(join.outputs["Geometry"], merge.inputs["Geometry"])
    lk(merge.outputs["Geometry"], n_out.inputs["Geometry"])
    return g


def _apply_mod(ob, mod):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _shrinkwrap(ob, body, offset):
    m = ob.modifiers.new("sw", "SHRINKWRAP")
    m.target = body
    m.wrap_method = "NEAREST_SURFACEPOINT"
    m.wrap_mode = "OUTSIDE"
    m.offset = offset
    _apply_mod(ob, m)


def apply_thickness_route(garment, body, thickness=0.004,
                          pre_offset=0.002, safety_offset=0.0005):
    """Full validated route on one garment object. Destructive (applies mods)."""
    _shrinkwrap(garment, body, pre_offset)
    m = garment.modifiers.new("thick", "NODES")
    m.node_group = build_thickness_group(thickness=thickness)
    _apply_mod(garment, m)
    _shrinkwrap(garment, body, safety_offset)


if __name__ == "__main__":
    import sys
    try:  # RUNBOOK §8.1: foundry blends need import_daz or drivers go dead
        import addon_utils
        addon_utils.enable("import_daz", default_set=True, persistent=True)
    except Exception as e:
        print("WARN import_daz not enabled:", e)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    body_name, garments, save_path = None, [], None
    it = iter(argv)
    for a in it:
        if a == "--body":
            body_name = next(it)
        elif a == "--garment":
            garments.append(next(it))
        elif a == "--save":
            save_path = next(it)
    body = bpy.data.objects[body_name]
    for gname in garments:
        apply_thickness_route(bpy.data.objects[gname], body)
        print("THICKNESS-APPLIED", gname)
    if save_path:
        bpy.ops.wm.save_as_mainfile(filepath=save_path)

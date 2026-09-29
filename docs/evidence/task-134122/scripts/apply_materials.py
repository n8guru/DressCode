"""task-134122: give the fitted garments real fabric materials (packed
textures from garment_textures.py) and save a new blend.

blender -b fit.blend --python apply_materials.py -- --tex DIR --out out.blend
"""
import json
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
tex = Path(argv[argv.index("--tex") + 1])
out = Path(argv[argv.index("--out") + 1])
report = {}
# The fit script's proof renders replace the body materials with a flat clay
# and hide every other mesh (hair, brows, lashes, eyes) -- that is why the
# task-134074 sheet showed a bald, featureless Amy.  Restore both from the
# identity master before anything is rendered or shipped.
if "--master" in argv:
    master = argv[argv.index("--master") + 1]
    with bpy.data.libraries.load(master, link=False) as (src, dst):
        dst.objects = ["Genesis 9 Mesh"]
    src_body = dst.objects[0]
    body = bpy.data.objects["Genesis 9 Mesh"]
    body.data.materials.clear()
    for mat in src_body.data.materials:
        body.data.materials.append(mat)
    # materials.clear() in the proof render also zeroed every polygon's
    # material index (whole body rendered with the fingernail shader)
    assert len(src_body.data.polygons) == len(body.data.polygons)
    idx = [0] * len(src_body.data.polygons)
    src_body.data.polygons.foreach_get("material_index", idx)
    body.data.polygons.foreach_set("material_index", idx)
    body.data.update()
    with bpy.data.libraries.load(master, link=False) as (src, dst2):
        names = list(src.objects)
    restored_vis = {}
    # visibility as saved in the master (AmyWaveCards is the GLB-only card
    # derivative and stays hidden in renders)
    mvis = {}
    with bpy.data.libraries.load(master, link=True) as (src, dst3):
        dst3.objects = names
    for o in dst3.objects:
        if o is not None:
            mvis[o.name] = o.hide_render
    for ob in bpy.data.objects:
        if ob.library is None and ob.name in mvis and ob.type in {"MESH", "CURVES"}:
            ob.hide_render = mvis[ob.name]
            restored_vis[ob.name] = not ob.hide_render
    for o in list(dst3.objects):
        if o is not None:
            bpy.data.objects.remove(o)
    for lib in list(bpy.data.libraries):
        bpy.data.libraries.remove(lib)
    _me = src_body.data
    bpy.data.objects.remove(src_body)
    if _me.users == 0:
        bpy.data.meshes.remove(_me)
    report["restored_from_master"] = {"master": master, "body_materials": [m.name for m in body.data.materials],
                                      "render_visible": restored_vis}
for kind, obname, sheen in (("pants", "Dressable Pants", 0.25), ("shirt", "Dressable Shirt", 0.1)):
    ob = bpy.data.objects[obname]
    meta = json.loads((tex / f"{kind}_textures.json").read_text())
    uv = ob.data.uv_layers
    assert len(uv), f"{obname} lost its UVs"
    uvname = uv[0].name
    m = bpy.data.materials.new(f"Dressable {kind.title()} Fabric")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    img = bpy.data.images.load(str(tex / f"{kind}_basecolor.png"))
    img.name = f"dressable_{kind}_basecolor"
    img.pack()
    t_base = nt.nodes.new("ShaderNodeTexImage")
    t_base.image = img
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = uvname
    nt.links.new(uvn.outputs["UV"], t_base.inputs["Vector"])
    nt.links.new(t_base.outputs["Color"], bsdf.inputs["Base Color"])
    nimg = bpy.data.images.load(str(tex / f"{kind}_weave_normal.png"))
    nimg.name = f"dressable_{kind}_weave_normal"
    nimg.colorspace_settings.name = "Non-Color"
    nimg.pack()
    mp = nt.nodes.new("ShaderNodeMapping")
    s = meta["weave_uv_scale"]
    mp.inputs["Scale"].default_value = (s, s, 1.0)
    nt.links.new(uvn.outputs["UV"], mp.inputs["Vector"])
    t_n = nt.nodes.new("ShaderNodeTexImage")
    t_n.image = nimg
    t_n.interpolation = "Cubic"
    nt.links.new(mp.outputs["Vector"], t_n.inputs["Vector"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = uvname
    nm.inputs["Strength"].default_value = 0.45 if kind == "pants" else 0.3
    nt.links.new(t_n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = meta["roughness"]
    for key in ("Sheen Weight", "Sheen"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = sheen
            break
    m.diffuse_color = tuple(list(img.pixels[:4]) if False else (0.13, 0.2, 0.36, 1) if kind == "pants" else (0.77, 0.55, 0.15, 1))
    ob.data.materials.clear()
    ob.data.materials.append(m)
    report[kind] = {"uv": uvname, "material": m.name, "weave_uv_scale": s,
                    "images": [img.name, nimg.name]}
bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
print("MATERIALS_OK", json.dumps(report), flush=True)

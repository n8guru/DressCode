"""Operator prompt -> GarmentCode sewing patterns (task-133934, decision #1988251; task-134122 refit per decision #1994543: flare from the knee, fitted shirt, shallower V).

Operator text (verbatim): "70's bellbottom jeans, and a large coller 70's shirt."
SewingGPT (DressCode) was tried first on this prompt (see sgpt logs): its pants
sample had a point-waist panel and stitches naming non-existent edges, and its
shirt sample had no collar panel and 26 cm sleeves.  So the prompt is mapped to
GarmentCode's design space instead; this mapping IS the text->pattern step and
is recorded verbatim in the output (PROMPT_TO_DESIGN).
"""
import json, sys, copy, yaml
from pathlib import Path
sys.path.insert(0, "/home/n8/cloth_test/task-133870/GarmentCode")
import os
os.chdir("/home/n8/cloth_test/task-133870/GarmentCode")
from assets.garment_programs.meta_garment import MetaGarment
from assets.bodies.body_params import BodyParameters

OUT = Path(sys.argv[1])
BODY = sys.argv[2]
PROMPT = "70's bellbottom jeans, and a large coller 70's shirt."
PROMPT_TO_DESIGN = {
    "bellbottom_jeans": {
        "meta.upper": None, "meta.wb": "StraightWB", "meta.bottom": "Pants",
        "waistband.width": 0.2, "waistband.waist": 1.0,
        "pants.length": 0.77, "pants.width": 1.0, "pants.flare": 1.0,
        "pants.rise": 0.9,
        "pants.cuff.type": "CuffSkirt", "pants.cuff.cuff_len": 0.44,
        "pants.cuff.skirt_flare": 1.5, "pants.cuff.skirt_fraction": 0.9,
        "pants.cuff.top_ruffle": 1.0,
    },
    "collar_shirt_70s": {
        "meta.upper": "Shirt", "meta.wb": None, "meta.bottom": None,
        "shirt.length": 1.5, "shirt.width": 1.0, "shirt.flare": 1.0,
        "collar.f_collar": "VNeckHalf", "collar.b_collar": "CircleNeckHalf",
        "collar.width": 0.25, "collar.fc_depth": 0.6, "collar.bc_depth": 0.0,
        "collar.component.style": "SimpleLapel", "collar.component.depth": 11,
        "collar.component.lapel_standing": False,
        "sleeve.sleeveless": False, "sleeve.armhole_shape": "ArmholeCurve",
        "sleeve.length": 0.73, "sleeve.end_width": 0.45,
        "sleeve.connecting_width": 0.2, "sleeve.sleeve_angle": 10,
    },
}


def setp(design, dotted, value):
    node = design
    for k in dotted.split("."):
        node = node[k]
    node["v"] = value


base = yaml.safe_load(open("assets/design_params/default.yaml"))["design"]
body = BodyParameters(BODY)
OUT.mkdir(parents=True, exist_ok=True)
for name, over in PROMPT_TO_DESIGN.items():
    d = copy.deepcopy(base)
    for k, v in over.items():
        setp(d, k, v)
    g = MetaGarment(name, body, d)
    pattern = g.assembly()
    si = g.is_self_intersecting()
    folder = pattern.serialize(OUT, tag="", to_subfolder=True, with_3d=False,
                               with_text=False, view_ids=False, with_printable=False)
    body.save(folder)
    Path(folder, "design_params.yaml").write_text(yaml.safe_dump({"design": d}))
    spec = next(Path(folder).glob("*specification.json"))
    P = json.loads(spec.read_text())["pattern"]
    print("GC_SPEC", json.dumps({"name": name, "spec": str(spec), "self_intersecting": bool(si),
                                 "panels": len(P["panels"]), "stitches": len(P["stitches"]),
                                 "panel_names": sorted(P["panels"])}), flush=True)
Path(OUT, "prompt_to_design.json").write_text(json.dumps(
    {"prompt": PROMPT, "mapping": PROMPT_TO_DESIGN, "body": BODY}, indent=2))

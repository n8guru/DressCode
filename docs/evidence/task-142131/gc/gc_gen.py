"""Generic text-prompt -> GarmentCode sewing pattern generator (dressable-g9 s16, task 142131).

Garment-agnostic: everything garment-specific lives in the SPEC JSON
(prompt text + GarmentCode design-param mapping + optional per-panel
placement overrides), never in this code.

  python gc_gen.py SPEC.json OUT_DIR BODY.yaml

SPEC = {"prompt": "...", "garments": {name: {"design": {dotted: value},
         "panel_placement": {panel_name: {"translation": [x,y,z]?, "rotation": [rx,ry,rz]?}}}}}
Writes OUT_DIR/<name>/<name>_specification.json (+ design_params.yaml, body) and
OUT_DIR/prompt_to_design.json with sha256 of every pattern JSON.
"""
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

GC = os.environ.get("GARMENTCODE", "/home/n8/cloth_test/task-133870/GarmentCode")
sys.path.insert(0, GC)
os.chdir(GC)
from assets.garment_programs.meta_garment import MetaGarment  # noqa: E402
from assets.bodies.body_params import BodyParameters  # noqa: E402

SPEC, OUT, BODY = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
spec = json.loads(SPEC.read_text())


def setp(design, dotted, value):
    node = design
    for k in dotted.split("."):
        node = node[k]
    node["v"] = value


base = yaml.safe_load(open("assets/design_params/default.yaml"))["design"]
body = BodyParameters(BODY)
OUT.mkdir(parents=True, exist_ok=True)
record = {"prompt": spec["prompt"], "spec_file": str(SPEC), "body": BODY, "garments": {}}
for name, g in spec["garments"].items():
    d = copy.deepcopy(base)
    for k, v in g["design"].items():
        setp(d, k, v)
    mg = MetaGarment(name, body, d)
    pattern = mg.assembly()
    si = mg.is_self_intersecting()
    folder = pattern.serialize(OUT, tag="", to_subfolder=True, with_3d=False,
                               with_text=False, view_ids=False, with_printable=False)
    body.save(folder)
    Path(folder, "design_params.yaml").write_text(yaml.safe_dump({"design": d}))
    sp = next(Path(folder).glob("*specification.json"))
    J = json.loads(sp.read_text())
    for pname, pl in g.get("panel_placement", {}).items():
        for key in ("translation", "rotation"):
            if key in pl:
                J["pattern"]["panels"][pname][key] = pl[key]
    sp.write_text(json.dumps(J, indent=2))
    P = J["pattern"]
    row = {"spec": str(sp), "sha256": hashlib.sha256(sp.read_bytes()).hexdigest(),
           "self_intersecting": bool(si), "panels": len(P["panels"]),
           "stitches": len(P["stitches"]), "panel_names": sorted(P["panels"]),
           "design": g["design"], "panel_placement": g.get("panel_placement", {})}
    record["garments"][name] = row
    print("GC_SPEC", json.dumps({k: row[k] for k in ("spec", "sha256", "panels", "stitches", "panel_names")}), flush=True)
(OUT / "prompt_to_design.json").write_text(json.dumps(record, indent=2))

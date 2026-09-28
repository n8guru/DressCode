"""Screenplay-pipe front door for dressable-g9 step 15 (task-133934).

Operator decision #1988251: "70's bellbottom jeans, and a large coller 70's
shirt." -- screenplay pipe has tools to produce the character in the outfit.
Creates (idempotently) the two wardrobe props for Amy (imagine_chat_global,
project 13, canonical character 90), binds each to the fitted G9 wearable via
register_wearable (screenplay_prop_wearable), and composes the Character
Foundry `assets` payload with compose_foundry_assets from the ACTIVE binding
rows.  Prints the envelope as JSON on the last line.
"""
import json
import os
import sys

os.environ.setdefault("HARNESS_RUNNER_ROLE", "")
sys.path.insert(0, os.getcwd())
from app import create_app  # noqa: E402

PROJECT, AMY = 13, 90
SRC = "/Users/nathanrichmond/character-foundry-wt/task-133934-inputs/dressable_g9_outfit_70s.blend"
META = "/Users/nathanrichmond/character-foundry-wt/task-133934-inputs/dressable_g9_outfit_70s.json"
PROPS = [
    ("70's bellbottom jeans", "Dressable Pants",
     "Mid-blue denim 1970s bell-bottom jeans: straight waistband, fitted "
     "through the hip, flaring from the knee into a wide bell hem."),
    ("large collar 70's shirt", "Dressable Shirt",
     "1970s long-sleeve shirt in warm mustard with an oversized pointed "
     "lapel collar over an open V neckline, worn untucked over the jeans."),
]

app = create_app()
with app.app_context():
    from app.screenplay.v4_props import find_or_create_prop
    from app.screenplay.v4_wearables import (
        _active_bindings, compose_foundry_assets, register_wearable)
    props, bindings = [], []
    for name, obj, appearance in PROPS:
        prop = find_or_create_prop(PROJECT, name, appearance=appearance,
                                   owner_canonical_character_id=AMY)
        props.append({"prop_id": prop["id"], "name": prop["name"],
                      "is_new": prop.get("is_new")})
        if "--bind" in sys.argv:
            bindings.append(register_wearable(PROJECT, int(prop["id"]), {
                "source": SRC, "objects": [obj], "metadata": META,
                "bake_offline": True}))
    ids = [p["prop_id"] for p in props]
    active = _active_bindings(PROJECT, ids)
    env = compose_foundry_assets(props, active)
    print("SP_WEARABLE " + json.dumps({"props": props, "registered": bindings,
                                       "active_bindings": active,
                                       "envelope": env}, default=str))

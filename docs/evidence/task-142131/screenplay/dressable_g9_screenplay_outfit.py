"""dressable-g9 screenplay outfit proof, garment-agnostic (step 16, task 142131;
generalised from step 15's dressable_g9_s15_screenplay_outfit.py on
agents/droplet/task-134122@a2d33448a, whose prop list was hard-coded to the 70s
outfit).  Screenplay outfit tools -> Foundry `assets`, against the SCRATCH
database (forage_test; refuses any other):

  1. a proof project (matched by --title) with one scene/block/sentence and Amy;
  2. one wardrobe prop per --props entry via ``find_or_create_prop``;
  3. an operator-pinned ``outfit`` state_change per prop at the sentence;
  4. POST /api/screenplay/<p>/v4/wearables/<prop> per prop (fitted G9 wearable
     + provider spring profile on mac);
  5. GET /api/screenplay/<p>/v4/wearable_spec/<cc>?sentence_id=<s> -> the
     Foundry ``assets`` envelope (status must be ``ready``).

PYTHONPATH=. python scripts/dressable_g9_screenplay_outfit.py --spec spec.json --out env.json
spec.json = {"title", "prompt", "sentence", "task", "pin", "decision",
             "source", "metadata", "profile",
             "props": [{"name", "object", "appearance"}]}
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

TITLE = SENTENCE = SOURCE = META = PROFILE = TASK = PROMPT = PIN = None
PROPS = []


def one(sql, **kw):
    from app import db
    return db.session.execute(text(sql), kw).scalar()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    global TITLE, SENTENCE, SOURCE, META, PROFILE, TASK, PROMPT, PIN, PROPS
    sp = json.loads(open(a.spec).read())
    TITLE, SENTENCE, PROMPT = sp["title"], sp["sentence"], sp["prompt"]
    SOURCE, META, PROFILE = sp["source"], sp["metadata"], sp["profile"]
    TASK, PIN = sp["task"], sp["pin"]
    assert len(PIN) <= 32, "decision_source is varchar(32)"
    a.decision = sp["decision"]
    PROPS = [(p["name"], p["object"], p["appearance"]) for p in sp["props"]]
    from app import create_app, db
    app = create_app()
    with app.app_context():
        name = db.engine.url.database
        if name != "forage_test":
            sys.exit(f"refusing to run against database {name!r}; forage_test only")
        pid = one("SELECT id FROM screenplay_projects WHERE title = :t ORDER BY id LIMIT 1", t=TITLE)
        if pid is None:
            pid = one("""INSERT INTO screenplay_projects (title, source_dir)
                         VALUES (:t, '/dev/null/dressable-g9-proof') RETURNING id""", t=TITLE)
        block = one("SELECT id FROM screenplay_source_block WHERE project_id=:p ORDER BY id LIMIT 1", p=pid)
        if block is None:
            block = one("""INSERT INTO screenplay_source_block
                (project_id, chapter_file, block_index, block_kind, raw_text)
                VALUES (:p, 'ch01.txt', 0, 'prose', :t) RETURNING id""",
                        p=pid, t=SENTENCE)
        scene = one("SELECT id FROM screenplay_scene WHERE project_id=:p ORDER BY id LIMIT 1", p=pid)
        if scene is None:
            scene = one("""INSERT INTO screenplay_scene
                (project_id, scene_index, start_block_id, end_block_id, detector_source)
                VALUES (:p, 0, :b, :b, :t) RETURNING id""", p=pid, b=block, t=TASK)
        db.session.execute(text("UPDATE screenplay_source_block SET scene_id=:s WHERE id=:b"),
                           {"s": scene, "b": block})
        sent = one("SELECT id FROM screenplay_source_sentence WHERE block_id=:b ORDER BY id LIMIT 1", b=block)
        if sent is None:
            sent = one("""INSERT INTO screenplay_source_sentence
                (project_id, block_id, sentence_index_in_block, global_sentence_index, text)
                VALUES (:p, :b, 0, 0, :t) RETURNING id""",
                       p=pid, b=block, t=SENTENCE)
        cc = one("SELECT id FROM screenplay_canonical_character WHERE project_id=:p AND name='Amy'", p=pid)
        if cc is None:
            cc = one("""INSERT INTO screenplay_canonical_character (project_id, name)
                        VALUES (:p, 'Amy') RETURNING id""", p=pid)
        user = one("SELECT id FROM users WHERE username = 'dressable_g9_s15_proof'")
        if user is None:
            user = one("INSERT INTO users (username) VALUES ('dressable_g9_s15_proof') RETURNING id")
        db.session.commit()

        from app.screenplay.v4_props import find_or_create_prop
        props = []
        for pname, obj, appearance in PROPS:
            prop = find_or_create_prop(pid, pname, appearance=appearance,
                                       owner_canonical_character_id=cc)
            props.append({"prop_id": int(prop["id"]), "name": prop["name"], "object": obj})
            have = one("""SELECT id FROM screenplay_state_change WHERE project_id=:p
                          AND canonical_character_id=:c AND canonical_prop_id=:pr
                          AND state_type='outfit' AND source_sentence_id=:s
                          AND superseded_by_id IS NULL""", p=pid, c=cc, pr=prop["id"], s=sent)
            if have is None:
                one("""INSERT INTO screenplay_state_change
                    (project_id, canonical_character_id, canonical_prop_id, state_type,
                     from_value, to_value, source_sentence_id, decision_source,
                     rationale, decided_by, decided_at)
                    VALUES (:p, :c, :pr, 'outfit', '', :tv, :s, :ds, :r, :by, NOW())
                    RETURNING id""", p=pid, c=cc, pr=prop["id"], tv=pname, s=sent, ds=PIN,
                    r=f"Operator decision #{a.decision}: {PROMPT}", by=TASK)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user)
            sess["user_id"] = user
            sess["_fresh"] = True
        registered = []
        for p in props:
            r = client.post(f"/api/screenplay/{pid}/v4/wearables/{p['prop_id']}", json={
                "source": SOURCE, "objects": [p["object"]], "metadata": META,
                "secondary_motion_profile": PROFILE, "bake_offline": True})
            if r.status_code != 201:
                sys.exit(f"register {p['prop_id']} -> {r.status_code} {r.get_data(as_text=True)[:400]}")
            registered.append(r.get_json())
        r = client.get(f"/api/screenplay/{pid}/v4/wearable_spec/{cc}?sentence_id={sent}")
        env = {"http_status": r.status_code, "route":
               f"GET /api/screenplay/{pid}/v4/wearable_spec/{cc}?sentence_id={sent}",
               "database": name, "project_id": pid, "canonical_character_id": cc,
               "sentence_id": sent, "props": props, "registered": registered,
               "response": r.get_json()}
        text_out = json.dumps(env, indent=2, sort_keys=True, default=str)
        open(a.out, "w").write(text_out + "\n")
        print("OUTFIT_ENVELOPE " + json.dumps(env, sort_keys=True, default=str))
        if r.status_code != 200 or (r.get_json() or {}).get("status") != "ready":
            sys.exit(2)


if __name__ == "__main__":
    main()

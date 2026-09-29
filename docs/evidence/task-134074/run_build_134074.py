"""task-134074: headless character-foundry build whose `assets` block is the
screenplay-v4 wearable_spec route response (forage_test proof project)."""
import json, os, sys
from pathlib import Path
os.environ["FOUNDRY_HOME"] = str(Path.home() / "character-foundry-wt/task-134074-home")
sys.path.insert(0, str(Path.home() / "character-foundry-wt/task-134074"))  # agents/forge/task-134074
from foundry import config, pipeline
from foundry.server import CharacterSpec
inp = Path.home() / "character-foundry-wt/task-134074-inputs"
env = json.loads((inp / "s15_envelope.json").read_text())["response"]
assert env["status"] == "ready", env
raw = {"name": "amy_dressable_g9_s15_70s_134074", "sex": "female", "identity_master": "amy_gp_v3",
       "assets": env["assets"]}
spec = CharacterSpec(**raw).model_dump()
job_id = "s15_dressable_70s_134074"
jd = config.JOBS_DIR / job_id
jd.mkdir(parents=True, exist_ok=True)
(jd / "spec.json").write_text(json.dumps(spec, indent=2))
print("STAGES", pipeline.build_stage_list(spec), flush=True)
def upd(jid, **kw): print("UPDATE", kw, flush=True)
pipeline.run_pipeline({"id": job_id}, update=upd)
print("MANIFEST", (jd / "manifest.json").read_text()[:4000])

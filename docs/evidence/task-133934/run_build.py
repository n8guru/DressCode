"""task-133934: headless character-foundry build whose `assets` block is the
screenplay-v4 compose_foundry_assets envelope (props 1012/1013 -> Amy)."""
import json, os, sys
from pathlib import Path
os.environ["FOUNDRY_HOME"] = str(Path.home() / "character-foundry-wt/task-133934-home")
sys.path.insert(0, str(Path.home() / "character-foundry-wt/task-133870"))  # main@a928806, unmodified
from foundry import config, pipeline
from foundry.server import CharacterSpec
inp = Path.home() / "character-foundry-wt/task-133934-inputs"
env = json.loads((inp / "screenplay_envelope.json").read_text())
assert env["status"] == "ready", env
raw = {"name": "amy_dressable_g9_s15_70s", "sex": "female", "identity_master": "amy_gp_v3",
       "assets": env["assets"]}
spec = CharacterSpec(**raw).model_dump()
job_id = "s15_dressable_70s_133934"
jd = config.JOBS_DIR / job_id
jd.mkdir(parents=True, exist_ok=True)
(jd / "spec.json").write_text(json.dumps(spec, indent=2))
print("STAGES", pipeline.build_stage_list(spec), flush=True)
def upd(jid, **kw): print("UPDATE", kw, flush=True)
pipeline.run_pipeline({"id": job_id}, update=upd)
print("MANIFEST", (jd / "manifest.json").read_text()[:3000])

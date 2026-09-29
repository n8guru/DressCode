"""Run tools/qc_gate/run_gate.py's canonical intention artifact builder with a
hosted OpenRouter vision judge (forge GPU is held by ComfyUI, so the local
llama-swap VLM cannot load: 502 / no mmproj).  Same build_intention_artifact,
same readiness_gate preview; only the HTTP judge adds an Authorization header.

PYTHONPATH=<forage tree> python run_gate_openrouter.py MEDIA --checklist C --producer P --model M --out OUT
"""
import argparse, base64, json, os, subprocess, sys
from pathlib import Path

import requests

sys.path.insert(0, os.getcwd())
from tools.qc_gate import run_gate as RG  # noqa: E402
from app.generation import readiness_gate as gate  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("media"); ap.add_argument("--checklist", required=True)
ap.add_argument("--producer", required=True); ap.add_argument("--model", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
key = subprocess.run(["forage-secret", "get", "OPENROUTER_API_KEY"], capture_output=True,
                     text=True).stdout.strip()


def judge(prompt, images):
    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(img).decode()}})
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=240,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": a.model, "temperature": 0, "max_tokens": 600,
                            "messages": [{"role": "user", "content": content}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"].get("content") or ""


checklist = json.loads(Path(a.checklist).read_text())
art = RG.build_intention_artifact(media=a.media, checklist=checklist, producer=a.producer,
                                  judge=judge, judge_model=a.model, judge_provider="openrouter")
readiness = {"producer": a.producer, "intention_qc": [art]}
sha = art["subject_sha256"]
preview = gate.evaluate(readiness, subjects=[{"url": a.media, "kind": art["media_kind"]}],
                        resolve_sha256=lambda _u: sha)
Path(a.out).write_text(json.dumps(readiness, indent=1, default=str))
print(gate.summary(preview))
sys.exit(0 if preview["verdict"] == "pass" else 1)

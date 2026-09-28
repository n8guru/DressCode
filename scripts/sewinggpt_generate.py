import os, sys, json, torch, random, numpy as np
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(R/"packages"), str(R/"nn"), str(R/"nn"/"evaluation_scripts")]
os.chdir(R)
from predict_class import infer
g = infer("./models/infer.yaml")
prompts = sys.argv[1:] or ["skirt, midi length, flared"]
for i, p in enumerate(prompts):
    for seed in (1, 2, 3):
        torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
        try:
            spec = g.forward(p, temperature=0.7, sim=False)
            print("SPEC", json.dumps({"prompt": p, "seed": seed, "spec": str(Path(spec).resolve())}), flush=True)
        except Exception as e:
            print("FAIL", p, seed, repr(e), flush=True)

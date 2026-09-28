import os, sys, json, torch, random, numpy as np
from pathlib import Path
R = Path("/home/n8/cloth_test/task-133870/DressCode")
sys.path[:0] = [str(R/"packages"), str(R/"nn"), str(R/"nn"/"evaluation_scripts")]
os.chdir(R)
from predict_class import infer
g = infer("./models/infer.yaml")
p = sys.argv[1]; seeds=[int(s) for s in sys.argv[2].split(",")]
for seed in seeds:
    torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
    try:
        spec = g.forward(p, temperature=0.7, sim=False)
        print("SPEC", json.dumps({"prompt": p, "seed": seed, "spec": str(Path(spec).resolve())}), flush=True)
    except Exception as e:
        print("FAIL", p, seed, repr(e), flush=True)

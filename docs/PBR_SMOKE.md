# Forge PBR texture smoke test

Run from an isolated DressCode worktree while holding the `gpu-vram` lease:

```bash
conda run -n DressCode python smoke_pbr.py \
  --model-dir /home/n8/DressCode/nn/material_gen \
  --output outputs/task-2928-pbr \
  --evidence docs/evidence/task-2928-pbr.json
```

The model emits separate 512×512 diffuse, tangent-normal, and roughness maps
from one shared latent. The smoke gate checks that all three maps exist, are
non-flat, have distinct hashes, and records edge discontinuity plus channel
statistics for candid tile-quality review.

Task 2928 evaluated three deterministic candidates. Seed `589169` was selected
because it preserved recognizable linen weave and slub structure while moving
the diffuse map toward the white-shirt target. The recorded edge MAE remains a
candid limitation: the maps are tile-oriented but not mathematically seamless.

`gen_texture` also recognizes the recoverable forge checkpoint layout where a
Hugging Face download nested the UNet blob under `unet/material_gen/unet`.
It loads that blob in place instead of modifying or duplicating shared weights.

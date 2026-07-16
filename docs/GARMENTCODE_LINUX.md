# GarmentCode Linux draping evaluation

DressCode's released simulator is proprietary Maya + Qualoth. GarmentCode is a
viable open-source Linux replacement at the solver layer: its MIT-licensed
pattern library invokes a GarmentCode-specific NVIDIA Warp fork, which compiled
and ran CUDA kernels on forge's RTX 5090 with CUDA 12.9.

## Reproduced passing gate

At GarmentCode commit `a4b3a92` on branch `agents/codex/task-2950`, run its
included shirt specification against the female SMPL A-pose body:

```bash
PYTHONPATH=/path/to/NvidiaWarp-GarmentCode:/path/to/GarmentCode \
  python test_garment_sim.py \
  --pattern_spec assets/Patterns/shirt_mean_specification.json \
  --sim_config assets/Sim_props/default_sim_props.yaml \
  --body_name f_smpl_average_A40 \
  --smpl_body
```

The fresh run reached static equilibrium in 264 frames with 0 body-cloth
intersections and 3 self-intersections. It produced an 8,343-vertex,
15,712-face OBJ and coherent front/back renders. Exact hashes and paths are in
`docs/evidence/task-2950-garmentcode-linux.json`.

## SewingGPT compatibility boundary

SewingGPT and GarmentCode specifications use the same top-level pattern schema.
GarmentCode ingests the task-2906 SewingGPT fixture without a structural
conversion. Their placement frames differ, however: SewingGPT's shirt panels
are centered around y=10--20 cm while GarmentCode's floor-origin A-pose torso is
around y=95--110 cm.

`scripts/prepare_garmentcode_spec.py` preserves the complete specification and
applies an explicit vertical offset for this experiment. The 84 cm-aligned
SewingGPT shirt correctly classified sleeves as arms and torso panels as body,
but still failed the gate: 136 body-cloth intersections, 260 self-intersections,
and a visibly over-scale drape. Do not use that result downstream. The passing
GarmentCode shirt is the step-2 fixture; production SewingGPT integration still
needs body-aware panel scale/placement calibration.

## Licensing

GarmentCode itself is MIT. Its Warp fork carries NVIDIA's source-code license
and explicitly states non-commercial use. This is suitable for evaluation but
is not a commercial deployment foundation without a license change or solver
replacement.

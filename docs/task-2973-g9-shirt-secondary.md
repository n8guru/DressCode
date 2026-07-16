# Task 2973 — G9 shirt GLB + shared secondary motion

This step consumes the fitted, weighted Amy shirt from task 2964 and implements
the garment-provider side of character-foundry's secondary-motion v1 contract.
The provider explicitly authors and weights three clothing chains (left sleeve,
right sleeve, and lower hem); the runtime contract remains the same one used by
hair and body chains.

Run the deterministic Blender gate with:

```bash
blender --background --python scripts/export_g9_garment_secondary.py -- \
  --source /home/n8/codex-mesh-worker/worktrees/task-2964/DressCode/outputs/task-2964-g9-transfer/garmentcode_shirt_on_g9_amy.blend \
  --pbr-dir /home/n8/codex-mesh-worker/worktrees/task-2928/DressCode/outputs/task-2928-pbr \
  --out-dir outputs/task-2973-g9-shirt-secondary
```

The script gates normalized blended weights, measured garment deformation under
the baked fan response, a 25 MB GLB budget, skin/animation/spring-joint presence,
embedded `asset.extras.foundry.secondary_motion`, and a clean GLB re-import whose
geometry still moves under the exported animation.

Fresh task-2973 evidence passes all gates: the 2.282 MB GLB contains one mesh,
one skin, one 72-frame animation, all six spring bones as skin joints, and the
three-chain embedded profile. A clean GLB import preserves all 15,712 faces and
moves 2,374 vertices over 1 mm at the peak frame (8.53 mm maximum). The compact
tracked manifest is `docs/evidence/task-2973-g9-shirt-secondary.json`; the Blend,
GLB, full report, profile, and proof renders are under
`outputs/task-2973-g9-shirt-secondary/`.

The source GarmentCode mesh's small ragged/open sleeve-seam spots are retained
and reported candidly; this step does not claim to repair source topology.
The exporter measures source topology rather than hard-coding this fixture's
counts, so a second fitted shirt can use the same command shape unchanged.

# Task 2964 — GarmentCode SMPL shirt to G9 Amy

The step-2 GarmentCode shirt now fits and follows the real G9 Amy artifact. The
headless fitter preserves all 7,990 vertices and 15,712 faces, converts the
GarmentCode centimetre SMPL frame into G9's metre Blender frame, establishes
4 mm body clearance, transfers and normalizes G9 weights, and effect-tests an
asymmetric upper-body pose.

Fresh Blender 5.2 evidence passes the step-4 gates:

- body penetration: 940 inside vertices before fit, 0 after; 0 body/garment
  BVH surface-overlap pairs after fit;
- skinning: 7,990/7,990 vertices weighted and normalized across 21 used G9
  groups;
- rig following: 7,979/7,990 vertices move more than 1 mm, with 3.74 cm mean
  and 14.89 cm maximum displacement;
- visual: front/back rest and posed renders show a coherent cropped shirt
  surrounding Amy and following both arms and torso.

The visual proof is deliberately candid: the source garment retains small
ragged/open spots around the sleeve seams. They are not G9-body penetration
(the geometric overlap gate is zero), but should be polished before a production
wardrobe claim.

Evidence is in `docs/evidence/task-2964-g9-transfer.json`; runtime artifacts are
under `outputs/task-2964-g9-transfer/` and are excluded from Git because the
fitted Blend is 107 MB.

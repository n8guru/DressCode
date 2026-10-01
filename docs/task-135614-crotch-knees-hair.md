# Task 135614: dressable-g9 step 15, operator decision #1997482

Nate's words on the task-134122 card: *"the two hightest value changes would be the "crotch" need to be close fit- and the knees look funny when bent. also the hair might need to be behind the shoulder. otherwise, a vast improvement."*

The priority order was:
1. a close-fitting jeans crotch;
2. knees that bend cleanly;
3. hair behind the shoulders.

Everything else was accepted as it was, so the colours and the collar are unchanged.

Evidence is in `docs/evidence/task-135614/`. The worker that made these changes has not verified them; an independent reviewer still needs to.

## 1. Crotch

**Cause.** The GarmentCode pants pattern puts its crotch point about 85 mm below the body's crotch. The pattern's crotch depth ignores the body. The task-134122 tightening pulled the fabric in against the thighs, but the midline stayed low. The result was a web of denim between the upper thighs.

**Change.** A new pass in `retarget_tighten.py` called `crotch_lift` (enabled with `--crotch-lift --crotch-ease-mm 10`):
* It casts a vertical ray up from every jeans vertex within 12 mm of the midline, in the crotch band. Where the ray hits the body's crotch underside, the vertex is constrained to sit 10 mm (the ease) under that surface.
* The waistband and the legs below z = 0.45 m are pinned.
* The lift everywhere else is a harmonic (Laplacian/Jacobi) interpolation over the garment mesh, so the rise shortens smoothly instead of kinking.
* The pass runs after the gp_v3 → a08 replay, and again after the relax, which otherwise averages the saddle back down.
* Inner-thigh fabric that the lift slid under the minimum offset is re-seated.

Numbers are in `crotch_midline.txt`, using the same probe on both wearables:

| | task 134122 | task 135614 |
|---|---|---|
| Jeans midline crotch, below the body crotch (retarget obj, inner surface) | 81.8 mm (z 0.7307) | 9.6 mm (z 0.8029) |
| Midline fabric verts below z 0.77 (wearable, 4 mm slab) | 23 of 23 | 6 of 35 |
| Crotch-mid gap to body, max | 26.6 mm | 9.0 mm |
| Seat gap to body, max | 27.0 mm | 10.3 mm |

The cross-sections are `crotch_xsec_before.png` and `crotch_xsec_after.png`. Blue is the jeans and black is the body.

## 2. Knees when bent

**Cause.** Measured with `probe/walk_probe.py`, the walk pose had **396 pants edges stretched more than 2×**, up to **156×**. The two bell-bottoms hang 2–3 mm apart between the shins. There were two faults:
* The nearest-skin weight transfer gave the inner face of one bell the **other** leg's shin weights.
* The spring flare chains split the flare by the sign of x rather than by leg.

In walk and step the two bells were therefore joined by a sheet of stretched fabric. The hem also carried foot and toe weights. Neither fault could be seen at rest.

**Change** (`fit_native_g9_outfit.py`):
* **`tag_leg_sides`.** Before the thickness slab, every pants vertex is stamped with the leg it was sewn into, as a `gc_leg_side` point attribute taken from the GarmentCode panel labels. Crotch seams count as shared. The slab's extrude, merge and shrinkwraps carry point attributes, so the second shell keeps its leg.
* **`pants_leg_weights`.**
  * Weight on the other leg's bones moves to the mirror bone.
  * Foot and toe weights move to the shin.
  * Bell fabric becomes a rigid tube on its own shin below the knee, blending over 7 cm at the knee joint.
* **Spring flare chains** are assigned by `gc_leg_side` instead of by the sign of x.
* **Retarget.** In `retarget_tighten.py --knee-fit-m 0.14`, the top 14 cm of the bell stays fitted to the calf and ramps out. A bent knee now reads as a fitted fold rather than a wide soft blob.
* **Sit correctives.** The fitted knee and the higher crotch needed more push iterations for the sit-pose correctives (`PC_ITERS=30`, up from 6). On sit 80 the offenders went 4 → 0.

## 3. Hair behind the shoulders

**Change.** New opt-in mode `hair_over_outfit.py --behind-shoulders`. A strand, or a hair-card island, counts as front hair when most of its length below the shoulder top lies in front of the torso mid-plane. Front hair is swung to the back:
* Each point below the shoulder top is reflected from its depth in front of the chest/collar to a depth behind the back surface. Both surfaces are found by Y-rays through the body and garments.
* The stand-off behind the back is halved and capped at 45 mm, so hair lies on the back.
* The swing ramps in over 9 cm below the shoulder top.
* Points that would end up inside the shoulder are laid on top of it.
* The scalp, the part and the face-framing hair above the shoulders do not move.

In the build, the normal lay-over-outfit pass then runs as before. Totals: 67,753 of 96,930 groom strands and 1,788 of 2,576 card islands were swung.

**Foundry.** On character-foundry `agents/forge/task-135614` (mac), `assets.outfit.hair_behind_shoulders=true` passes `--behind-shoulders` to the outfit-stage hair pass.

**Latent bug fixed along the way.** `Outfit` in `foundry/server.py` did not declare `hair_over_outfit` or `hair_behind_shoulders`, so `CharacterSpec.model_dump()` silently dropped both. The task-134122 opt-out had never reached the stage. The first build of this task ran without the swing for the same reason. Both fields are now declared, and `test_outfit_hair_styling_flags_survive_model_dump` covers them.

## Gates

**Fit** (`fit/f15`, `PC_ITERS=30`):
* 31,546 of 31,546 jeans vertices and 19,950 of 19,950 shirt vertices are weighted and normalized.
* 0 boundary edges; closed slabs; cover OK.

**Fresh re-measure.** `verify_outfit_gates.py`, run in a fresh process on the wearable (sha256 `0bf847699d89e05d9f5531bb113b8a4a86dd56fa1d3bc84c6a93fafec5cc4803`), gives **gated_all_zero=True**. That covers rest, ship, walk, sit 80, arms-up 45/20, arm swing a/b, step+twist, weight shift and sit 40/55/70. The report is `verify_gates.json`, sha256 `67f43752…`.
* The diagnostic failures, sit95 and stride_133870, are the same two as in tasks 134074 and 134122.

**Screenplay** (forage_test). Script: `agents/droplet/task-134122:scripts/dressable_g9_s15_screenplay_outfit.py`, run with `--task 135614 --pin operator_1997482:scene_start`. Result: **200 `ready`**, with `assets.outfit` pointing at `task-135614-inputs` (`s15_envelope_135614.json`).

**Foundry build.** Character-foundry `agents/forge/task-135614@496a8a9` (mac), `run_build_135614.py`, `identity_master=amy_a08_v3`, `hair_behind_shoulders=true`:
* `OUTFIT_OK meshes=2 verts=51496 weighted=51496 provider_bones=8`
* `HAIR_CLEAR_OK curves_points=221427 strands=84515 card_verts=5244`, with a `behind_shoulders` block in `foundry_hair_over_outfit.json`
* `COVER_OK frac=0.0982`
* `SECONDARY_OK chains=4 bones=8 frames=120`
* `EXPORT: ALL OK`
* `STEP35_GLB_OK targets=46`
* **GLB sha256 `1f29dc2fe80c9f0f82e5e86303eeac151ea3e7540c935d650c1c390041db9cf6`**
* The manifest status is `succeeded_with_identity_master_nsfw_fail`. `assert_nsfw` fails on the bare amy_a08_v3 master exactly as it did at baseline (see task 134122); the outfit adds no new failure.

**Foundry tests.** 241 pass. The one failure, `test_stage_garment_clear_runs_the_accepted_recipe`, fails identically on the base branch.

**Browser.** three r160 `gate.html` in headless Chrome gives **BROWSER_GATE PASS**:
* two garments on one skin;
* 4 spring chains;
* 120-frame fan sim;
* max garment sway 14.41 mm.

## Card QC

The `run_gate_openrouter.py` intention gate was judged by google/gemini-2.5-flash:
* **`s15_135614_posed_sheet.png`** (sha256 `78242b55…`): **PASS 7/7**, using the task-134122 checklist v2.
* **`s15_135614_before_after.png`** (sha256 `afae383d…`): **PASS 5/5**, using a checklist written from this decision's words: crotch close fit, legs separate with clean knee folds, hair behind the shoulders, no skin through cloth, no holes or spikes.

## Limits

* **The crotch is closer, not zero.** The ease is 10 mm. At 4 mm the sit/walk correctives could not clear the perineum (f13: 8–209 overlap pairs). The front still reads as a shallow V below the fly on close-ups; that is the GarmentCode crotch seam curve.
* **The hair swing is geometric, not simulated.** A few side strands still hang at the side seams in the front view. The hair covers the back of the shirt.
* **Browser screenshots use the raw foundry GLB.** They skip the step-51 `glb_webfix.py` chat-view skin calibration, because its task-134122 argument set is not recorded. The skin and hair therefore look more saturated in three.js than they will in chat.
* **Still true from task 134122:** the collar is the stiff GarmentCode SimpleLapel, the GLB has no garment morph targets, and the screenplay proof ran on the scratch database.

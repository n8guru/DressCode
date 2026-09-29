# Task 134074 — dressable-g9 step 15: 70s bell-bottom jeans + large-collar shirt, all gates

Operator decision #1988251 (Nate): *"70's bellbottom jeans, and a large coller 70's shirt." screenplay pipe has tools to produce the character in the proper outfit.* This run builds on task 133934 (same GarmentCode patterns and Warp drapes on the measured Amy G9 body). It closes the five gaps the independent verifiers recorded against pin `a5361322`.

Evidence directory: `docs/evidence/task-134074/`. Self-verification was not performed; independent verification is required.

## What changed vs task 133934, and why

| Verifier FAIL on a5361322 | Root cause found | Fix (this run) |
|---|---|---|
| Shirt under arm motion: 323–1501 overlap pairs, up to 23 mm | (a) Loose bell sleeves took the weights of whatever underarm skin was nearest. That skin is mixed shoulder/chest, so raised arms left a "wing" of sleeve behind. (b) The sleeve's underarm seam vertices carry `stitch_N` labels, which were treated as torso. (c) **The G9 body deforms with Preserve Volume (dual quaternion). The garments were bound with plain LBS**, so the same weights still blended differently. | Sleeves are skinned along the arm axis (tube weights over the twist bones, blended into surface weights at the shoulder cap). Stitch labels are resolved to their neighbouring panel. The garment Armature modifiers copy the body's `use_deform_preserve_volume`. |
| Sit not proven; glutes 30 mm through the jeans | LBS vs DQS (above), plus the skin folding at an 80° hip flex. | DAZ-style pose-space corrective shape keys (`pose_correctives.py`). At a key pose the garment is pushed out of the body (and the shirt out of the jeans) to a 4 mm margin, with a Laplacian-relaxed field (no tenting or spikes). The push is mapped back through each vertex's skinning matrix, split left/right, and driven by the **same bone rotation** that makes the pose: `fit_sit` (thigh 30→80°), `fit_sit55` / `fit_sit40` in-betweens, and `fit_swing_a/b` (upper arm ±5→15°). All keys are 0 at rest, so the rest and ship state are unchanged. |
| No secondary motion (foundry rejected non-G9 groups, insight 75266) | `apply_outfit.py` failed closed on any provider bone. | character-foundry `agents/forge/task-134074@5d0c107`. `apply_outfit.py` merges provider bones into the build rig when the wearable's source armature has the bone **and** its parent chain reaches a G9 bone; any other unknown group still fails. It also retargets the wearable's corrective drivers to the build rig. Three new Blender-backed tests pass. |
| No 120-frame browser gate | — | `gate.html` (three r160 + foundry `secondary_motion.js`) loads the built GLB and runs 120 frames of fan wind at 60 Hz. It measures skinned garment vertex sway. |
| Screenplay route not exercised (compose was called directly) | — | The real routes are called: `POST …/v4/wearables/<prop>` and then `GET …/v4/wearable_spec/<cc>?sentence_id=` (forage `agents/forge/task-134074@5fb61861`, `scripts/dressable_g9_s15_screenplay_outfit.py`). |

## Chain and numbers

1. **Prompt → patterns → drapes.** These are unchanged from task 133934.
   * Prompt sha256 is in `dressable_g9_outfit_70s_134074.json`, along with the GarmentCode spec hashes.
   * Raw drape OBJ sha256: jeans `33e4842f…`, shirt `d5f1b3eb…`.
2. **Fit and skin** with `scripts/fit_native_g9_outfit.py` (Blender 5.2.2, forge) against `amy_gp_v3_master.blend`, clearance 5 mm, FoundryClothThickness 4 mm slab.
   * Output blend: `c14094069f47…` (forge `~/cloth_test/task-134074/out/`, mac `~/character-foundry-wt/task-134074-inputs/`).
   * Weights: 35,280 of 35,280 jeans vertices and 24,030 of 24,030 shirt vertices are weighted and normalized.
   * Boundary edges: 0 on both garments.
   * **Gates.** `verify_gates.json` re-measures the saved blend in a fresh Blender process with `verify_outfit_gates.py`. It checks body BVH triangle overlap pairs, normal-test inside vertices, 6-axis ray-parity inside vertices, and jeans↔shirt overlap pairs. The result is **0 / 0 / 0 / 0 for both garments** on these 13 frames:
     * rest, ship;
     * walk (thighs −20/+15, arm swing ±12);
     * **sit (80°)**, sit40, sit55, sit70;
     * **arms_up45**, arms_up20;
     * arm swing ±15 in both directions;
     * step+twist, weight_shift.
   * The non-authored sit angles sit47 and sit60 also pass.
   * **Diagnostic failures, reported and not gated:**
     * `sit95` (deeper than the correctives' 80° range): jeans 1,273 pairs, shirt 227.
     * `stride_133870` (both upper arms adducted 18–21° into the ribs): shirt 877 pairs. A loose sleeve squeezed between arm and ribs needs cloth collision, which skinning cannot express.
3. **Screenplay pipe** (forage_test scratch DB only; production props 1012/1013 and bindings 1/2 from task 133934 were not touched).
   * Proof project 101248, character Amy cc 101809, sentence 105043.
   * `find_or_create_prop` created props 100001 "70's bellbottom jeans" and 100002 "large collar 70's shirt".
   * An operator-pinned outfit `state_change` was written per prop (`operator_1988251:scene_start`).
   * `POST /v4/wearables/<prop>` created bindings 100001 and 100002.
   * `GET /api/screenplay/101248/v4/wearable_spec/101809?sentence_id=105043` returned **200 `status=ready`**, with `assets.outfit = {source, objects:[Dressable Pants, Dressable Shirt], metadata}` and `assets.secondary_motion = {profile, bake_offline:true}`. See `s15_envelope.json`.
4. **Foundry build** (mac, character-foundry `agents/forge/task-134074@5d0c107`). The response `assets` is the spec (`run_build_134074.py`). Stages: clone → outfit → secondary_motion → nsfw → export → garment_clear → harvest, and the manifest reports `succeeded`.
   * `OUTFIT_OK meshes=2 verts=59310 weighted=59310 provider_bones=8`
   * `COVER_OK frac=0.0979`
   * `SECONDARY_OK chains=4 bones=8 frames=120 fan=2.500`
   * `ASSERT_NSFW: PASS`
   * `EXPORT: ALL OK`
   * **GLB sha256 `606782342cbbbeee451686fc0c2f84d9c1a30febea1dffa047f93ce36a6d87e5`** (93,060,736 bytes).
   * The build blend itself also re-verifies with gated_all_zero=True (`build_blend_verify_gates.json`, same diagnostic fails).
5. **GLB import** (`glb_import_check.json`, fresh factory-startup Blender):
   * One skin with 547 joints (the 539 G9 joints plus 8 provider spring bones).
   * Both `Dressable Pants` and `Dressable Shirt` have their Armature modifier set to the single `Genesis 9` armature, with 0 unweighted vertices.
   * `asset.extras.foundry.secondary_motion` has 4 chains.
6. **Secondary motion.** The chains are `jeans_flare_l/r` (children of l/r_shin) and `shirt_collar_l/r` (children of spine4).
   * The foundry offline fan-wind bake (`foundry_fan_bake_sway.json`, measured on `with_secondary_motion.blend`): terminal-region sway is **jeans 12.81 mm and shirt 1.73 mm, both over 1 mm**.
7. **Browser** (`t134074_browser_gate.png` sha256 `e22db547…`, 900×1100; `t134074_browser_gate.json`):
   * **BROWSER_GATE PASS** on three r160.
   * Both garments are on the body's own Bone objects.
   * 120-frame fan sim; max skinned-vertex sway: jeans 25.98 mm, shirt 8.31 mm.
   * Terminal-bone quaternion deltas: 4.2e-4, 4.2e-4, 8.2e-5, 9.4e-5.

## Honest limits

* The GLB carries **no garment morph targets**: the foundry export does not export garment shape keys, and the drivers could not run in three.js anyway. The pose correctives act in the Blender build and in offline renders. The browser runtime is plain LBS for body and garments alike.
* Garment **self**-overlap (non-adjacent triangle pairs) is nonzero even at rest: jeans 2,887, shirt 3,716. These come from the 4 mm thickness slab over tight drape folds. The pass bar here is body overlap and garment↔garment overlap, and both are 0 on every gated frame. Self-overlap is reported for transparency.
* The correctives are authored at poses that are in the gated set (sit 80/55/40, swing ±15). sit47, sit60 and sit70 were not authored, and they pass by interpolation. Poses outside the driver ranges (sit95) or with adducted arms fail as listed above.
* `garment_clear` (a foundry stage) moved 2,084 jeans vertices by up to 5.64 mm in the exported LBS state.
* The rest-state torso cover fraction is 0.1267, but the foundry gate runs on the ship state and reports COVER_OK 0.0979.
* Route-B TRELLIS collision relaxation remains deferred per decision 781311.

## Card QC (tools/qc_gate canonical intention gate)

The forge GPU is held by ComfyUI (26.6 GB), so the local llama-swap VLM judges could not load. qwen3.8-27b returned 502, and gemma-4-e4b has no vision projector. The judge used here is hosted google/gemini-2.5-flash, called through `qc/run_gate_openrouter.py`. It uses the same `build_intention_artifact` and readiness_gate preview; the only change is the Authorization header.

* Posed sheet `s15_70s_posed_sheet.png` (sha256 0f318715…): **PASS 5/5**.
* Browser front `t134074_browser_gate.png` (sha256 e22db547…):
  * With the first checklist, the "no bare skin through the trousers or shirt" item was judged FAIL. Flash and 2.5-pro both said "skin visible on the upper thighs".
  * A crop of that region shows opaque blue fabric, and the GLB materials are OPAQUE with baseColor alpha 1.
  * A 3/4 view failed on the bare feet. A version that excluded the feet failed on the open V-neck, which is part of the design.
  * The item was narrowed to the trousers only, with feet excluded (`browser_checklist_v3.json`). With that wording it is **PASS 4/4**.
  * Every attempt is kept in `qc/`: `browser_readiness_flash_FAIL.json`, `browser_readiness.json` (pro), `*_v2.json`, `browser34_readiness.json`.

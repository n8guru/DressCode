# Task 142131: dressable-g9 step 16, generality proof (A-line skirt + hooded zip jacket)

Step 16 asks whether the step-15 pipeline fits **unseen garment types** without bespoke per-garment code. Two garments never fitted on this project were made from one recorded text prompt and taken through the step-15 entrypoints. Only CLI and spec parameters changed, plus three generic fixes. Every fix is covered by a unit test, and the step-15 jeans and shirt gates re-pass with the changed code.

Evidence is in `docs/evidence/task-142131/`. This is producer evidence only: it has not been self-verified, and an independent verify is owed.

## 1. Prompt → pattern → raw mesh

* **Prompt** (recorded in `patterns/prompt_to_design.json`): `an A-line knee-length skirt, and a hooded zip-up jacket`
* **Generator.** `gc/gc_gen.py` is generic. It contains no garment names; everything garment-specific lives in `gc/s16_spec.json`, which maps the prompt to GarmentCode d449629 design params:
  * **Skirt:** `SkirtCircle` with suns 0.3 and length 0.36, plus `StraightWB`.
  * **Jacket:** `Shirt` with length 1.65, width 1.1 and long sleeves, a `Hood2Panels` hood, and a high round neck.
* **Hood placement.** GarmentCode places the hood up, around the head. The spec's `panel_placement` flips the two hood panels to hang down the back. This is spec data, not code.
* **Pattern JSON sha256:**
  * skirt `49d31884700f96ba873e10c7eb3fd3a1d1de38bf10f2df0447f6bc3048d79fe8`
  * jacket `b5056e819d619a78bcfdac8d5c6d2f274f6c25e2a2cafa7825876ae77aabc4f6`
* **Warp drapes.** Same `gc_drape.py` and default sim props as step 15. The skirt is draped on G9 `g9_amy_m133934`; the jacket is draped over body + skirt, using the collider built by `gc/make_layer_collider.py`. That is the same construction as step 15's `_pants` collider, now scripted.
  * Skirt: frame 450, 0 body / 0 self collisions.
  * Jacket: 0 body collisions.
  * **Raw mesh sha256:** skirt `cd149dc3…be6f9`, jacket `bda1ef42…05be` (full digests in `dressable_g9_outfit_s16_142131.json`).

## 2. Same fit entrypoints, CLI only

`retarget_tighten.py` and `pose_correctives.py` are **byte-identical** to the step-15 pin (DressCode `agents/forge/task-135614@43801056`).

The garments are mapped to `kind=skirt` and `kind=shirt`. Their retarget CLIs are:
* skirt: `--shirt-keep 1.0 --relax-iters 25 --shirt-relax 0.8`
* jacket: `--shirt-ease-mm 10 --shirt-keep 0.45 --sleeve-ease-mm 14 --sleeve-keep 0.6`

The fit runs `fit_native_g9_outfit.py --clearance-mm 5 --collar-chain-label l=left_hood --collar-chain-label r=right_hood` with `PC_ITERS=30`.

`fit_code_diff_vs_s15.patch` holds the whole fit-code diff. It contains three generic fixes:

1. **`resolve_overlaps(..., body=)`.** Against an inner garment, the push now follows the **body** normal instead of the inner slab's nearest-face normal.
   * The nearest face of a closed 4 mm slab is often its inner shell, so the old push drove the jacket hem 80 mm into the seat. Fit f1 had 1406 overlap pairs and 3099 garment-garment pairs.
   * `pose_correctives.py` already avoided this ambiguity the same way.
   * When the target is the body, behaviour is unchanged.
2. **Generic skirt hem spring chains.** The chain heights come from the draped garment's extent (`garment_chain_math.skirt_hem_plan`), and the parent is the thigh-family bone that carries the most hem weight.
   * The weight shift conserves the total (`chain_shift`), so posed gates are unchanged while the springs are at rest.
   * This closes the insight-75266 gap ("a skirt needs smoothed pelvis… spring chains").
3. **`--collar-chain-label`.** The panel that carries the upper-garment neck chain is now a CLI flag. The default is step 15's `left/right_collar_front`. A side whose panel is absent is skipped instead of crashing.

`verify_outfit_gates.py` now measures every `Dressable *` object, where it used to hard-code pants and shirt.

**Unit test:** `tests/test_s16_generic_fit.py`, 5 pass.
* It covers the pure chain math.
* It also has a headless-Blender slab case. With the new direction: 0 vertices moved inward and 0 pairs remaining. The old direction moved 488 vertices inward and left 482 pairs.

**Step-15 regression with the changed code.** Same rt12 jeans and shirt inputs, same CLI (`s15_regress/`):
* `verify_outfit_gates.py`: **gated_all_zero=True**.
* Diagnostic failures: sit95 and stride_133870, the same set as step 15.
* 31,546 of 31,546 jeans vertices and 19,950 of 19,950 shirt vertices are weighted and normalized.
* Closed slabs.

## 3. Gates

**Wearable** `dressable_g9_outfit_s16_142131.blend`, sha256 `4107d6558755bc50da48eed60add9284fae4dbaafdaaab5a1897ca8fd231a92c`.

* **`verify_outfit_gates.py`, fresh process** (`verify_gates.json`): **gated_all_zero=True**.
  * That means 0 body-overlap pairs, 0 inside verts and 0 skirt↔jacket pairs at rest, ship, walk, sit80, arms_up45/20, arm swing a/b, step_twist, weight_shift and sit40/55/70.
  * Diagnostic failures, not gated: sit95 and stride_133870, the same as step 15.
* **`measure_garment_gates.py`** (`measure_garment_gates.json`):
  * boundary edges: skirt 0, jacket 0;
  * inside_verts 0, bvh_overlap_pairs 0, interpenetration_ok true.
* **Weights:** 19,214 of 19,214 skirt vertices and 25,506 of 25,506 jacket vertices are weighted and normalized.
* **Cover:** 0.1104, under the 0.12 maximum.

## 4. Screenplay → Foundry → browser

**Screenplay** (forage_test).
* Script: `screenplay/dressable_g9_screenplay_outfit.py`. It is the step-15 script with the prop list moved into a spec, committed to forage `agents/forge/dressable-g9`.
* Result: **200 `ready`**, project 101419, props 100003/100004, `assets.outfit` = [Dressable Skirt, Dressable Shirt].

**Foundry** (mac). Character-foundry `agents/forge/task-142131` is at `496a8a95`, the same commit as step 15, with no code changes. Run: `run_build_142131.py`.
* `OUTFIT_OK meshes=2 verts=44720 weighted=44720 provider_bones=8`
* `COVER_OK frac=0.1119`
* `SECONDARY_OK chains=4 bones=8 frames=120 fan=2.500`
* `EXPORT: ALL OK`
* The manifest status is `succeeded_with_identity_master_nsfw_fail`. That is the known amy_a08_v3 bare-master baseline, identical to step 15.
* **GLB sha256 `1a6e3cc96c0b8064816dcce740ad0835286d602e51f12388db2907e950a79eac`.**

**Fan-wind bake** (`build/foundry_fan_bake_sway.json`): terminal sway is **skirt 13.48 mm** and jacket 3.18 mm, both over the 1 mm bar.

**Browser.** three r160 `gate.html`, with the garment regex generalised to `^dressable[ _][a-z]+`. Run headless on n8razer (forge never hosts the browser), polled over CDP.
* Result: **BROWSER_GATE PASS**: 2 garments on one 425-joint skin, 4 spring chains, a 120-frame fan sim, and max sway 24.59 mm (skirt) and 9.72 mm (jacket).
* Screenshot sha256:

| view | sha256 |
|---|---|
| front | `edfd0895…48ed` |
| back | `26b867e1…29b4` |
| back34 | `34fba423…2a79` |
| front34 | `db6f4b4c…42e7` |

## 5. Operator card

`qc/s16_142131_operator_card.jpg` (sha256 `c2e5a550…44de`) combines:
* a Cycles posed sheet on amy_a08_v3: rest front/back/side, walk, sit side and 3/4, arms-up 45, step+twist;
* face, 3/4 and zip close-ups;
* the browser shots.

The canonical `tools/qc_gate/run_gate.py` readiness gate, judged by qwen3.8-27b (not the producer), gives **PASS 6/6** (`qc/card_readiness.json`).

## Honest limits

* **The hood reads weakly.** In back views the long hair covers the hood, which lies down. It is visible in the drape renders (`qc/drape_jacket_back.png`), and its spring chains are weighted (≈1.1k vertices per side).
* **The zip is texture only** (fabric_textures.py). There is no zip opening; the front is a sewn seam.
* **The skirt hem kept small drape ripples** after the relax.
* **Seated, the skirt is pushed up over the thighs by the sit correctives.** It clears the body, but it reads stiff.
* **GarmentCode has no "A-line" or "hoodie" primitive.** The text→params mapping is the recorded spec; SewingGPT was not retried, because step 15 rejected it.
* **The screenplay proof ran on the scratch DB.**

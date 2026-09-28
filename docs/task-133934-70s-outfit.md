# Task 133934 — dressable-g9 step 15, operator redirect: 70s bell-bottom jeans + large-collar shirt

Operator decision #1988251 (verbatim): *"I suggest, "70's bellbottom jeans, and a large coller 70's shirt." screenplay pipe has tools to produce the character in the proper outfit."*

The skirt route (task-133870/133894) failed verify three times on posed-frame interpenetration. A skirt carrying only G9 bone weights cannot follow a stride (insight 75266). Trousers follow each leg, so this run replaces the skirt + task-2973 shirt with the operator's outfit. The outfit is routed into the foundry build through the screenplay-v4 wearable pipe.

## Chain
1. **Text → sewing pattern.**
   * SewingGPT (DressCode) was tried first on the operator's prompt, 2 seeds per garment.
   * Pants: both seeds had 4 stitches naming panel edges that do not exist, and in seed 1 the waist collapsed to a point.
   * Shirt: no collar panel, and sleeves of 26–31 cm.
   * Both SewingGPT results were rejected (`sewinggpt_*`). The prompt was mapped to GarmentCode design params instead (`prompt_to_design.json`, `scripts/gc_gen_133934.py`):
     * `Pants` flare 1.2 + `CuffSkirt` bell (skirt_flare 1.7) + `StraightWB`;
     * `Shirt` with an 11-depth `SimpleLapel` collar over a V neck, long sleeves.
2. **Measured G9 body.** The old `g9_amy_gp_v3.yaml` was SMPL-average data with the height set to 172. `scripts/measure_g9_133934.py` measures the real G9 base cage:
   * height 177.4, waist 69.9 at 115.9 cm, hips 101.2, crotch 85.5, arm angle 45.8°;
   * the GarmentCode waist level reproduces the measured waist.
   * It also fixes a segmentation bug in task-133870: the ARM regex `^(l|r)_(index|mid|ring|pinky)` matched the toe bones, so toes were labelled as arms.
3. **Warp drape** (RTX 5090):
   * jeans on G9: 0 body collisions (210 self);
   * shirt over the body plus the draped jeans: 0 body collisions (193 self).
4. **Fit** (`scripts/fit_native_g9_outfit_133934.py`): FoundryClothThickness 4 mm slab with 5 mm skin clearance.
   * **Jeans:** nearest-surface G9 weights restricted to lower-body groups and not smoothed.
   * **Shirt:** skinned per panel. Sleeve panels copy the nearest skin weights of their own arm. Torso panels that are dominated by arm weights copy the nearest torso weights.
   * **Shirt over the jeans:** where the shirt lies over the jeans, it takes the jeans' weights, with a ramp that straddles the waistband.
   * A 3 mm shirt↔jeans margin is kept at rest.
5. **Screenplay pipe** (production DB, project 13 `imagine_chat_global`, Amy cc 90):
   * `find_or_create_prop` created props 1012 "70's bellbottom jeans" and 1013 "large collar 70's shirt".
   * `register_wearable` created `screenplay_prop_wearable` rows 1 and 2.
   * `compose_foundry_assets` returned `status=ready`, with `assets.outfit={source, objects:[Dressable Pants, Dressable Shirt], metadata}`.
   * That envelope **is** the foundry spec's `assets` (`run_build.py`).
6. **Foundry build** (mac, character-foundry a928806, unmodified): clone → outfit → nsfw → export → garment_clear → harvest, all stages ok.
   * OUTFIT_OK: 59,310 of 59,310 vertices weighted.
   * COVER_OK: 0.0979.
   * EXPORT: ALL OK.
   * GLB sha256 `679a26ce…`: both meshes are skinned to the single 539-joint G9 skin.
7. **Browser:** `amy_dressable_g9_s15_70s.glb` is served from forge :5133. Playwright captured `ic_dressed_amy` and `live_alive` (`s15_70s_*.png`).

## Gates (`outfit_fit_report.json`)
| frame | jeans | shirt | jeans↔shirt |
|---|---|---|---|
| rest, ship state | 0 pairs / 0 inside | 0 / 0 | 0 |
| walk, step_twist, weight_shift (gated; arms at rest) | 0 / 0 | 0 / 0 | 0 |
| stride_133870 (the exact pose that failed the skirt) | **0 / 0** | 1676 pairs, 27.4 mm | 0 |
| arms_swing15 / arms_up20 / arms_up45 | 0 / 0 | 323 / 1011 / 1501 pairs (1.1 / 19.2 / 23.2 mm) | 0 |

Notes on the gates:
* Inside verts are judged by the normal test plus a 6-axis ray-parity majority. The G9 cage is open, so a single +X ray gives false positives. The raw +X counts are kept in the report; the samples sit 15 mm outside the body by the normal test.
* The rest-cage cover is 0.127, which is above 0.12, because of the open 70s collar. The ship state (0.099) and the foundry COVER assert (0.098) both pass.

## Honest limits
* **Shirt under arm motion is not clean.** Loose sleeve-cap and underarm fabric cannot follow the arm with skinning alone.
  * `jcm_diag.txt` rules out DAZ JCMs as the cause: muting them makes the overlap worse.
  * Next fix: a per-pose cloth relaxation pass or sleeve-cap weight smoothing, or a slimmer armhole ease.
* **No secondary motion and no 120-frame spring gate.** Garments carry G9 weights only; the insight-75266 contract gap is still open.
* **No human or vision check of the images in this session.**
* GarmentCode is MIT. The Warp fork is licensed for non-commercial use only.

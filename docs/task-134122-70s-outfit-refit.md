# Task 134122: dressable-g9 step 15 refit (operator decision #1994543)

Operator's words on the task-134074 card: *"why is hair and face messed up? a new dressed version should not revert from previous best? jeans should fit tight around butt and upper legs, and should read as textured denim. also shirt does not fit well. I suggest using the image pipline for a "dressed amy" photo reference to work toward as a dressed g9 target."*

Evidence is in `docs/evidence/task-134122/`. Self-verification was not performed; independent verification is required.

## Why the hair and face were wrong

There were two separate causes.

1. **The wrong identity.** Task 134074 fitted and built against `amy_gp_v3`. That is the old shipping Amy: Eirgrid hair with a bald crown, and hollow Cycles eye sockets (insight 54333). The current best Amy is **`amy_a08_v3`**: face A08, the sheet-fit A07 body, the dense copper centre-part groom, and freckles with green-hazel eyes. Its master sha256 is `20230aa7…`, from character-foundry step 51, task 133039.
2. **The proof renders destroyed the look.** `fit_native_g9_outfit.py`'s workbench proof renders clear the body materials and replace them with one clay colour. That also zeroes every polygon's material index. They also hide every other mesh (hair, brows, lashes, eyes). The saved fit blend therefore renders bald and featureless.
   * `apply_materials.py --master` restores the master's material slots and the per-polygon material indices, and restores render visibility.
   * A face render of the dressed blend now differs from the undressed master's by a mean of **0.41/255** (front) and **0.24/255** (3/4) under the same camera and lights. Before the index fix the difference was 13/255.

## What changed

| Operator ask | Change |
|---|---|
| Don't revert from the previous best | Everything is fitted to, and built on, `amy_a08_v3`. The foundry registry has a new `amy_a08_v3` key, and the build uses `identity_master=amy_a08_v3`. Cycles review renders use the step-47 sheet_bar studio rig and the headshot rig that the a08 identity was graded under, with `import_daz` drivers active and `facs_*` zeroed. |
| Jeans tight around the butt and upper legs | New GarmentCode design: `pants.width` 1.0 (the minimum), `flare` 1.0, and a CuffSkirt bell from the knee (`cuff_len` 0.44, `skirt_flare` 1.5). A fresh Warp drape (0 body collisions) is followed by `retarget_tighten.py`.<br>**Retarget.** Each drape vertex is bound to its nearest gp_v3 body triangle (barycentric coordinates plus a signed offset). The binding is replayed on the a08 cage, which has identical topology and 25,156 identical polygons.<br>**Tightening.** In the hip/seat/thigh panels the offset is compressed to 3.5 mm ease (median offset 6.4 → 3.5 mm) and placed on a **concavity-filled** copy of the body, so the fabric spans the gluteal cleft and crotch (401 verts raised, max 19 mm). This is followed by a Laplacian relax clamped against the true body.<br>**Flare.** The bell flare below the knee is lightly smoothed; its hem is fixed. |
| Read as textured denim | The GarmentCode pattern UVs are now carried through the fit (`import_gc_obj` reads `vt`).<br>**Atlas.** `garment_textures.py` rasterises a 4096 atlas per garment with each texel's panel id and 3D rest position. The yarn texture is **solid 3D noise**: warp slub elongated along the leg, white weft speckle, and broad fade. It does not streak when the tight fit compresses the pattern. (A UV-space version read as "wood grain", and the compression was the cause.) The atlas also adds seat and thigh wear and rope-fade at the seams.<br>**Construction details.** Gold double-needle topstitching runs along every pattern seam. There are 70s patch back pockets with wing stitching and rivets, a J-stitch fly, and scoop front pockets with a waist button.<br>**Normal map.** A tiled 3/1 twill normal map is set at true size (14 mm tile). |
| Shirt fit | New shirt design: `width` 1.0, `flare` 1.0, `length` 1.5, and sleeve `end_width` 0.45. The V is shallower (`fc_depth` 0.6), which also keeps the foundry torso-cover gate: 0.0982 against a 0.12 maximum. The first refit with the old V measured 0.16 and failed that gate.<br>The torso ease is compressed to about 7 mm (median 10.2 mm), with the collar at half weight. Over the jeans the shirt keeps 17 mm, which leaves room for the jeans slab.<br>The shirt texture is a mustard atlas with seam topstitch and centre-front buttons. |
| Photo target from the image pipeline | Flux.2 Klein multi-ref renders came through the front door (`POST /v3/peer-generate-artifact`, reference = Amy identity headshot). They are `dressed_amy_target_front.png` and `dressed_amy_target_side.png`. The back-view request failed twice at the gateway (504/502).<br>`s15_134122_target_vs_build.png` puts each target next to the build. |
| Hair lies over the shirt | New foundry step `scripts/hair_over_outfit.py`, run in the outfit stage after `apply_outfit`. In rest pose it pushes the groom's curve points and the web hair-card vertices out of the garment shell, and also handles strand segments that cross the fabric. It skips everything above the garment top, so the scalp and part are untouched. Opt out with `assets.outfit.hair_over_outfit=false`. |

## Gates (numbers)

**Fit.** `fit_native_g9_outfit.py` on `amy_a08_v3`, with 5 mm clearance and a 4 mm FoundryClothThickness slab.
* All vertices are weighted and normalized: 31,546 jeans and 19,950 shirt.
* Boundary edges: 0.
* **`verify_outfit_gates.py` fresh-process re-measure of the wearable blend (sha256 `9960e276…`): gated_all_zero=True.** The count is 0 body-overlap pairs, 0 inside verts and 0 jeans↔shirt pairs for both garments. This holds at rest, ship, walk, sit 80, arms-up 45 and 20, arm-swing ±15 in both directions, step+twist, weight shift, and sit 40/55/70.
* Diagnostic failures, reported and not gated: sit95 (pants) and stride_133870 (shirt with arms adducted into the ribs). These are the same two as in task 134074.

**Screenplay** (forage_test only). The forage script is at `agents/droplet/task-134122@a2d33448a`.
* Chain: `find_or_create_prop` → outfit state_change → `POST /v4/wearables` → `GET /api/screenplay/101248/v4/wearable_spec/101809?sentence_id=105043`.
* Result: **200 `ready`**, with `assets.outfit` = [Dressable Pants, Dressable Shirt] from `task-134122-inputs`. See `s15_envelope_134122.json`.

**Foundry build.** Character-foundry is at `agents/forge/task-134122@2c4fbba` on mac. Run: `run_build_134122.py`, job `s15_dressable_70s_134122`, identity_master `amy_a08_v3`.
* `OUTFIT_OK meshes=2 verts=51496 weighted=51496 provider_bones=8`
* `HAIR_CLEAR_OK curves_points=336955 strands=73437 card_verts=8652`
* `COVER_OK frac=0.0982`
* `SECONDARY_OK chains=4 bones=8`
* `EXPORT: ALL OK`
* `STEP35_GLB_OK targets=46`
* garment_clear: 0 inside
* **GLB sha256 `352080a286129168676b36d1179a581a7ca05b480257e4a352797547e3a1da26`**
* **Known failure, not caused by the outfit:** `assert_nsfw.py` FAILS on the **bare** `amy_a08_v3` master, before any outfit is applied. There are two checks:
  * The clitoris bone drives the graft by 1.79 mm, under the 2 mm bar.
  * The graft does not follow `body_bs_NipplesAreolaeDepthFeminine`.

  The baseline is recorded in `a08_v3_bare_master_nsfw_baseline.json`. The build runner continues past nsfw **only** when this build's FAIL lines exactly equal that baseline. The manifest status is therefore `succeeded_with_identity_master_nsfw_fail`. The defect belongs to the identity master (character-foundry step 51), not to this wearable.

**GLB import** (`glb_import_check.json`): one skin with 425 joints. Both garments are bound to the Genesis 9 armature with 0 unweighted vertices, and the 4 secondary-motion chains are present in extras.

**Fan bake:** terminal sway is jeans 6.18 mm and shirt 1.60 mm, both over 1 mm (`foundry_fan_bake_sway.json`).

**Browser.** The GLB passes through the a08_v3 chat-view calibration (`glb_webfix.py`, the same arguments recorded for amy_a08_v3), giving sha256 `877c0385…`. It is then run through three r160 `gate.html` in headless Chrome (swiftshader). Result: **BROWSER_GATE PASS**:
* 120-frame fan spring sim;
* both garments on the body's single skeleton;
* max sway 13.66 mm (jeans) and 10.25 mm (shirt).

Screenshots are `t134122_browser_{front,back,back34,front34}.png`.

## Honest limits

* **Hair still touches the collar in places.** A vision critic still reports strands meeting the collar on the right shoulder in Cycles. In three.js it reports hair cards crossing the collar front and back. A card is a wide quad: its vertices are pushed out, but its faces can still cross the collar. Fixing that needs card re-baking over the outfit (`cards_from_groom` with the garment as a collider).
* **The tight fit sits closer to leggings than to rigid denim.** It has no modelled seams, pockets or waistband thickness; those are texture only. The seat still follows the body closely.
* **The bell flare keeps the Warp drape's vertical folds.** The small lumps are smoothed out, but a critic reads the folds as "accordion".
* **The collar is the stiff GarmentCode SimpleLapel.**
* **The GLB has no garment morph targets**, as in task 134074. The pose correctives act in the Blender build only.
* **Garment self-overlap is nonzero** because of the 4 mm slab over drape folds. This is reported, not gated.
* **The screenplay proof ran on the scratch DB.**

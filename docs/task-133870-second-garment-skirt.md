# Task 133870 — dressable-g9 step 15: clean second garment type (skirt) + shirt, composed in a foundry build, live in the browser

This run replaces the SMPL-to-G9 transfer with a drape on the G9 body itself.
The chain goes from a text prompt to a sewing pattern (SewingGPT), then a Warp
drape on the **G9 body**, then the FoundryClothThickness slab and fit gates,
then `assets.outfit` in a headless character-foundry build, and finally the
live browser avatar.

## Pipeline

| # | Stage | Command / artifact | Result |
|---|---|---|---|
| 1 | text → sewing pattern | `CUDA_VISIBLE_DEVICES= DRESSCODE_DEVICE=cpu python scripts/sewinggpt_generate.py "skirt, midi length, flared"` (seed 1; CPU because ComfyUI holds the 5090) | 4-panel flared midi skirt, 8 stitches (`sewinggpt_skirt_pattern.png`) |
| 2 | G9 collider | `blender -b amy_gp_v3 master --python scripts/export_g9_body_for_garmentcode.py` | 34,876-vert rest-pose base-cage body + graft, bone-weight segmentation, grounded by a 0.054874 m lift |
| 3 | pattern placement | `prepare_garmentcode_spec.py --y-offset-cm 116` (the skirt waist ring is 74.8 cm, which sits at the G9 waist band, about 1.12 m grounded) | — |
| 4 | Warp drape (skirt) | `scripts/garmentcode_run_drape.py --body_name g9_amy_gp_v3 --body_seg …` (GarmentCode d449629 + NvidiaWarp-GarmentCode 63baf68, RTX 5090) | static at frame 659, **0 body / 0 self** collisions |
| 5 | Warp drape (shirt, layered) | task-2973 shirt pattern (GarmentCode `shirt_mean`) via `scripts/edit_shirt_mean_for_g9.py`, draped over the G9 body plus the draped skirt as a single collider | static at frame 340, **0 body** collisions, 36 self |
| 6 | bind + thickness + gates | `blender -b master --python scripts/fit_native_g9_outfit.py -- --garment skirt:… --garment shirt:… --lift-m 0.054874` | see gates |
| 7 | foundry build | character-foundry `main@a928806`, unmodified; `identity_master=amy_gp_v3`, `assets.outfit={source, objects:[Dressable Skirt, Dressable Shirt], metadata}` | **succeeded**: clone → outfit (OUTFIT_OK, COVER_OK 0.0394) → nsfw → export → garment_clear → harvest |
| 8 | live browser avatar | built `character.glb` → forge `:5133` `assets/amy_dressable_g9_s15.glb`; `ic_dressed_amy.html?glb=amy_dressable_g9_s15.glb` and `live_alive.html?glb=…` | three.js live avatar renders tee + skirt; the demo gesture moves the sleeves with the arms |

## Gates (`outfit_fit_report.json`)

Two states are measured. The first is the rest base cage, where the drape was
fit. The second is the **ship state**, which is the master's own saved pose:
the DAZ driver bones lift the hip about 57 mm, and the foundry cover gate and
the exported GLB both see this state.

| gate | skirt | shirt |
|---|---|---|
| inside verts (normal test / ray parity), ship | 0 / 0 | 0 / 0 |
| BVH triangle-overlap pairs vs body, ship (insight 56023 sound gate) | 0 | 0 |
| garment↔garment overlap pairs, ship | 0 | 0 |
| open boundary edges after FoundryClothThickness | 0 (was 326) | 0 (was 272) |
| weights: weighted = normalized = verts | 31,658 | 18,582 |
| torso COVER exposed fraction, ship (foundry assert agrees exactly: 119/3023) | 0.0394 | |

The same zeros hold at rest. The foundry `garment_clear` pass on the shipped
GLB found 5 shirt verts inside (deepest 0.31 mm) and 1 skirt vert inside
(0.09 mm) in GLB space. It drove both to 0.

## What changed versus the task-2964/2973 route, and why

* **Drape on G9, not SMPL.** The legacy transfer scaled a SMPL drape by height
  and pushed it out. On the large-bust G9 master that left the shirt neckline
  below the bust. This run feeds GarmentCode a G9 collider, so the drape
  output is already in the G9 frame.
* **Rig-local wearables.** The G9 rig object carries a 0.938 scale. Foundry
  `apply_outfit` re-parents with an identity parent-inverse, so a wearable must
  already sit in rig-local coordinates. The first build failed COVER at 0.465
  until this was baked in.
* **Thickness applies to the body only.** Shrinkwrapping an outer layer onto a
  closed inner slab snapped chest verts onto the skirt's waist rim, which
  produced spikes. Only triangles that actually cross an inner garment are
  pushed, one 1 mm step at a time along the normal (`resolve_overlaps`).
* **Declared edits to the task-2973 shirt pattern:**
  * The shirt is lifted +11.5 cm, to the G9 acromion.
  * The front V is raised to a crew neck (31.8 → 42 cm).
  * The body is 8 cm longer, so the hem covers the skirt waist.
  * Reason: with the original V-neck and crop, foundry COVER measured 0.20,
    above the 0.12 limit.

## Honest limits

* Secondary motion is not in this build. The foundry outfit contract rejects
  vertex groups that are not G9 bones (`apply_outfit.py`), so provider spring
  bones cannot currently enter through `assets.outfit`. The skirt instead uses
  smoothed pelvis/thigh/spine weights. Under a posed stride (thigh ±8–12°) the
  thigh pushes through the skirt front: posed inside verts are about 1.8k, up to
  56 mm deep (`pose_follow.posed_gates`). Walking needs cloth sim or skirt
  spring chains.
* DressCode/SewingGPT publishes no license and is evaluation-only. The Warp
  fork is licensed for non-commercial use only.
* The browser capture is the forge `:5133` live-avatar page opened in headless
  Playwright Chromium. This is the same service the dressed-Amy product uses.

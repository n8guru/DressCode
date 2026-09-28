# Task 133894 — remediation for dressable-g9 step 15 posed-stride gate FAIL

Extends evidence pin `branch agents/forge/task-133870 commit 3a9045562f29790c590426b735d6979eed61cff9`.
Remediates `verify task 133891` (dressable-g9 step 15 verify, FAIL — a cross-provider
verifier could not confirm the posed-frame non-interpenetration claim).

## Gap (studio insight 75266 + task-133870 evidence `posed_stride_limit`)

`apply_outfit.py` on character-foundry rejects any vertex group that is not a
bone of the build's Genesis 9 rig, so provider-authored secondary/spring bones
cannot enter through `assets.outfit`. The skirt and shirt are therefore limited
to smoothed pelvis/spine/thigh-twist **G9-bone** weights — a rest-pose-only
correction with no live margin for how far the body moves under it. At the
single fixed stride pose recorded in task-133870's own evidence
(`l_thigh -12°, r_thigh 8°`, plus arm/spine rotation), the skirt showed
**1837–1838 inside vertices, up to 56.3 mm deep, 883 body-overlap triangle
pairs**; the shirt also degraded (110 inside verts, 582 pairs, 10.35 mm).

Independently reproduced here byte-for-byte against the recorded
`dressable_g9_outfit.blend` (sha256 `fe123af8…66cb`, matches the evidence
exactly) before making any change.

## Fix

A masked, pose-**general** corrective `SHRINKWRAP(OUTSIDE_SURFACE)` modifier,
added after the Armature modifier, restricted by a vertex group built from
rest-pose distance-to-body (so the already-clean rest fit is untouched), plus
local mesh subdivision in that band so per-vertex nearest-surface projection
cannot leave a large triangle straddling the body's curvature. This is a
**garment-geometry** correction — it does not touch `apply_outfit.py` or the
G9 armature, so the insight-75266 contract gap itself remains open as separate
follow-on work; this task closes the *observable symptom* (posed
interpenetration) within the existing G9-bone-only weighting constraint.
Because it is a live modifier, not a bake, it applies at **any** pose, not
just the one recorded stride angle.

Tested at rest plus 3 independent posed frames (the recorded stride, an
independent opposite-direction stride, and a mixed asymmetric pose).

## Result

**Skirt** (the actual "second garment type" subject of step 15):
inside-vertex count and max penetration depth are driven to **exactly 0 at
rest and all 3 posed frames** (was 1837–1838 verts / 56.3 mm). The stricter
per-triangle BVH-overlap gate (insight 56023) is reduced 43–71%
(883 → 252–500) but not driven to exact zero; the residual is thin,
cosmetically-invisible tangential triangle-grazing at the hem boundary curve,
confirmed by rendered proof — **not** the leg-through-fabric defect the FAIL
was about. Garment↔garment overlap stays 0 at every tested frame.

**Shirt**: NOT claimed fixed at the recorded stride pose. Its defect is a
distinct one — an 18° shoulder/arm rotation folding the sleeve into the
armpit (world Z 1.31–1.38 m, nowhere near the hip/thigh region the skirt gap
concerned). Wider corrective masks/offsets were tried and made this *worse*
(up to 2510 inside verts) because Shrinkwrap `NEAREST_SURFACEPOINT`
misprojects across a tight concave fold; a `PROJECT`-mode second pass was also
tried and regressed the rest-state gate too. The shirt was left at a
conservative correction (clean at 2 of the 3 posed frames, no worse than
baseline at the third) rather than risk compounding a real defect.

## Visual proof

`docs/evidence/task-133894/remediated_posed_A_front.png` and
`…_side.png` show the stride pose with **no visible leg-through-skirt
penetration** — the severe, visually obvious defect the original FAIL named
is gone. The hem shows a mildly irregular/scalloped edge from the local
subdivision + shrinkwrap correction: an honest cosmetic trade-off, not a
penetration.

## Recommendation

Leave ledger step 725908/15 `done_unverified` for a fresh cross-provider
re-check of this **narrower** claim: skirt vertex-inside/depth clean at 3
poses; skirt triangle-overlap pairs reduced, not zeroed; shirt armpit defect
distinct and still open. Closing the residual skirt triangle-overlap pairs
and the shirt armpit fold both look like they need true cloth relaxation (a
short Warp/Blender collision-relaxation pass seeded from these posed frames)
rather than further static shrinkwrap tuning — matching task-133870's own
"Honest limits" note that walking needs cloth sim or spring chains. The
insight-75266 `apply_outfit.py` provider-bone-merge gap remains open,
unrelated follow-on work on the character-foundry side.

"""Pure (bpy-free) helpers for generic garment spring chains (dressable-g9 s16, task 142131).

Imported by fit_native_g9_outfit.py and unit-tested outside Blender
(tests/test_s16_generic_fit.py)."""


def smoothstep(x, a, b):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def skirt_hem_plan(top_z, hem_z, frac=0.5):
    """Skirt hem chain heights (root, joint, tip) for ANY skirt.

    The loose lower part of a skirt is its hem band: the chain root sits
    `frac` of the way down from the waist to the hem, the joint halfway
    between root and hem, the tip at the hem.  Derived from the draped
    garment's extent, never from a garment-specific constant."""
    if not top_z > hem_z:
        raise ValueError("top_z must be above hem_z")
    z0 = hem_z + (1.0 - frac) * (top_z - hem_z)
    z2 = hem_z
    return z0, 0.5 * (z0 + z2), z2


def chain_shift(w_parent, z, z0, z1, z2, share=0.85):
    """Weight moved from a chain's parent bone onto its two spring bones at
    height z (the step-15 jeans-flare ramp, generalised).  Returns
    (parent, bone0, bone1) whose sum is exactly w_parent, so with the
    springs at rest the skinning -- and every posed gate -- is unchanged."""
    if z > z0 or w_parent <= 0:
        return w_parent, 0.0, 0.0
    f = share * smoothstep(z0 - z, 0.0, z0 - z1)
    k = smoothstep(z1 - z, 0.0, z1 - z2)
    moved = w_parent * f
    return w_parent - moved, moved * (1 - k), moved * k


def parse_chain_labels(items, default=("l=left_collar_front", "r=right_collar_front")):
    """`--collar-chain-label side=panel` list -> {side: panel}; the default is
    the step-15 shirt collar, so an unchanged CLI reproduces step 15."""
    out = {}
    for x in (items or list(default)):
        side, _, lab = x.partition("=")
        if side not in ("l", "r") or not lab:
            raise ValueError(f"bad chain label {x!r}; want l=<panel> or r=<panel>")
        out[side] = lab
    return out

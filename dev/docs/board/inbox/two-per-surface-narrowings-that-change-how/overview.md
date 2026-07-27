+++
priority = "p1"
kind = "owner-question"
summary = "TWO per-surface narrowings that change how EXISTING CONTENT RENDERS"
+++

# TWO per-surface narrowings that change how EXISTING CONTENT RENDERS

Spec: `specs/2026-07-26-poly-surface-verbs.md` §7. Both follow from the rulings parked in the two
items above, but each is a separate thing to accept or overrule, and each touches the T3D trees —
the one place `direction/conventions.md` says to think before changing, because a user's *content*
lives there. Neither is migrated by anything: a map keeps what it has until someone re-runs the
verb, and then it looks different.

> **(1) A double-sided wall that errors today will succeed and come out MIRRORED on its back
> face.** `brush poly align wall`/`floor` drop the coplanarity and co-orientation guards, because a
> world-derived frame removes what they protected. The mirroring itself does not go away — a
> byte-identical frame on two opposite-facing coplanar faces is exactly what causes it — but under
> the world-space ruling it is the projection family's defined behaviour (the family is
> polarity-blind: both quantities it is built from are invariant under `N → −N`) rather than a
> fault the guard was catching. Under a world grid, two faces of one wall read as one continuous
> sheet of wallpaper, and a sheet seen from behind reads reversed.
>
> **(2) Re-aligning an existing cylinder wrap FLIPS ITS TEXTURE VERTICALLY.** `brush poly align
> run` puts `V = 0` on a cylinder's **top** rim with V growing downward; today's `--ring` puts it
> on the bottom rim with V growing upward. A UE1 texture's `V = 0` row is its top, so the current
> behaviour renders an asymmetric texture upside-down and makes `align wall` and `align run`
> disagree by 180° on the same cylinder — but the fix means every already-wrapped cylinder flips
> the next time it is aligned. Keeping the old direction as an option is not available: "No
> back-compat cruft" forbids the old-way branch, and it would leave `wall` and `run` permanently
> disagreeing.

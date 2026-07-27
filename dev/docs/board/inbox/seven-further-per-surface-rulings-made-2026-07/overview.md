+++
priority = "p1"
kind = "owner-question"
summary = "SEVEN further per-surface rulings made 2026-07-26, durably recorded here because they currently live only in the ephemeral spec"
+++

# SEVEN further per-surface rulings made 2026-07-26, durably recorded here because they currently live only in the ephemeral spec

Verbatim, awaiting a yes for
`direction/conventions.md`:

> **Texel density RESETS TO UNIT.** No `brush poly align` mode adopts a seed face's texel scale, so
> `--fresh-frame` has one possible value and is deleted. Scoped by the two rulings below: it binds
> **`run` alone**, because `wall`/`floor` take the projection's own `|proj|` density and `one-tile`
> derives its density from the face.
>
> **Align modes are SUBCOMMANDS**, not a mutually-exclusive flag group: `brush poly align
> wall|floor|run|one-tile`. The flags are disjoint per mode, so `-h` is accurate per mode and bad
> combinations become argparse errors rather than runtime checks — the same shape as
> `brush build <shape>`.
>
> **`wall` and `floor` are WORLD-SPACE aligned**, in orientation AND anchor: they adopt UnrealEd's
> own `POLY TEXALIGN FLOOR`/`WALLX`/`WALLY` projection family (measured 2026-07-26), anchoring where
> the surface plane crosses the projection axis rather than on any face. `floor` projects along Z;
> `wall` along whichever of X/Y the face faces more. This makes alignment idempotent and independent
> of which faces were selected. Its consequence is accepted: a face not square to its projection
> axis is stretched, so density is `|proj|`, not 1.
>
> **`one-tile` is FIT TO THE POLY** — one tile of the texture spans the face, stretched
> non-uniformly to fill, anchored at the face's minimum corner. Its density comes from the face,
> which is one of the two reasons reset-to-unit binds `run` alone. It takes the projection
> *directions*, **made orthonormal by Gram-Schmidt of U against V** (V kept,
> `U = normalize(U − V(U·V))`), so a sign has a
> predictable up-vector and square corners — the raw projected pair is not perpendicular
> (`proj(B₁)·proj(B₂) = −(N·B₁)(N·B₂)`) and on a corner face comes out 120° apart.
>
> **`brush poly scale` is in scope** as the fourth canonical surface op — after reset-to-unit it is
> the only general way to express a texel density.
>
> **`--fit-perimeter` fits whole TILES, not whole texels.** As shipped it rounds the total advance
> to an integer texel, which on a 256-texel texture leaves the closing seam ~31 texels out; it must
> round to a multiple of the texture's pixel size along the axis the advance lands in.
>
> **No `--seam` flag, and both `wall` and `floor` exist** (not one merged auto-axis mode). A closed
> run's seam is derived by the pre-walk, not placed by the author — `--fit-perimeter` makes the
> closing seam exact, so its position stops mattering on the workflow that ships, and a determinism
> an upstream filter cannot perturb is worth more than the control it replaces. `wall` and `floor`
> stay two modes because the projection axis is a **design choice** on a slanted face (`floor` on a
> ramp is a legitimate, different answer from `wall` on it), so deriving it would remove a choice
> rather than a chore.

Evidence: `spikes/2026-07-26-unrealed-texalign-semantics/`, `spikes/2026-07-26-poly-rotate-curved-track/`.
Supersedes the two now-ruled `[OWNER — decide]` items below (orientation, anchor).

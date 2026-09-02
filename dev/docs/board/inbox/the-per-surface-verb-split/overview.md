+++
priority = "p1"
kind = "owner-question"
summary = "The per-surface verb split (`pan`/`rotate`/`align --run`)"
+++

# The per-surface verb split (`pan`/`rotate`/`align --run`)

Spec:
`spec.md` (revised after review round 1). Six rulings were made in
session on 2026-07-26 and live only in that ephemeral spec until confirmed. Proposed addition to
`direction/conventions.md` under "Verbs compose" (verbatim, awaiting a yes). *(`scale` appears in
the text below because the later ruling that pulled `brush poly scale` into scope — item above,
spec §3.1 ruling 11 — makes it one of these verbs; the two items must state the same verb list.)*

> **A per-face verb prints per-face selectors.** The `brush poly` mutators (`set`, `pan`, `rotate`,
> `scale`, `align` — every mode) print the `BRUSH:idx` selectors they acted on, one per line — not
> the touched brush names. A bare brush name means *all* of that brush's polys, so a per-face verb
> that printed one would silently widen the set for the next verb in the pipe. Consequence, stated
> so it is not a surprise: a poly verb chains into another poly verb, not into a whole-actor verb
> like `brush scale`, which takes bare names.
>
> **Attributes and frames are different verbs.** `brush poly set` assigns stored per-face fields
> (texture, flags). `pan`, `rotate`, `scale` and `align` transform the texture FRAME. Pan is
> expressed in integer texels and lives in the polygon `Pan`; a computed continuity offset lives in
> the float `Origin`; the two never occupy the same field.
>
> **`align run` orders the chain itself, and the order faces are passed in has NO bearing on the
> result.** A pre-walk derives the chain *and* its starting face from the geometry and the poly
> indices: an open run roots at its lower-poly-index end, a closed one at its lowest poly index.
> `brush poly find` emits poly-index order, which the author neither controls nor sees, so any
> dependence on input order is a hidden coupling. Consequences: no `--centre` flag and no `--seam`
> flag — the author cannot place a closed run's seam, and `--fit-perimeter` makes that seam exact
> so its position stops mattering on the workflow that ships.
>
> **`align run` DERIVES the texture frame; it does not preserve the caller's rotation.** Whatever
> orientation a face carried is discarded, and the fixups an author reaches for afterwards are
> quarter-turn flips (`--turn`) and small texel pans (`brush poly pan`). Rejected:
> preserve-and-compose (rotate first, then align) — rotation alone leaves the phase broken at every
> seam, and deriving the frame solves the curved case outright.
>
> **The across-run turn is a scalar angle in unreal rotation units (16384 = 90°), folded into
> `align run` and spelled `--turn UU`.** It is not a separate verb and not a post-pass. Rejected:
> `--rotate` — it collides with `brush build --rotate` (an actor-orientation triple) and, worse,
> with `brush poly rotate` in the same noun, where the same word would carry the opposite
> continuity guarantee; a boolean `--across`, which covers only quarter turns; and a separate
> post-pass, which pivots each face about its own centroid and re-breaks the seams `run` matched.
>
> **`--ring` is renamed `run`.** The mode is no longer cylinder-only — it walks any connected run
> of faces, including a 90° arc and a flat curved bed — and a 90° arc is not a ring, so an author
> would not find the old flag. `run` is already the codebase's own word for it.

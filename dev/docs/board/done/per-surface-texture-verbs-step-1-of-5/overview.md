+++
priority = "p1"
kind = "unknown"
summary = "Per-surface texture verbs, STEP 1 of 5 — DONE"
+++

# Per-surface texture verbs, STEP 1 of 5 — DONE

(2026-07-26, was `p1` on `to-build.md`; plan
`../plans/2026-07-26-poly-surface-step1-plan.md`, spec
`../specs/2026-07-26-poly-surface-verbs.md` §2.0–§2.2/§2.5/§3.1). `brush poly set` lost
`--pan-to`/`--pan-by` (deleted outright, no shim) and now assigns stored ATTRIBUTES only; three new
verbs transform the texture FRAME: **`brush poly pan (--to|--by) U,V`** (whole texels, writes
`Pan`, never `Origin`), **`brush poly rotate --by UU`** (unreal rotation units, exact `n̂ ×` path at
quarter turns, Rodrigues otherwise) and **`brush poly scale --by FU,FV`** (names the APPARENT size,
so it divides the stored magnitudes). Both transforms re-anchor on the face centroid — `rotate` by
`Origin' = C − R(C − Origin)`, `scale` by a 2×2 Gram solve, which is what keeps a SKEWED frame
correct under a non-uniform factor. All four per-face verbs now print `BRUSH:idx` selectors on
stdout instead of brush names (owner ruling: a bare name silently widens the set downstream).
Durable write-ups: `../architecture.md` "Surface edits" and `../rationale/surface.md`; the
user-facing half is in `docs/usage.md` and `docs/leveldesign/general/textures-and-surfaces.md`.
**Built in the `poly-surface-step1` worktree; the build gate ran its full two rounds, and both
found real defects.** Round 1: six findings plus two wording items and an extra pin — an
`OverflowError` traceback on an arbitrary-precision `rotate --by`; `scale` naming the frame
instead of the factor on an absurd factor; a degraded argparse message from a one-member mutex
group; a stale CLI spelling in a live spike comparison table; the two level-design doc indexes not
listing the new verbs; and step 1 missing from this file and misdescribed on `to-plan.md`.
Round 2: five findings, including a **data-corruption bug round 1's own fix had introduced** —
`scale --by` wrote a ZERO-LENGTH texture axis into the trunk at exit 0 with clean stdout, because
the writability guard restated `emit`'s floor as six decimal places when the real floor is
`emit.CLEAN_EPS = 1e-3` (`clean` snaps within `CLEAN_EPS` of an integer, and zero is an integer).
Three ordinary `--by 10,10` calls destroyed a unit axis; reachable on real content at `--by 667`
on the `0.6667` axes the editor-exported fixtures contain. Round 2 also found the same guard's
grow side leaking the band `[1e22, ~1.3e154]` (it asked `emit.clean`, which passes those, rather
than `emit.fmt_vertex`, which refuses them), and that BOTH of the tests round 1 added for that
guard passed for the wrong reason. The guard now asks the serializer itself and is pinned at the
emitted-text level. All findings from both rounds are fixed.
**THEN THE TURN DIRECTION CHANGED, after the gate had closed.** Step 1 was built on the residual
that `rotate` follows the *polygon* normal, which turns the texture the opposite way from what the
author sees on a subtractive brush; a concurrent session put that to the owner and **ruling
2026-07-27 reversed it — `n̂` is flipped on a subtract, so the verb turns against the VISIBLE
surface normal**. Implemented as given (`surface._visible_normal`), with the ruling's own
acceptance test pinned both ways; the docs were rewritten to describe the new behaviour, so nothing
still describes the shipped verb as polygon-normal. This change came AFTER the two-round gate and
therefore takes a fresh build round of its own.
**REMNANTS, all filed separately on `inbox.md` rather than covered by this entry:** (1)
`brush poly align` still prints touched brush NAMES while its four siblings print per-face
selectors — the same owner ruling covers it, but the align restructure is steps 2–5; (2) a
`CsgOper` that is neither `CSG_Add` nor `CSG_Subtract` (`CSG_Intersect`/`CSG_Deintersect`) has no
visible surface normal for the 2026-07-27 ruling to apply to, so `rotate` currently exits 2 naming
the value — the conservative interim, needing the owner's call; (3) a MIRRORED brush — scale
determinant negative, i.e. an ODD number of negative components — still inverts the turn; outside
the ruling, documented not corrected, and a geometric argument rather than a measured one.
**`scale --to`** (absolute world units per tile) is NOT built: it needs the texture catalog, and
it is part of step 5 on [`to-plan/`](../../to-plan/).

# `surface.py` — per-face texture edits

Why the surface-edit code is the way it is. Sibling of [`emit.md`](emit.md) and [`cli.md`](cli.md);
see [`README.md`](README.md) for the index. Revised in place — agents maintain this freely.

The owner's *product* decisions about these verbs live in `../direction/conventions.md` (once
confirmed) and are parked meanwhile on `../board/inbox.md`; this file holds only the engineering.

---

## The verb split: attributes vs the frame

`brush poly set` assigns **stored per-face fields** (texture, flags). `pan`, `rotate`, `scale` and
`align` transform the **texture frame**. They were one verb only because pan had nowhere else to
live, and mixing them made `set` a verb with two unrelated jobs.

**Why it is this way.** The frame verbs compose — an author aligns, then nudges, then turns — and a
verb per operation is what makes that pipeline expressible. `set` grew a `--pan-*` flag pair for
want of an alternative, which is exactly the "big verb grown a bespoke flag at a time" that
`../direction/conventions.md` "Verbs compose" rejects.

**Rejected.** *Keeping pan on `set`* — the `--pan-to`/`--pan-by` compound spelling exists only
because it shares a verb; alone it is `pan --to/--by`, matching every other transform in the CLI
(`brush scale --to/--by`, `mover key rotate --to/--by`).

**Refs.** `specs/2026-07-26-poly-surface-verbs.md` §2.1; `plans/2026-07-26-poly-surface-step1-plan.md`.

---

## The centroid re-anchor, and why `scale` needs a Gram solve

`rotate` and `scale` both leave the face's centroid `C` at the same `(U,V)`, so the texture turns or
grows *in place* rather than sliding off the face.

**`rotate`** — `Origin' = C − R(C − Origin)`, where `R` is the same operator applied to the axes.
Then `(C−O')·U' = R(C−O)·R(U) = (C−O)·U` identically. No linear solve, and no float dust beyond `R`
itself, which is what preserves quarter-turn exactness.

**`scale`** — a **2×2 Gram solve**, not the same shortcut:

```
u,v         = D·TU, D·TV                    with D = C − Origin
g11,g12,g22 = TU'·TU', TU'·TV', TV'·TV'     with TU' = TU/fu, TV' = TV/fv
det         = g11*g22 − g12*g12
a,b         = (u*g22 − v*g12)/det, (v*g11 − u*g12)/det
Origin'     = C − (a*TU' + b*TV')
```

**Why it is this way.** T3D does not require `TextureU ⊥ TextureV`, and the shortcut that works for
`rotate` does not transfer: `R` is an isometry so the Gram matrix is invariant under it, but scaling
is not. Scaling the covectors `TU,TV` by `1/fu,1/fv` requires scaling position by the **inverse
transpose** — along the reciprocal vectors, not along `Û`/`V̂`.

**Rejected.** *Scaling the direct-basis components* (`Origin' = C − (fu·a·Û + fv·b·V̂ + c·n̂)`). It is
correct for an orthogonal frame **or** a uniform factor, and silently wrong for the intersection of
skew and non-uniform scaling — the case the formula exists for. Measured counter-example: a 60°
skewed frame with `--by 2,1` and `D = Û` gives `D' = (2,0,0)`, moving the centroid's V from `0.5` to
`1.0`; the Gram solve returns `(2, −0.5774, 0)` and preserves both. Caught in plan review, not by a
test — which is why the skewed-frame non-uniform case is a required regression.

---

## `rotate`'s out-of-plane guard: `max(3e-3, 1e-2·|axis|)`

A face whose stored axes have a component along the normal is rejected: `n̂ × U` silently annihilates
that component, changing `|U|` and therefore the texel density.

**Why the threshold is absolute-OR-relative.** The two effects it sits between scale differently:

- **the noise is ABSOLUTE.** `emit.clean` snaps any coordinate within `CLEAN_EPS = 0.001` of an
  integer, and the texture axes pass through it. One component carries the magnitude and cannot be
  snapped, so the worst displacement is `√2·0.001 = 1.41e-3` — *independent of the axis magnitude*.
- **the harm is RELATIVE.** `n̂ × U` shortens the axis by `√(1−ε²)` for a relative out-of-plane
  component `ε`, costing `ε²/2` of density — `5e-5` at `ε = 1e-2`, invisible.

A purely relative gate therefore fails on short axes, which `brush poly scale --by` produces on
demand: after `--by 8,8` a unit axis is `0.125` long and the same absolute noise is **1.13e-2**
relative — over a `1e-2` gate. `scale --by 8,8` followed by `rotate` would exit 2 on a frame uedcli
itself wrote, one round trip earlier.

**Measured floor:** `max |axis·n̂|/|axis|` over 942 axes in `../../uedcli/tests/fixtures/**/*.t3d`
(normals via `preview._face_normal`) is **4.135e-07**, on `builder_revolve.t3d` poly 15; 876 of the
942 are exactly zero.

**Rejected.**
- *`1e-3` relative* (the spec's first assertion) — below the `2.1e-3` relative displacement the
  serializer can produce at `0.6667`, the smallest magnitude in the corpus, so it rejects uedcli's own
  output.
- *Deriving the threshold from the observed ceiling.* A threshold pinned to whatever the current
  corpus contains is only as tight as that corpus is clean; one clean corpus and the gate fires on the
  next map. Choose from the harm side and measure only to confirm the noise floor sits far below.

---

## `n̂` comes from the winding, floated first

The normal is computed from the polygon's own vertex winding via `preview._face_normal` (Newell),
normalised — never `poly.normal`.

**Why it is this way.** `../unrealed/t3d.md` "Winding defines the face": the importer ignores the
stored normal and the engine recomputes it, so an authored `(0.707,0.707,0)` re-exports as the true
`(0.541,0.541,0.643)`. `builders._face` marks its own write *advisory*.

Two traps, both measured:

- **Float the vertices first.** `Polygon.vertices` are `Decimal` triples and `_face_normal` seeds its
  accumulators at `0.0`, so passing them raw raises `TypeError`. `polyalign` avoids this only because
  `_world_verts` floats them on the way through.
- **Not a naive 3-vertex cross product.** On a face whose first three vertices are near-collinear it
  produces garbage: measured `1.09e-01` of false out-of-plane residue on `level_small.t3d`, where
  Newell reports exactly `0.0`.

---

## Refs

`specs/2026-07-26-poly-surface-verbs.md` · `plans/2026-07-26-poly-surface-step1-plan.md` ·
`spikes/2026-07-26-poly-rotate-curved-track/` (the curved-run measurements and `uv_preview.py`, which
renders each specified operation from the spec's rules) ·
`spikes/2026-07-26-unrealed-texalign-semantics/` (what the editor's own alignment does).

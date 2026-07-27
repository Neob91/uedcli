+++
priority = "p?"
kind = "unknown"
summary = "`level import` — native (editor-less) `.dx`/`.unr` → T3D ingestion — BUILT, with ONE remnant"
+++

# `level import` — native (editor-less) `.dx`/`.unr` → T3D ingestion — BUILT, with ONE remnant

(2026-07-27, was §8 on `to-build.md`; spec `dev/docs/specs/2026-07-24-level-import.md` v3, plan
`dev/docs/plans/2026-07-24-level-import.md`). `level import MAPFILE --tree level|stash/NAME
[--overwrite]` decodes a compiled map file into a new T3D tree with no editor, no container and no
game: the level's own `Actors` array gives the order, each actor's `StateFrame` is skipped and its
tagged properties rendered the way `MAP EXPORT` writes them (six-decimal floats, enum-named byte
struct members, struct members equal to the class default dropped), and a brush's private `UModel`
→ `UPolys` → `FPoly` chain becomes a real `PolyList`. Strict on ingest: an unresolvable class or
texture, a duplicate actor name, or an actor missing from the order array fails the whole import
naming it.
**Two defects the parked branch carried were fixed first**, each now with a regression test: a
face's `Item` label was read as unset at name-table index 0, silently deleting every
`Item=OUTSIDE` (7399 of 10690 polys in `02_NYC_Street.dx`); and `Model`/`Polys` bodies were entered
at their raw offset, desyncing on the ~1.5 % of retail ones whose export carries `RF_HasStack`.
**Owner ruling 2026-07-27:** import drops the editor's own scratch objects — the builder brush and
the `Camera` viewport actors — narrowing the spec's "all actors verbatim" to all *content* actors;
the drop must precede class qualification, since both key on the short class name.
Durable write-ups: `../architecture.md` "Native (editor-free) map IMPORT",
`dev/docs/rationale/mapimport.md`, `dev/docs/unrealed/package-format.md` (the two format traps); user-facing
docs in `docs/usage.md` "`level import`".
**REMNANT (`p1` on `inbox.md`): the load-bearing fidelity gate is unrun** — nothing has compared an
import against a UCC export of the same retail map, because the build machine had neither the
retail corpus nor the editor container. Slices 5.1/5.2 are what remains.

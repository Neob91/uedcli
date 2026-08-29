# Spec — `level reimport`

Owner-approved 2026-08-29 via brainstorming; canonical copy at
`docs/superpowers/specs/2026-08-29-level-reimport-design.md`. Mirrored here for the board runbook.

## Motivation

`level materialize` builds a `.dx`/`.unr` from trunk. Occasionally someone opens that map file
directly in UnrealEd — for something uedcli can't yet express (meshes, terrain, lighting tweaks,
whatever) — and saves it. There is currently no way to fold those changes back into the trunk that
produced it without destroying everything else in the trunk.

`level import` (`dev/docs/architecture.md` "Native (editor-free) map IMPORT") already decodes a
compiled map into the per-actor T3D a trunk holds, but only in **create mode**: it either creates a
new box, or (`--overwrite`) treats the ENTIRE existing trunk as deleted and rewrites every actor
fresh. That destroys per-actor identity for actors that didn't change — new `order_value` for
everything, folder/label sidecars lost, and a diff that touches every file in the level regardless of
how small the actual edit was.

## What we want

A new verb, **`level reimport MAPFILE --tree level/NAME`**, that reimports into an *existing* trunk
box, matching actors by name so unrelated actors are left untouched.

- **Decode is unchanged** — reuses `mapimport.import_map` as-is: same editor-scratch drop, same
  qualify-and-validate, same verbatim body decode `level import` already does.
- **The box must already exist** — the opposite of `level import`'s create-mode resolver. Exit 2,
  naming the box and pointing at `level import`, if it doesn't.
- **Actors are matched by name** against the trunk's current on-disk actor set (loaded via the
  ordinary `src.load()`):
  - **Matched** (name in both) — body replaced verbatim from the decode. This is the hand-edit.
    Folder/label sidecars are left untouched — the compiled format carries neither.
  - **Added** (map-only) — new actor dir. A point actor is appended-after-all, same as any new-actor
    write today. A brush is ranked per the order rule below.
  - **Deleted** (trunk-only) — passed as `deleted=` to `trunk.write_level`, the same mechanism
    `level import --overwrite` already uses for its whole-trunk case, scoped here to the real diff.
- **`order_value` recompute is brush-only.** Point actors don't participate in CSG, and
  `level materialize` already forces points-before-brushes regardless of `order_value`
  (`dev/docs/architecture.md` "The core write pattern"), so a point actor's `order_value` is never
  touched by reimport. For brushes: take the map's brush-only order as the target, find the longest
  run of matched brushes whose relative order is unchanged from the trunk's current order (longest
  increasing subsequence by current `order_value`) — those keep their existing `order_value` untouched
  (zero diff). Everything else (moved or new) gets freshly minted LexoRank values via the existing
  `order_ops.compute_reorder_ranks`/`compute_add_ranks` helpers, interpolated at its new position.
- **Write goes through the existing delta path unchanged** — `TrunkLevelSource.save` /
  `trunk.write_level`. This verb only has to construct the right in-memory `Level`, the right
  `deleted=` set, and the right order overrides before calling it. No new write primitive.
- **Round-trip fidelity is inherited, not new mechanism.** Matched/added bodies are written verbatim
  from the decode — the same renderer `level import` already uses — so a later `level materialize`
  clears the same fidelity bar `level import` already targets
  (`dev/docs/direction/trunk-and-editor.md`: "equivalence to `MAP EXPORT` through canonical lens, not
  byte-identity"). `reimport` inherits the existing, not-yet-closed gap noted in
  `dev/docs/rationale/mapimport.md` "What is not yet verified" — decode fidelity has never been
  checked against a real UCC export on retail maps. `reimport` doesn't need to close that gap; the
  guarantee is only as strong as it.

### The blast-radius guard

Reimporting the wrong file (or a map that has diverged far more than expected) should not silently
rewrite most of the trunk. The guard:

- **`--force` is required if** `(modified + deleted) / actors_in_old_trunk > 0.20`.
- **`modified`** = matched actors whose body differs from the old trunk, EXCLUDING actors where the
  only difference is `Location=`/`Rotation=` (ordinary repositioning shouldn't trip a wrong-file
  guard).
- **`deleted`** = old-trunk actors absent from the new map.
- **Pure additions don't enter the count at all** — neither numerator nor denominator (a reimport
  that's mostly new content isn't penalized for the adds).
- **Denominator is the OLD trunk's actor count** (`actors_in_old_trunk`), not the new map's — so
  adding a lot of new actors doesn't dilute the percentage and mask a real mass-edit.
- Without `--force`, exceeding the threshold is exit 2 naming the percentage and the counts.
- This replaces a narrower class-mismatch check considered earlier: a same-name class change (e.g.
  reclassing a mover) is a legitimate matched-actor edit and flows through as an ordinary body diff.
  A mass reclass across many actors trips the blast-radius guard on its own merit; one reclassed actor
  among hundreds doesn't, correctly.

### Testing

- **No-op case** (cheapest strong regression): `reimport(materialize(trunk))` applied back onto the
  SAME trunk with zero edits writes nothing at all.
- Moved-actor body update touches only that actor's file.
- Add/delete land in the delta-write's existing `deleted=`/new-dir paths.
- Brush reorder mints ranks only for the actually-reordered brushes; unchanged brushes' `order_value`
  files are byte-identical on disk.
- Point-actor reordering in the source map is a no-op on `order_value`.
- Blast-radius guard: a reimport under 20% modified+deleted succeeds without `--force`; over 20% exits
  2 and succeeds with `--force`; additions alone never trip it regardless of count.

## Rejected

- **A mode flag on `level import`** (e.g. `--merge`) instead of a new verb — a new verb better matches
  the CLI's small-single-purpose-verb convention (`dev/docs/direction/conventions.md`), and
  `level import`'s resolver semantics (create-mode) are opposite enough from `level reimport`'s
  (existing-box-required) that sharing one verb would mean branching behavior on a flag rather than
  the verb name.
- **Recomputing `order_value` for all actors, including points, from the map's actual order** —
  simpler, but noisier diffs: reordering point actors is rarely user-intentional (it's mostly an
  artifact of add/delete order in the editor) and carries no functional meaning, since materialize
  already forces points-before-brushes regardless.
- **A hard class-mismatch block** on a matched actor whose class changed — refuses a legitimate
  same-name reclass (e.g. changing a mover's class). Superseded by the blast-radius guard, which
  catches a mass reclass without blocking a targeted one.
- **A class-mismatch warning (non-blocking)** as a narrower substitute — considered between the hard
  block and the blast-radius guard; dropped once the blast-radius guard was proposed, since it
  subsumes the same wrong-file signal more generally (a mass reclass trips it; ordinary reclasses
  don't need a special-cased warning).

## Open follow-on (not in scope here)

- `rationale/mapimport.md` "What is not yet verified": `level import`'s decode has never been checked
  against a real UCC export of a retail map. `level reimport` shares this decode path and inherits the
  gap. Tracked separately on the board (`level-import-has-not-been-checked-against`).

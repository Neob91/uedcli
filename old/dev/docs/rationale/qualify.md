# Package qualification — why `qualify.py` recovers qualifiers the way it does

`MAP EXPORT`/`batchexport` strip the package qualifier from `Texture=` and `Class=` refs. `qualify.py`
reads it back off a live editor that has the matching level loaded. Textures and classes use two
different read-backs, for the reasons below.

## Classes qualify from `OBJ LIST CLASS`, never by `OBJ DEPENDENCIES` block order

**Why it is this way:** `qualify_level_classes` resolves a bare `Class=` name by running `OBJ LIST
CLASS=Class` — a flat dump of every loaded class as `Package.ClassName` — and building a bare-name →
package map (`parse_loaded_classes`). A bare name with exactly one loaded candidate qualifies; zero
or 2+ raise rather than guess. Textures use a different read-back (`OBJ DEPENDENCIES`, one block per
brush, matched to poly index), and the obvious move is to mirror it for classes — resolve each
actor's class from its per-actor `OBJ DEPENDENCIES` block. That is impossible: the per-actor block
order does not match `level.order`, so no positional scheme attributes a block to a specific actor.
There is no other per-actor class read-back, so a genuine two-package collision cannot be
auto-qualified at all.

**Rejected:** *Mirror the texture approach — positional match from `OBJ DEPENDENCIES`* — block order
≠ level order (disproven live). Raising on a genuine collision is the only safe contract.

**Refs:** `uedcli/qualify.py` (`qualify_level_classes`, `parse_loaded_classes`) ·
`spikes/2026-06-21-class-qualification-discovery-and-roundtrip.md` (Test 2: no read-back attributes an
instance to its colliding package) · `uedcli/tests/test_qualify.py`
(`test_qualify_level_classes_raises_on_a_genuine_collision`,
`..._raises_on_an_unresolvable_class`)

## Textures bind to `OBJ DEPENDENCIES` blocks by content, not position

**Why it is this way:** the `OBJ DEPENDENCIES PACKAGE=MyLevel` walk emits one `Engine.Polys` block
per authored brush PLUS one more — the level's own world BSP `Model`, an aggregate of every brush's
surviving surfaces (non-empty once any brush is textured). That aggregate block's position among the
non-empty blocks is not stable: live-probed 2026-07-14 it landed last for a 2-brush level, first for
the 95-brush castle, and in the middle for a World-shell level. So neither "drop the first block" nor
"drop the last" is safe, and the old rule (`#textured-brushes == #non-empty-blocks`, correlated
positionally) raised `N vs N+1` on every textured level and aborted materialize. `qualify_level_textures`
instead binds each brush to the first not-yet-claimed non-empty block whose ordered per-poly
object-names (`_bare`, the segment after the last `.`) equal the brush's own textured polys'
object-names; the aggregate is left unclaimed and dropped. It raises loudly if any brush finds no
matching block.

Content, not position-plus-a-count-guard, because the materialize post-verify cannot catch a
*deterministic* mis-bind — it re-qualifies both sides with this same function, so a mis-bind made
identically on both matches itself. The qualifier must be correct by construction.

One load-bearing limit: matching is by object-name, so two brushes carrying the same object-name from
different packages (`PkgA.Wall` vs `PkgB.Wall`) can't be told apart by content; that tie falls back to
block order, correct only because dump block order equals authored order. This is the one place
correctness rests on order — do not reorder surviving brush blocks when filtering.

**Rejected:**

- *Drop the trailing (or first) aggregate block* — its position is not stable (castle put it first).
- *Positional zip + a `<` count guard* — fails loud on multi-brush drift but silently mis-binds the
  single-brush case where the aggregate precedes the brush's own block, and leans on a post-verify
  that can't catch a deterministic mis-bind.
- *Identify the aggregate by its duplicate `Engine.Model` block* — drops both blocks for a single-brush
  level (the brush's `Polys` equals the `Model` too) → under-count; content matching handles it.
- *Treat semisolid as a materialize bug and rework `builders.py`* — semisolid emission is byte-correct
  (`PolyFlags=32`); the original one-shot failure was a transient editor wedge, not a code bug.

**Refs:** `uedcli/qualify.py` (`qualify_level_textures`, `_bare`) ·
`spikes/2026-07-13-semisolid-save/` (`probe_tree.py`, `probe_aggregate.py` — the aggregate-position
probes) · `spikes/2026-06-19-read-surface-texture-package.md` (block order equals authored order) ·
`uedcli/tests/test_qualify.py`
(`test_qualify_drops_the_world_model_aggregate_block_wherever_it_sits`,
`test_qualify_does_not_mis_bind_when_aggregate_precedes_a_lone_brush`,
`test_qualify_same_name_diff_package_relies_on_block_order_a_reorder_would_swap`)

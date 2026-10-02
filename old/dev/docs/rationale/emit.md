# T3D emit — why `emit.py` writes what it writes

Decisions about `uedcli/emit.py`, the module that turns the in-memory model
(`uedcli/model.py`) back into T3D text. It is a single choke point feeding four consumers:

1. the durable trunk on disk (`trunk.dump_actor_body` → `normalize.canonical_actor_t3d`),
2. the `MAP IMPORT` payload handed to UnrealEd at `level materialize`,
3. the compare view the post-verify checks the built map against
   (`normalize.compare_view` → `_geometry_text` → `emit_brush`), and
4. the identity hash that keys the photo build cache (`normalize.canonical_level_hash`).

A spelling emitted here appears on all four at once, including both sides of the post-verify
comparison.

## A zero polygon `Pan` is never emitted

A polygon's `Pan U=<u> V=<v>` line is the texture offset in the UV mapping
`U = (Vertex − Origin)·TextureU + PanU` (see [`../unrealed/t3d.md`](../unrealed/t3d.md) "The UV
convention"). The line is optional; a polygon with no `Pan` line has pan zero, so `Pan U=0 V=0` and
no line describe the identical surface. `emit_polygon` writes the line only when a component is
non-zero.

Why:

- UnrealEd's own exporter omits it. `MAP EXPORT` writes `Pan` only for a non-zero pan; no
  `Pan U=0 V=0` occurs in any real editor export in this repo. uedcli's job at materialize is to
  hand the editor the text it would itself have written, so a build round-trip is a no-op.
- The geometry half of the post-verify is a whole-text compare — `normalize._geometry_text`
  renders the brush with `emit_brush` and the two strings are compared outright, so a redundant line
  is a difference wherever it sits. It does not report as "a pan differs": the diagnostic
  (`verify._first_diff`) pairs the texts by line number, so one extra line shifts every following one
  and the message names a bogus vertex mismatch. This shipped as a bug: after `brush poly align`,
  which writes its seed's pan onto every target face, a freshly built brush (whose faces carry no
  `Pan`) gained `Pan U=0 V=0` on each aligned face, and the next `level materialize` aborted with
  `post-verify mismatch: … differs in GEOMETRY at line 43` and wrote nothing — the documented
  `brush poly find … | brush poly align …` → build workflow could not complete.
- The "never omit a property to mean zero" write-side rule
  ([`../unrealed/t3d.md`](../unrealed/t3d.md) "The corresponding WRITE-side rule") does not reach
  here. It exists because an omitted actor property re-imports as the class default, which is not
  always zero, and the write paths have no resolver to check. A polygon `Pan` is not an actor
  property: it is a field of the brush's `FPoly`, with no UnrealScript class and no class default
  behind it. Its only "default" is zero, so the two spellings are interchangeable on import. The
  same reasoning already governs `Flags` in the same function, omitted when zero since the beginning.
- Emit fixes every producer at once. Three write paths can land a poly on a zero pan —
  `polyalign._write_world_frame` (aligning to a seed with no pan, or `--fresh-frame`, which zeroes
  it), `surface.apply_pan` (`brush poly pan --to 0,0`, and `--by` arithmetic that cancels), and
  `clip.py`'s generated cap faces. Normalizing at the serialization boundary means a future write
  path cannot re-open the bug.

Rejected:

- Fix `polyalign` alone (don't write a zero pan there) — fixes the one reported repro but leaves
  `brush poly pan --to 0,0` and `brush clip` able to produce the same aborted build. The value align
  writes is correct; the defect is that one value had two spellings on the wire.
- Make the compare tolerant (drop a `(0,0)` pan in `normalize._geometry_text`, or normalize pan on
  both compare sides) — stops the abort, but leaves the durable trunk and the `MAP IMPORT` payload
  carrying a line UnrealEd will never write back. Every materialize → re-ingest round trip would
  churn the trunk in git for no semantic change, and the identity hash would keep two spellings of
  one level as two cache keys. It is also strictly weaker: with emit canonical, both compare sides
  are canonical for free, since the intended side reaches the compare through `emit_brush`.
- Make the model canonical — parse an absent `Pan` as `(0, 0)` and drop `Polygon.pan`'s `None`,
  mirroring `Polygon.flags: int = 0`. Defensible, but it changes the meaning of `pan is None` for
  every reader (`query.list_polys`'s `--json` and its `-` column, `preview_native`,
  `surface.apply_pan`'s `--by` base) to fix a defect that lives in the text form, which is where the
  two spellings collapse.
- Emit a zero `Pan` and teach the post-verify to align lines — a text-diff that resynchronizes
  after an inserted line would hide real geometry differences, the one thing the post-verify exists
  to catch.

Consequences a reader should expect:

- `brush poly pan --to 0,0` removes the surface's `Pan` line rather than writing a zero one, and
  `brush poly list` shows `-` (its spelling for "no pan") in the `pan` column. That is the same
  state the surface had before any pan was set — `0,0` is "no pan".
- An existing trunk holding `Pan U=0 V=0` is rewritten the next time anything saves that level, even
  for an unrelated edit. `TrunkLevelSource.save` writes an actor's body back whenever its emitted
  text differs from the file on disk, and such an actor now differs by exactly that line. So a user
  who edits one actor can see other actors appear in `git status` with only zero-`Pan` lines removed
  — a one-time migration to the canonical spelling, not a content change.
- A level holding a zero `Pan` gets a new identity hash, so its next photo rebuilds once.
  `canonical_level_hash` runs over this same emitted text and keys `preview_game.materialized_dx`'s
  build cache, so the cached `.dx` is no longer found under the new key. That is the harmless
  direction for the cache to err — a stale hit would serve a map built from different content; a
  miss only costs time — and the two spellings can never again produce two keys for one level.

**Refs:** `uedcli/emit.py` (`emit_polygon`) · `uedcli/tests/test_engine_facts.py`
(`test_editor_export_never_writes_an_all_zero_poly_pan` — the ENGINE fact this rests on, pinned
against the editor-exported goldens) · `uedcli/tests/test_emit.py`
(`test_a_zero_pan_emits_no_pan_line_at_all`) · `uedcli/tests/test_polyalign.py`
(`test_align_emits_no_zero_pan_so_materialize_can_verify_the_built_map`) ·
[`../unrealed/t3d.md`](../unrealed/t3d.md) "Polygon sub-fields reference" ·
[`../architecture.md`](../architecture.md) "The compare view vs the identity hash"

## `Location` lives in the typed field only, never mirrored into `props`

**Why it is this way:** an actor's `Location` is stored once — the typed `Actor.location` field, what
`move`/`rotate`/`translate`/bounds mutate. `model._parse_actor` keeps `Location` (and `Name`) out of
`actor.props`; `emit_actor` emits the line solely from `a.location` and skips any stray `Location`
props entry so a legacy one can never double-emit.

Field-canonical, not props-canonical, for two reasons. A props-canonical design (a `location`
property derived over `props`) needs a setter that formats `Decimal → (X=…)` with `emit`'s
formatter — but `emit` imports `model`, so `model` can't import `emit` (circular) — and it would
text-quantize `location` on every assignment. And it kills the whole field/`props` drift class:
`move`/`rotate`/`translate` already update only the field, so a props mirror is perpetually stale.

The bug this fixed: with `Location` dual-stored, `normalize_actor` nulled the field for an origin
actor, but `emit_actor` then fell through to the generic `{key}={val}` on the stale props string and
re-emitted the line the editor omits — a from-scratch materialize failed post-verify on origin actors
carrying `Location=(0,0,0)`.

**Rejected:**

- *Props-canonical, `actor.location` derived over `props`* — the setter needs `emit`'s formatter but
  `emit` imports `model` (circular); text-quantizes on every assignment; and doesn't preserve the
  source line position without extra in-place-replace logic.
- *Keep the dual-store, fix only `normalize_actor`* — treats the one symptom while leaving the
  field/`props` drift footgun live for every other write path. Removing the denormalization removes
  the whole class.

**Refs:** `uedcli/emit.py` (`emit_actor`) · `uedcli/model.py` (`_parse_actor`) ·
`uedcli/normalize.py` (`normalize_actor`) · `uedcli/tests/test_emit.py`
(`test_the_location_text_side_channel_is_never_emitted`) · `uedcli/tests/test_normalize.py`
(`test_normalize_actor_keeps_an_all_zero_location_in_the_trunk`,
`test_a_camera_authored_at_the_origin_keeps_its_location_in_the_durable_emit`)

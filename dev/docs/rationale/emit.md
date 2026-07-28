# T3D emit — why `emit.py` writes what it writes

Decisions about `uedcli/emit.py`, the module that turns the in-memory model
(`uedcli/model.py`) back into T3D text. It is a single choke point feeding four consumers:

1. the durable trunk on disk (`trunk.dump_actor_body` → `normalize.canonical_actor_t3d`),
2. the `MAP IMPORT` payload handed to UnrealEd at `level materialize`,
3. the compare view the post-verify checks the built map against
   (`normalize.compare_view` → `_geometry_text` → `emit_brush`), and
4. the identity hash that keys the preview build cache (`normalize.canonical_level_hash`).

A spelling emitted here appears on all four at once, including both sides of the post-verify
comparison.

## A zero polygon `Pan` is never emitted

A polygon's `Pan U=<u> V=<v>` line is the texture offset in the UV mapping
`U = (Vertex − Origin)·TextureU + PanU` (see [`../unrealed/t3d.md`](../unrealed/t3d.md) "The UV
convention"). The line is optional, and a polygon with no `Pan` line has pan zero — so
`Pan U=0 V=0` and no line at all describe the identical surface. `emit_polygon` writes the line only
when at least one component is non-zero.

Why:

- UnrealEd's own exporter omits it. `MAP EXPORT` writes `Pan` only for a non-zero pan; no
  `Pan U=0 V=0` occurs in any real editor export in this repo. uedcli's job at materialize is to
  hand the editor the text the editor would itself have written, so that a build round-trip is a
  no-op.
- The geometry half of the post-verify is a whole-text compare — `normalize._geometry_text`
  renders the brush with `emit_brush` and the two strings are compared outright, so a redundant line
  is a difference wherever it sits. It does not report as "a pan differs": the human
  diagnostic (`verify._first_diff`) pairs the two texts up by line number, so one extra line shifts
  every following one and the message names a bogus vertex mismatch. This shipped as a bug: after
  `brush poly align`, which writes its seed's pan onto every target face, a freshly built brush
  (whose faces carry no `Pan` at all) gained `Pan U=0 V=0` on each aligned face, and the next
  `level materialize` aborted with `post-verify mismatch: … differs in GEOMETRY at line 43` and wrote
  nothing — the whole documented `brush poly find … | brush poly align …` → build workflow could not
  complete.
- The "never omit a property to mean zero" write-side rule does not reach here. That rule
  ([`../unrealed/t3d.md`](../unrealed/t3d.md) "The corresponding WRITE-side rule") exists because an
  omitted actor property re-imports as the class default, which is not always zero, and the
  write paths have no resolver to check. A polygon `Pan` is not an actor property: it is a field of
  the brush's `FPoly`, with no UnrealScript class and therefore no class default behind it. Its only
  "default" is zero, unconditionally, so the two spellings are interchangeable on import and omitting
  one cannot mean anything else. The same reasoning already governs `Flags` in the same function,
  which has been omitted when zero since the beginning.
- Emit is where the fix covers every producer at once. Three write paths can land a poly on a
  zero pan — `polyalign._write_world_frame` (aligning to a seed with no pan, or `--fresh-frame`,
  which zeroes it by construction), `surface.apply_pan` (`brush poly pan --to 0,0`, and `--by`
  arithmetic that cancels), and `clip.py`'s generated cap faces. Normalizing at the
  serialization boundary means a future write path cannot re-open the bug.

Rejected:

- Fix `polyalign` alone (don't write a zero pan there) — it fixes the one reported repro and
  leaves `brush poly pan --to 0,0` and `brush clip` able to produce the same aborted build. The
  defect is not "align is wrong"; the value align writes is correct. The defect is that one value had
  two spellings on the wire.
- Make the compare tolerant instead (drop a `(0,0)` pan in `normalize._geometry_text`, or
  normalize pan on both compare sides) — it stops the abort, but leaves the durable trunk and the
  `MAP IMPORT` payload carrying a line UnrealEd will never write back. Every
  materialize → re-ingest round trip would then churn the trunk in git for no semantic change, and
  the identity hash would keep two spellings of one level as two cache keys. Fixing the compare is
  also strictly weaker: with emit canonical, both compare sides are canonical for free, because the
  intended side reaches the compare through `emit_brush`.
- Make the model canonical instead — parse an absent `Pan` as `(0, 0)` and drop
  `Polygon.pan`'s `None`, mirroring `Polygon.flags: int = 0`. Defensible, and arguably the tidiest
  model, but it changes the meaning of `pan is None` for every reader (`query.list_polys`'s `--json`
  and its `-` column, `preview_native`, `surface.apply_pan`'s `--by` base) to fix a defect that lives
  in the text form. The text form is where the two spellings exist, so that is where they collapse.
- Emit a zero `Pan` and teach the post-verify to align lines — a text-diff that can resynchronize
  after an inserted line would hide real geometry differences, which is the one thing the post-verify
  exists to catch.

Consequences a reader should expect:

- `brush poly pan --to 0,0` removes the surface's `Pan` line rather than writing a zero one, and
  `brush poly list` then shows `-` (its spelling for "no pan") in the `pan` column. That is the same
  state the surface had before any pan was set, which is correct — `0,0` is "no pan".
- An existing trunk that already holds `Pan U=0 V=0` is rewritten the next time anything saves that
  level, even for an unrelated edit. `TrunkLevelSource.save` writes an actor's body back whenever
  its emitted text differs from the file on disk, and the emitted text for such an actor now differs
  by exactly that line. So a user who edits one actor can see other actors appear in `git status`
  with only zero-`Pan` lines removed. That is a one-time migration to the canonical spelling, not a
  content change.
- A level holding a zero `Pan` gets a new identity hash, so its next preview rebuilds once.
  `canonical_level_hash` runs over this same emitted text and keys `preview_game.materialized_dx`'s
  build cache, so the cached `.dx` for such a level is no longer found under the new key. One extra
  build, once. That is the harmless direction for that cache to err (a stale hit would serve a map
  built from different content; a miss only costs time), and after this change the two spellings can
  never again produce two keys for one level.

**Refs:** `uedcli/emit.py` (`emit_polygon`) · `uedcli/tests/test_engine_facts.py`
(`test_editor_export_never_writes_an_all_zero_poly_pan` — the ENGINE fact this rests on, pinned
against the editor-exported goldens) · `uedcli/tests/test_emit.py`
(`test_a_zero_pan_emits_no_pan_line_at_all`) · `uedcli/tests/test_polyalign.py`
(`test_align_emits_no_zero_pan_so_materialize_can_verify_the_built_map`) ·
[`../unrealed/t3d.md`](../unrealed/t3d.md) "Polygon sub-fields reference" ·
[`../architecture.md`](../architecture.md) "The compare view vs the identity hash"

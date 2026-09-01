# Spec: batch of 5 lowest-effort board fixes

Source: top-20 lowest-effort ranking of the inbox/to-spec/to-plan/to-spike/someday board (450
actionable items scanned; board has no `effort` field, ranking was inferred). Two of the original
top-5 picks were dropped after reading their overview.md — they are not fix-now candidates:

- `grid-caption-major-8x-drawn-is-imprecise-once` — already resolved by editing the *spec text*
  (dropped the major field); no code to change.
- `umodel-parser-harness-pf-portal-constant-is` — explicitly deferred on purpose ("fix only if
  someone touches that file for another reason").

Replaced with the next two lowest-effort, verified-actionable items: `native-csg-golden-py-362-calls-ensure-editor`
and `a-doubly-signed-poly-index`.

## 1. `delete-the-ephemeral-spec-specs-2026-07-18`

**File:** `dev/docs/board/inbox/delete-the-ephemeral-spec-specs-2026-07-18/` (`spec.md` 37,594
bytes, `plan.md` 4,749 bytes).

**Fix:** delete both files. The unify-T3D-trees work they covered landed; the durable outcome is
already folded into `architecture.md`/`usage.md`/`direction/trunk-and-editor.md`. After deletion,
`git mv` the item itself to `done/` and trim its `overview.md` to a one-line reference, per the
board's own "when finished, trim to a short reference line" convention.

**Test:** none (doc-only).

## 2. `brush-clip-prints-nothing-on-success`

**File:** `uedcli/cli/commands/brush/edit.py`, `clip()` (~line 180-260).

Current behavior (verified — the item's "editing level banner" framing predates a since-landed
redesign of `brush clip` into a stateless T3D stdin→stdout filter, but the underlying gap is real):
a brush whose plane misses it entirely gets a stderr note (`plane did not intersect brush {name} —
emitted unchanged`, line 256); a brush that's actually clipped gets nothing but the T3D on stdout.

**Fix:** in the per-actor loop (~line 245-248), capture `before = len(actor.brush.polys)` prior to
`clip_brush`, and after a successful clip print to stderr, matching the existing "whole" line's
style and the verb-composition convention (`find`/README: "human summaries and counts go to
stderr"):

```
brush clip: clipped {actor.name}: {before}→{len(actor.brush.polys)} faces
```

**Test:** extend `uedcli/tests/test_brush_clip.py` (or `test_clip.py`) — assert the new stderr line
appears with the correct before/after counts on a plane that actually intersects a brush; assert it
does NOT appear for the "whole"/unchanged case (that keeps its existing message only).

## 3. `board-readme-md-still-says-every-issue-gets-a`

**File:** `dev/docs/board/README.md`, the `overview.md` section, "The stage is the path" bullet.

**Fix:** exact reword already given in the item — replace the "every issue gets a plan anyway"
justification with the real one:

> …are retired as tags: the path already says which stage an item is in. `kind` is what the path
> cannot say.

Both docs are agent-maintained; the item's overview.md notes no owner ruling is needed.

**Test:** none (doc-only). `test_board.py` doesn't check README prose.

## 4. `native-csg-golden-py-362-calls-ensure-editor`

**File:** `uedcli/native/csg_golden.py`, `regenerate()` (~line 350-403).

Confirmed by reading the code: `editor.ensure_editor` and `editor.stop_editor` both now require
`state_dir: Path` as a kwarg (`uedcli/editor.py:298,423`); `regenerate()` calls neither with one, so
every call currently raises `TypeError`. Additionally, `container = editor_mod.ensure_editor(editor_id)`
runs *before* the `try:` (line 364-365), so if `ensure_editor` raises after partially provisioning
(the wineprefix volume is created before `EditorNotReadyError` can fire, per `ensure_editor`'s own
docstring on the container/volume split), `stop_editor` in `finally` never runs and the volume
leaks. `stop_editor` tears down by deterministic container name (`editor_container(editor_id)`), so
calling it is safe even when `ensure_editor` only partially succeeded.

**Fix:**
- Resolve `state_dir` the same way `uedcli/apply.py` does: `config.resolve_project()` →
  `config.state_dir(project.root, create=True)`.
- Pass `state_dir=state_dir` to both the `ensure_editor` and `stop_editor` calls.
- Move `container = editor_mod.ensure_editor(...)` inside the `try:` block (or wrap it in its own
  try/finally) so `stop_editor` runs on any `ensure_editor` failure, not just failures inside the
  loop body.

**Test:** this is a harness-only script with no existing direct-call test (only `CORPUS`/
`_find_model_export` are imported elsewhere) — add a minimal regression: mock/stub `ensure_editor`
to raise `EditorNotReadyError` and assert `stop_editor` is still called once, with `state_dir`.

## 5. `a-doubly-signed-poly-index`

**File:** `uedcli/surface.py:83`, `resolve_polys()`.

Confirmed: `if not part.lstrip("-").isdigit():` strips *every* leading `-`, so `--3` (or `---3`,
etc.) passes the guard and reaches `int()`, raising a raw `ValueError: invalid literal for int()...`
that names neither the brush nor the verb — unlike every neighbouring failure mode (`+3`, `-3` out
of range, `x`), which all raise a `{brush_name!r}: ...` message via the existing `raise ValueError`
below it.

**Fix:** replace the double-strip guard with one that rejects a second sign, e.g.:

```python
if not re.fullmatch(r"-?\d+", part):
    raise ValueError(f"{brush_name!r}: bad poly index {part!r} (expected an integer)")
```

(needs `import re` at the top of `surface.py` if not already present — check first). This makes
`--3` fall into the existing `bad poly index` message instead of reaching `int()` unguarded.

**Test:** extend the existing poly-index test coverage (wherever `ROOM:-3`/`ROOM:+3`/`ROOM:x` cases
are tested for `resolve_polys` or `brush poly rotate`) — add `ROOM:--3` and assert it raises `bad
poly index '--3'` naming the brush, not a bare `ValueError` from `int()`.

## Out of scope

No shared code path between these five — each is a standalone, single-location fix. No new
abstractions, no flags, no tests beyond what's listed per item.

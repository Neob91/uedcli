# Open questions from the 2026-06-20 second-round review (`Opus 4.8` + `Sonnet`)

Two independent reviewers went over the full `uedcli-impl` diff (export_and_qualify,
the live OBJ DEPENDENCIES read, `apply`'s qualify-aware THEIRS, `poly set`). Two real bugs were
found and fixed (see `board/to-spec.md`'s "FIXED 2026-06-20 (second review round)" note — `run_apply`'s
exception handling around the qualify phase, and `dispatch.py`'s hardcoded
`("Engine", "Core")` missing `"Editor"`). The items below are things at least one reviewer
flagged that I'm deliberately leaving alone, either because they're an already-documented
tradeoff or because resolving them needs a live editor experiment I didn't think was in scope
for this review pass. Surfacing them here rather than guessing.

## 1. `level apply --check` now unconditionally tears down + recreates the session's live editor

`run_apply` calls `_theirs` (which calls `export_and_qualify` for THEIRS qualification) BEFORE
the `--check` early return. `export_and_qualify` always does `stop_editor` then a fresh
`ensure_editor` for its live OBJ DEPENDENCIES phase — by design, documented in
`architecture.md` ("always remove and recreate the per-session editor container... before MAP
LOAD") and in `qualify.export_and_qualify`'s own docstring, because a REUSED editor accumulates
stale texture bindings from whatever level it had loaded before. The editor is keyed purely by
session id (`editor.session_container`), and that's the SAME container `level preview` uses.

So: if a user has a `level preview` open in VNC for a session, and someone (or some agent) runs
`level apply --check` against that same session, the preview's editor gets killed and replaced
out from under them — `--check` is supposed to be the cheap, side-effect-free dry run, but it's
not side-effect-free against a concurrent preview. `board/to-spec.md`'s existing note on this only
mentions the COST ("`--check` now costs one extra editor spin-up"), not this specific
consequence.

I did NOT change this — the "always recreate, never reuse" rule is explicitly chosen and
explained (stale-texture-pool correctness > reuse convenience), and the obvious fix (only
recreate if NOT already the preview's container) would silently reintroduce the exact staleness
bug the architecture doc describes. A real fix likely needs either: (a) `--check` skipping the
qualify-aware THEIRS read entirely (i.e. accept a stale/bare-name comparison for `--check` only,
which may make `--check`'s plan disagree with the eventual real `apply`'s plan — defeating its
purpose), or (b) some way to snapshot+restore a `level preview`'s editor state across a `--check`
run, which is real new work. Flagging rather than picking one un-asked.

## 2. H3 post-verify's "empty Engine.Polys block = level's own BSP Model, always empty" claim is untested after a REBUILD

`qualify.qualify_level_textures` drops empty `Engine.Polys` dump blocks on both sides of its
brush↔block correlation, justified by the spike finding that the level's internal BSP `Model`
contributes one EMPTY block (confirmed live, but only for a freshly `MAP LOAD`ed level with no
rebuild in between). The H3 post-verify path (`apply._save_and_swap_verified` →
`verify_dx_matches(..., qualify_driver=driver)`) runs `OBJ DEPENDENCIES` on the SAME editor
AFTER `_materialize` has called `rebuild()` (a `MAP REBUILD`) and `MAP SAVE`. Whether the
rebuilt BSP Model's `Engine.Polys` block stays empty (because it has no poly-level Texture=
of its own — plausible, since BSP nodes reference the model's authored Polys, not duplicate
textured ones) or gains entries post-rebuild is a genuinely different, untested scenario — the
spike doc never drove a rebuild before reading OBJ DEPENDENCIES.

If it turns out NOT to stay empty, H3 post-verify would raise `qualify_level_textures`'s
count-mismatch `ValueError` on every successful apply (now caught cleanly as rc=2 per the fix
above, but still a false-positive verify failure, not a real merge bug). I did not attempt to
verify this live — it would need a real apply against the persistent `dx-lum-uned` container
(or a fresh ephemeral one) with a textured brush, which is a multi-step live experiment outside
this review's scope. If H3 starts spuriously failing on a real `level apply`, this is the first
place to look.

## 3. `qualify._segment_since_header`'s `rfind`-anchor-on-last-header assumption, if a single `OBJ DEPENDENCIES` walk ever emits its own header line twice

`_segment_since_header` anchors on the LAST `Dependencies of <package>:` line in the read text,
specifically to reject a STALE prior walk's already-flushed completion marker. This is correct
under the assumption that a single walk emits its header exactly once. If the walk's header
ever recurs mid-walk (not observed in the 5/5 live-confirmed rounds, and not something the spike
doc set out to check), `rfind` would anchor past the actual brush blocks and `_blocks_only`
would return a segment with them missing — `qualify_level_textures` would then see a
count-mismatch where there isn't really one. Pure speculation; the live evidence available
(5/5 rounds) doesn't show this happening, and I have no way to provoke it without another live
investigation. Not changing anything; just flagging in case a future flaky `qualify_live_level`
failure traces back here.

## 4. `packages.write_paths_and_reload`'s dedup check is a substring containment test, not a per-line exact match

`new = [f"Paths={p}" for p in paths if f"Paths={p}" not in existing]` checks whether the
candidate `Paths=<abs-path>` string appears ANYWHERE in the ini file's full text, not as its
own line. In practice this is very low risk (it would need another `Paths=` line whose value
is a literal superstring of the candidate path), but it's a fragile equality test for something
load-bearing — a false "already present" silently drops a needed entry, and a missing package
load fails much later and less legibly than at this check. Low-severity; didn't fix it because
the realistic false-positive rate looks close to zero and a "proper" fix (parse into lines, do
an exact per-line match) touches an integration-only, substrate-blocked function I have no way
to exercise live in this pass.

# Mover `NumKeys` is authoritative — the editor does NOT auto-decrement it when trailing keys are zero

**Date:** 2026-07-20
**Method:** live probe in an ephemeral `dx-lum-uned` editor (UED22 under wine), driven by
`harness/numkeys_probe.sh`. For each fixture: `MAP NEW` → `MAP GRID X=1 Y=1 Z=1` →
`MAP IMPORTADD` the mover T3D → `MAP EXPORT` (pre-rebuild) → `MAP REBUILD` → `MAP EXPORT`
(post-rebuild), batched into one `EXEC <file>` script, then the whole-level T3D read back and
the mover's `NumKeys`/`KeyPos` grepped. Fixtures (`harness/fixtures/`) are a uedcli-generated
128³ `Engine.Mover` cube with hand-set keyframe props, wrapped in `Begin Map…End Map` (bare
`Begin Actor` blocks do NOT import via `MAP IMPORTADD`).
**Confidence:** ✅ live-verified (every value below is a `MAP EXPORT` readback; editor stayed
alive through all three fixtures).

## The question

While speccing `mover key` (drop `add`; `move`/`rotate` create-or-edit a key by index, growing
`NumKeys`), Andrzej asked: **"if you set, say, key 5 to a location and then back to `0,0,0`, does
UnrealEd keep `NumKeys=6` or decrement it?"** — because if the editor auto-shrinks past trailing
all-zero keys, uedcli should mirror that; if it keeps them, uedcli must retain keys and reducing
`NumKeys` becomes an explicit verb.

## The finding

**`NumKeys` is preserved verbatim; there is no auto-decrement.** All three fixtures round-tripped
their authored `NumKeys=6` through `MAP IMPORTADD` *and* `MAP REBUILD`:

| Fixture | Authored | Readback (pre and post `REBUILD`) |
|---|---|---|
| `KeyPos(5)=(Z=256)` populated | `NumKeys=6`, `KeyPos(5)` | `NumKeys=6`, `KeyPos(5)=(Z=256.000000)` |
| **all movement keys zero** | `NumKeys=6`, no `KeyPos` | **`NumKeys=6`, no `KeyPos` line** |
| only `KeyPos(1)=(Z=64)` set | `NumKeys=6`, `KeyPos(1)` | `NumKeys=6`, `KeyPos(1)=(Z=64.000000)` |

Key observations:
- A key at the base pose stores **no** `KeyPos`/`KeyRot` line (zero offset is omitted), yet
  `NumKeys` still counts it. The editor uses `NumKeys` as the authoritative key count — it does
  **not** infer the count from which `KeyPos` lines are present, and does not truncate trailing
  zero keys. So a 6-key mover with every movement key at base stays a 6-key mover.
- `KeyPos` values round-trip exactly; `MAP REBUILD` changes neither `NumKeys` nor `KeyPos`
  (consistent with the 2026-06-25 mover spike: keyframe props are plain authored scalars/arrays).

## Scope / caveat

This tests the **materialize path uedcli actually uses** (`MAP IMPORTADD` + `MAP EXPORT`, and
`MAP REBUILD`). It does **not** test the interactive GUI keyframe workflow (set `KeyNum`, drag the
mover in a viewport). That distinction is moot for uedcli: the 2026-06-25 spike established that
the GUI keyframe path (`ACTOR KEYFRAME`/`BRUSH ADDMOVER`) is a derived-view recompute and a dead
end for authoring — uedcli authors keyframes entirely in T3D. So the materialize-path result is
the binding one.

## Design consequence (folds into `specs/2026-07-20-mover-key-base-relative-frame.md`)

uedcli **mirrors the editor: no auto-shrink.** `mover key move`/`rotate` set a key's offset and
only ever *grow* `NumKeys` (to `index+1`); zeroing a key leaves `NumKeys` unchanged. Reducing the
count is an explicit operation — `mover key remove <i>` (delete + compact) already does this; a
`clear` verb is an optional convenience, not required by any engine behavior. This matches the
current `movers.set_key_pos`/`set_key_rot` (they call `_ensure_numkeys`, which only grows) — pinned
by `test_movers.py::test_it_keeps_numkeys_when_a_key_is_zeroed`.

Reproduce: `bash harness/numkeys_probe.sh` (boots + tears down `uned-spike-numkeys`).

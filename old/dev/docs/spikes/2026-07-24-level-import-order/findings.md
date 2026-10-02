# Spike — `level import` authoritative actor ORDER (2026-07-24)

**Question (spec in board item `level-import-native-editor-less-dx-unr-t3d` §9; plan Slice 0 — gated BUILD):** when we decode
a compiled `.dx`/`.unr` for `level import`, in what ORDER do we emit actors? The order is load-bearing
twice — brush order = CSG precedence, and `normalize.canonical_level_hash` folds `level.order` into
the hash — so it must equal UnrealEd/UCC `batchexport`'s order or every acceptance compare fails.

Three sub-questions: **Q1** can we decode the actor list? **Q2** null/deleted slots? **Q3** does raw
export-table order already equal it (a shortcut that avoids decoding the list)?

## Finding

The `Engine.Level` object's body is `UObject` tagged properties (`None`-terminated — a real map's
Level carries **zero** tagged props) followed by the ULevel native tail, whose FIRST element is the
`Actors` array (`TTransArray<AActor*>`), serialized as:

```
[i32 Num][i32 Max]                         # raw INT32 — NOT a compact-index count; Num == Max on disk
Num × <compact-index object ref>           # signed FCompactIndex; ref 0 == a null/deleted slot
```

- **`Actors[0]` is always `LevelInfo0`** (the UE1 invariant — `ULevel::GetLevelInfo()` returns
  `(ALevelInfo*)Actors(0)`), `Actors[1]` the default/builder brush. Recovering this invariant is what
  proved the decode alignment (the initial mis-read below).
- Nulls are **interspersed and trailing**; drop them.
- After the array come URL, the Model ref, ReachSpecs, and the trailing block.

**This matches the native WRITE side already in the tree** — `uedcli/native/level_write.py`
`write_level_body` emits `struct.pack("<ii", Num, Max)` then `ci(ref)` per actor, docstring
"index 0 = LevelInfo, 1 = Default Brush". The spike independently CONFIRMS that layout by DECODING
three real retail maps.

### Answers
- **Q1 — decodable: YES.** Layout pinned above.
- **Q2 — nulls: YES.** 29–329 per map (below); interspersed + trailing; must be dropped.
- **Q3 — export-table-order shortcut: NO.** The Actors-array order differs from export-table
  (ascending-index) order on every map tested — so import MUST decode the Actors array for order; it
  cannot cheat with export-table order.

## Evidence (host-native, production `upackage`; `harness/order_probe.py`)

| map | Num=Max | nulls | non-null actors | `Actors[0]` | array==export-table order |
|-----|--------:|------:|----------------:|-------------|:-------------------------:|
| `00_Intro.dx`      | 2162 | 329 | 1833 | `LevelInfo0` | NO |
| `00_Training.dx`   | 1337 |  29 | 1308 | `LevelInfo0` | NO |
| `02_NYC_Street.dx` | 2198 | 134 | 2064 | `LevelInfo0` | NO |

All three: `Num==Max`, 0 bad import-refs, all non-null refs distinct, sane byte remainder for the
tail. **Initial mis-read (recorded so it isn't repeated):** reading the `Num` field as a *compact
index* decoded `0x0872` as `562` and desynced the array (nulls-first, `Actors[0]`=a Brush) — the
`72 08 00 00 72 08 00 00` doubled-INT32 pattern is the tell that it's `Num;Max`, not a compact count.

## `array order == batchexport order`?

Treated as **near-definitional and scheduled, not an open unknown**: UnrealEd's `UExporter` for a
Level iterates `Level->Actors` in order, skipping NULL entries — it cannot emit any other order. The
LevelInfo-first convention this predicts is confirmed by the committed UCC goldens
(`dev/docs/spikes/levelinfo_update/ucc_export_after_save.t3d`, `uedcli/tests/fixtures/level_small.t3d`
both list `LevelInfo0` first). A direct `batchexport` of a retail map was attempted but needs the
map's package deps staged (`Can't find file for package 'CoreTexMetal'`) — that full-package
`export_dx_level` path is exactly plan **Slice 5**'s integration golden, where the end-to-end
`native-order == batchexport-order` is confirmed on the corpus. Not re-litigated here.

## Decision folded into the spec (§5.1)
Import decodes the `Engine.Level` Actors array (layout above), **drops null slots**, and emits actors
in that order (LevelInfo first). No export-table-order shortcut. The build is unblocked.

## Regression
`uedcli/tests/test_engine_facts.py::test_level_actors_array_is_int_num_max_then_compact_refs` pins the
layout via a round-trip against the encode mirror `native.level_write.write_level_body` (offline, no
committed binary — game maps are gitignored copyrighted assets).

# Spike — does `MAP IMPORT` give a brush the bounds CSG needs? (No.)

**Date:** 2026-07-26, live against a fresh ephemeral `dx-lum-uned` editor.
**Question (owner):** the materialize drive introduces brushes by loading the host clipboard and
issuing `EDIT PASTE`. Could it use `MAP IMPORT` instead — a plain file-based console command?
**Answer: NO. `MAP IMPORT` drops the brush's bounds exactly like `MAP IMPORTADD` does, so CSG skips
the brush and the built map has ZERO BSP nodes.** `EDIT PASTE` remains the only add path that
produces a game-loadable map.

Harness: [`harness/probe.py`](harness/probe.py) (re-runs all three rounds against a fresh editor),
[`harness/bspnodes.py`](harness/bspnodes.py) (the offline measuring instrument).
Regression: `uedcli/tests/test_engine_facts.py::test_only_edit_paste_gets_a_brush_into_csg`,
pinned against the three real `.dx` files this probe produced
(`uedcli/tests/fixtures/map_import_bounds/`).

## Why it was worth asking rather than inferring

`dev/docs/unrealed/quirks.md` "How brushes enter the level" already records that a brush entering
via **`MAP IMPORTADD`** never gets its `Bound` computed — `ULevelFactory` does not compute it and
`MAP REBUILD` does not compute it later — so CSG skips the brush entirely and the level stays solid.
Proven live 2026-06-28, including the downstream consequence: such a map loads in the real game and
then dies at `MatchViewportsToActors → "Failed to spawn player actor"`, because a solid world leaves
nowhere to spawn.

Every one of those probes used `IMPORTADD`, the **add-to-current-level** form. Nobody had driven
`MAP IMPORT`, the **replace-the-whole-level** form. The two are believed to share `ULevelFactory`,
so the expectation was "same defect" — but that was an inference, and the answer changed a design:

- a working `MAP IMPORT` would make the whole materialize drive file-based, with no host clipboard
  round-trip in the middle of an otherwise batchable console script;
- it would delete the `+32uu` paste-drift compensation (`writes.PASTE_DRIFT`), a correction that has
  already misled one spec into misplacing brushes by 32 uu on a non-paste path;
- it would remove the constraint that forces all point actors to be introduced before all brushes,
  which is the only reason `materialize.levelinfo_first_order` exists.

Three real benefits, resting on an assumption nobody had tested. Hence the probe.

## Method

One editor container, three rounds over the **same** two-brush fixture — a subtractive 1024×1024×512
room with an additive 128×128×512 pillar inside it (untextured, so no content package is mounted and
the probe cannot fail for an unrelated missing-asset reason). Each round starts from `MAP NEW`,
introduces the actors by exactly one verb, then rebuilds, saves and exports:

| Round | How the brushes enter | Role |
|-------------|------------------------------|---
| `paste`     | `EDIT PASTE`                 | the production path — the positive control
| `importadd` | `MAP IMPORTADD FILE=`        | the 2026-06-28 known-bad negative control
| `import`    | `MAP IMPORT FILE=`           | the question

Each round is driven as ONE `EXEC <file>` console script (`dev/docs/unrealed/commands.md`
"`EXEC <file>`"), whose last line is a `MAP EXPORT` that doubles as the completion marker the host
polls for — driving is fire-and-forget, so a marker is the only honest completion signal, and a
script rides through the GC "Cleaning up…" dialog that stalls the same commands typed one at a time.

The verdict is read **offline** from the saved `.dx`: the number of nodes in the built world model
(`uedcli.native.umodel.parse_model_body`). Zero nodes means CSG never saw the brush. That is the
only check that can tell the failure apart from success, because a skipped brush still saves, still
parses, and still draws its wireframe in the editor. The instrument was validated first against
retail maps (`00_Intro.dx` → 7810 nodes, `01_NYC_UNATCOHQ.dx` → 5174) and cross-checked against the
independent `spikes/bspspike/umodel_parser` on the probe's own output — identical counts.

## Results (live 2026-07-26)

| Round | BSP nodes | BSP surfs | saved `.dx` | actors in the re-export |
|-------------|-----------|-----------|-------------|---
| `paste`     | **16**    | 10        | 7952 B      | `Brush1`, `LevelInfo0`, `ProbePillar`, `ProbeRoom`
| `importadd` | **0**     | 0         | 3547 B      | `LevelInfo0`, `ProbePillar`, `ProbeRoom`
| `import`    | **0**     | 0         | 3525 B      | `LevelInfo0`, `ProbePillar`, `ProbeRoom`

Three things this shows, in order of importance:

1. **`MAP IMPORT` has the same defect as `MAP IMPORTADD`.** Zero nodes, zero surfaces. The
   replace-the-level form is no better than the add form; the shared `ULevelFactory` inference was
   right.
2. **The failure is silent, and the probe proves it is silent.** Both brushes are *present* in the
   re-export of the failed rounds — `ProbeRoom` and `ProbePillar` are right there with their
   geometry. Nothing about the actor list, the save, or the parse says anything is wrong. Only the
   node count does. The ~4.4 KB size gap between `paste.dx` and the other two is the absent BSP.
3. **Names survive every path.** All three rounds preserve `ProbeRoom`/`ProbePillar` verbatim. So
   name preservation is *not* what rules the import verbs out — it is purely the missing bounds.
   (This matters because the obvious third candidate, `BRUSH IMPORT` + `BRUSH ADD`, *does* run the
   real CSG path but renames brushes to `Brush1…BrushN`, which uedcli's name-keyed model cannot
   accept. So there is no import-shaped escape route: one path computes bounds but destroys names,
   the others keep names but skip CSG.)

## Consequences

- **`EDIT PASTE` stays**, and `writes._re_add`'s split — point actors by `MAP IMPORTADD`, brushes by
  `EDIT PASTE` — is confirmed as the only working arrangement, not merely the incumbent one.
- **`PASTE_DRIFT` and `levelinfo_first_order` stay too.** They are the price of the only path that
  works, not incidental complexity to be cleaned up.
- **Batching the drive is unaffected.** The clipboard is loaded HOST-side (a `docker exec` running
  xclip) and only then does a console `EDIT PASTE` consume it — so the clipboard is already in place
  before a batched `EXEC` script starts, and `EDIT PASTE` sits inside such a script quite happily.
  This probe's own rounds are the demonstration: every one of them pasted from inside an `EXEC`
  script. **A clipboard-based add path is not an obstacle to batching the build.**

## What is NOT established here

- **Why** `ULevelFactory` skips the bound computation, and whether some flag or a subsequent verb
  could make it compute one. The probe measures the outcome of the two shipped import verbs as they
  are; it did not disassemble the factory or try to provoke a recompute.
- Whether any **later** command can retro-fit a bound onto an already-imported brush. `MAP REBUILD`
  demonstrably does not (that is the 2026-06-28 finding, re-confirmed here). `ACTOR APPLYTRANSFORM`
  is documented to work on `IMPORTADD` brushes and touches geometry, so it is the one plausible
  candidate — untested, and out of scope, because the production path already works.

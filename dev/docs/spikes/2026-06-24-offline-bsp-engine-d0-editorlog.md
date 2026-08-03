# D0 built + validated: editor drop-warning capture (the cheap, complete-on-real-build hole detector half)

**Date:** 2026-06-24
**Implements:** the D0 half of board item `bsp-issue-detector` / board item `bsp-issue-ground-truth-detector-d0-d1` §6 (D0).
**Code (spike-grade, `_scratch/bspspike/`):** `bsp_editorlog.py` (parser + live capture), `d0_live.py` (live validation).
**Result:** ✅ D0's parser works on all channels (offline, deterministic) and **caught a real
injected hole live**, cleanly distinguishing it from a good build.

---

## What D0 is

D0 reads the editor's own `MAP REBUILD` log — the editor *confesses* every face it drops and every
defect it finds. `bsp_editorlog.parse_build_log(text) -> BuildLog` parses these channels:

| Channel (Editor.dll wide string) | Meaning |
|---|---|
| `FPoly::CalcNormal: Zero-area polygon` | a dropped face (zero area) |
| `FPoly::Finalize: Not enough vertices (%i)` | a dropped face (<3 verts after cleanup) |
| `BspValidateBrush linked %i of %i polys` | linked<total ⇒ not watertight (leak/hole) |
| `bspAddNode: Infinitesimal polygon %i (%i)` | a phantom/sliver node (invisible-wall candidate) |
| `Processed %i T-points, linked: %i/%i sides` | total−linked ⇒ unlinked T-junctions (HoM crack) |
| `Nodes: %i -> %i` / `Portalized: … %i leaves, %i nodes` | final structure (sanity) |

`BuildLog` exposes `has_drops`, `has_holes_or_hom`, and `findings()` (human-readable). `BuildLog`
is a frozen kw-only dataclass.

## Validation

**Offline (deterministic, the load-bearing logic):** `parse_build_log` on a synthetic log
exercising every channel returns the exact expected counts — and correctly does **not** flag a
clean `BspValidateBrush linked 6 of 6` (only `linked<total`). A clean-build sample yields zero
findings, `final_nodes=6`, `leaves=1`.

**Live (`d0_live.py`, one fresh ephemeral editor, torn down in `finally`):**

| Case | nodes | leaves | D0 verdict |
|---|---|---|---|
| clean subtract box | 6 | 1 | **no holes/HoM** ✅ |
| open box (one face removed) | 5 | 1 | **flagged: "4 unlinked T-junction side(s) (HoM crack)"** ✅ |

The open box (a deliberately non-watertight brush — `writes.add_actor` accepts it; `validate_brush`
checks per-poly validity, not watertightness) produced **4 unlinked T-junction sides** in the
rebuild log: removing a face left four edges the editor's `bspOptGeom` could not link → exactly the
HoM-crack signal D0 is meant to surface. (The `BspValidateBrush linked X<Y` line is
higher-verbosity and didn't flush this run; the T-points channel caught the same defect — D0 reads
multiple channels precisely so one not flushing doesn't blind it.) **D0 distinguished broken from
clean geometry live.**

## What this establishes / where it sits

- D0's mechanism is proven: the editor's log is a real, parseable ground-truth channel for dropped
  faces / leaks / HoM cracks / phantom nodes, on a live build, with no port.
- D0 is the **dropped-face/absence + existence half** of the complete detector; **D1** (parse the
  saved built model) is the **located-issue half** (HoM/T-junction/invisible-wall/fall-through
  *locations*). Together = complete on the real build (board item `bsp-issue-detector`, spec §1 table).

## Next

1. **D0-b — the measurement (gates whether D2 is ever built):** run D0 over the repo's **real
   DeusEx maps** and count how many drops/HoM are build-emergent vs single-brush (cross-ref the
   shipped static `doctor`); the residual "silent-absence" frequency decides D2. *Needs the
   gitignored DeusEx install content present (real maps).* 
2. **Promote** `bsp_editorlog.py` → `uedcli/bsp/editorlog.py` with offline golden tests (the
   synthetic-log parser cases) + an integration-gated live test, and wire a `level doctor` verb
   (author-time/CI report). Per discipline, promote after D0-b runs on a real map.
3. **D1 — P0-a feasibility:** can a saved `.dx`'s built `Model` (`Nodes`/`Surfs`/`Vectors`/`Points`/
   `Leaves`/`Zones`) be parsed (new binary RE; version-61 wrinkle)? That unlocks the located-issue
   half.

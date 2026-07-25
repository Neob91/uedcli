# 90 — Castle re-baseline: is the 58% headline measured against a FAIR golden? — YES ✅

**Status:** grounding measurement, landed. **Date:** 2026-07-19.
**Scope:** re-ground the castle native-parity headline (the long-tracked ~58%) on the CORRECT basis
established in §89 — UnrealEd's OWN batch build of the SAME trunk — instead of the shipped
`DX/Maps/Test_Castle.dx`, and decide whether the number changes.
**Harness:** `harness/build_ued_golden.py` (golden builder), `harness/ground_truth_bytediff.py`
(raw byte diff), `harness/persec_bytematch.py` (the "compiled %" — per-section aligned positional
match), `harness/bsp_health_check.py` (structural validity), `harness/build_native_castle.py`
(native build).

### Confidence legend
✅ live-verified this session against real editor builds and the real shipped `.dx`.

---

## 1. Why re-measure ✅

§89 proved the parity basis had been unfair for UNATCO: the shipped `03_NYC_UNATCOHQ.dx` is
hand-authored / incrementally CSG-built, so a clean UnrealEd BATCH rebuild of the same trunk differs
from it by **+21.7 % nodes / −66 % leaves** — build-procedure, not native drift. The castle's
headline (~58 %) was likewise measured against the shipped `Test_Castle.dx`. **Open question:** is
`Test_Castle.dx` itself a clean batch build (so the 58 % is already fair), or is it authored/
incremental like UNATCO (so the real native number differs once re-based)?

## 2. What "58 %" actually is (the metric) ✅

Three different roll-ups of the same Model-body byte diff, do not conflate them:
- **Raw whole-body positional** (`ground_truth_bytediff.py`): **43.0 %**. Collapses at the first
  section whose LENGTH differs (everything downstream byte-shifts), so it under-reports.
- **Fully-byte-identical sections** (`ground_truth_bytediff.py` final line): **0.01 %**. Harsh
  all-or-nothing floor — a single differing byte voids a whole section.
- **Per-section ALIGNED positional, length-weighted** (`persec_bytematch.py`): **58.1 %**. Each
  section is walked independently so a length diff in one does not desync the next; this is the
  **"compiled parity %"** the castle work has tracked. **The 58 % headline = this metric.**

## 3. The golden is deterministic ✅

`build_ued_golden.py` on the castle trunk (`_scratch/castle/uedctl/maps/foobar` — 161 actors: 95
`Brush`, 62 `Light`, 1 `ZoneInfo`, 1 `SkyZoneInfo`, 1 `PlayerStart`, 1 `LevelInfo` — **all engine
classes, so NO `DeusEx.u` stub needed and no world-only/mover contamination risk**) run **twice**:
both `.dx` are **448 858 bytes**; their Model bodies are **100.00 % byte-identical** (all 17 sections
`YES`). The only full-file delta is 270 bytes at header offsets ~37-46 = the package GUID + save
timestamps. So the golden is a reproducible fixed point. Build settings: **full trunk + lit**
(NOT `--world-only`, NOT `--no-light`) — the castle native build is lit, and every castle actor is an
engine class the editor resolves, so the apples-to-apples golden keeps the 62 lights + zones. (§89's
`--world-only --no-light` canonical basis is for OG trunks with unresolved `DeusEx.u` movers/lights;
the castle has neither problem.) Each editor phase idles in ~19-22 s under the CPU barrier; whole
build ~2 min, no wedge, no crash — the earlier "it's taking minutes" worry was just the sum of the
per-phase quiet-window barriers, not a hang.

## 4. The three diffs (RAW bytes) ✅

Native = `build_native_castle.py` (lit). Golden = `UEDGolden_castle_r1.dx` (UnrealEd batch, full,
lit). Shipped = `DX/Maps/Test_Castle.dx`.

| metric | (a) native vs GOLDEN [NEW] | (b) native vs SHIPPED [OLD] | (c) GOLDEN vs SHIPPED [build-proc] |
|---|---:|---:|---:|
| Model body bytes | 245234 vs 249287 | 245234 vs 249287 | 249287 vs **249287** (Δ0) |
| compiled % (per-sec aligned) | **58.08 %** | **58.07 %** | ~99.9 % |
| raw whole-body positional | 43.04 % | 43.04 % | **99.89 %** |
| fully-identical sections | 0.01 % | 0.01 % | **70.17 %** |

**(a) ≡ (b): the NEW basis gives the SAME number as the OLD one** — 58.08 % vs 58.07 %, a 7-byte
difference. Re-basing the castle onto its self-built golden does **not** move the headline.

**(c) is the point.** UnrealEd's batch golden and the shipped `Test_Castle.dx` have an **identical-
size Model body** and are **byte-identical in EVERY section except three** — `Nodes`, `Surfs`,
`Lights(e4)` — and those three differ only in embedded OBJECT-REFERENCE bytes (surf `iActor`/texture
import indices, node/light refs), i.e. pure export/import renumbering, NOT geometry. `bsp_health_check`
confirms golden, native, and shipped ALL carry the identical topology: **nodes 1156, leaves 384,
surfs 485, verts 16163, zones 4**, same 691/1156 DFS reachability. Contrast UNATCO (§89 §4), where
golden-vs-shipped diverged +21.7 % nodes / −66 % leaves / +15.9 % bounds.

## 5. Verdict ✅

**`Test_Castle.dx` IS effectively a clean batch UnrealEd build of its trunk.** Golden-vs-shipped is
99.89 % positional with an identical body size and identical BSP topology, differing only by object-
table renumbering in the three ref-bearing sections. Unlike UNATCO, the castle carries **no
incremental-authoring inflation**, so the castle metric was ALWAYS measured against a fair golden.

**The corrected castle parity number vs the self-built golden = 58.08 %, unchanged from the 58.07 %
vs shipped.** The ~58 % headline **stands as-is** — none of it was hidden build-procedure, and the
sharpest native target is unchanged: the native gap is real geometry/encoding drift (`Surfs` 21 %,
`Verts` 27 %, `Lights` 1.6 %, `Leaves`/`LightBits` ~45 %), not a golden artifact. Why the castle
differs from UNATCO: the LUM test castle was purpose-built as the parity target by a single batch
`MAP REBUILD`, whereas the shipped OG UNATCO map accreted over a long hand-authoring history.

**Key finding for the corpus:** the §89 rebaseline lesson (chase the batch golden, not the shipped
map) is what MADE UNATCO fairer; for the castle it CONFIRMS the existing number rather than changing
it. When picking parity targets, a shipped map's fairness depends entirely on whether it was batch-
or incrementally-built — verify per level with a golden-vs-shipped diff before trusting it.

## 6. Reproduce
```
cd Tools/uedctl
# native (lit) from the castle trunk
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/build_native_castle.py \
  _scratch/gtruth/NativeCastle.dx
# UnrealEd golden (FULL + LIT) from the SAME trunk — BOUNDED BACKGROUND JOB (editor wedges silently)
.venv/bin/python -u dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py \
  --trunk _scratch/castle/uedctl/maps/foobar \
  --out _scratch/uedgolden/UEDGolden_castle_r1.dx --overwrite            # no --world-only, no --no-light
# the three diffs + the compiled %
D=dev/docs/spikes/2026-07-15-native-materialize/harness
.venv/bin/python $D/ground_truth_bytediff.py _scratch/gtruth/NativeCastle.dx _scratch/uedgolden/UEDGolden_castle_r1.dx
.venv/bin/python $D/ground_truth_bytediff.py _scratch/uedgolden/UEDGolden_castle_r1.dx /home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx
.venv/bin/python $D/persec_bytematch.py     # native-vs-golden + native-vs-shipped compiled %
.venv/bin/python $D/bsp_health_check.py _scratch/uedgolden/UEDGolden_castle_r1.dx _scratch/gtruth/NativeCastle.dx /home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx
```
Outputs live under gitignored `_scratch/uedgolden/` + `_scratch/gtruth/` (editor-built maps never
enter the tree).

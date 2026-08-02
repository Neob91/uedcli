# Native ↔ UnrealEd byte-parity — session status / resume handoff

*Checkpoint 2026-07-20. Read this FIRST on resume, then the cited `sections/92-*.md` entries for detail.
This file is the durable resume pointer; the blow-by-blow lives in `sections/92-bspbrushcsg-reallevel-port-plan.md`
(§11–§54) and the ledger map in `rationale/MIGRATION.md`.*

---

## Goal (unchanged)
`native level materialize` output **byte-for-byte identical to UnrealEd's OWN build of the same trunk**
(you must EXPORT the trunk and run UnrealEd yourself to make the golden — NOT the hand-authored shipped
`.dx`), on **all original Deus Ex levels**, ignoring GUIDs, timestamps, the red builder brush, and other
non-deterministic editor-session artifacts ("and similar"). Two reference levels drive the work:
- **castle** (`Test_Castle`) — small, no rotated/scaled/portal/detail brushes; the **castle-safety gate**:
  every fix MUST keep the castle Model body byte-identical (only the 16 GUID bytes may differ).
- **UNATCO** (`02_NYC_UNATCOHQ`) — large, exercises rotation/scale/portals/semisolids; the hard target.

---

## HEADLINE STATE (checkpoint `e0a566f10`, branch `uedcli-impl`)

- **NINE real byte-parity fixes landed + pushed** (§11 dome-cap, §33 convex-seed, §34 texture-covector,
  §42 GMath trig, §43/44 scaled-normal, §45 vertex-PointXform+pBase, §48 per-face-normal-CSG-op, §52
  second-SafeNormalSlow, §54 portal-pass-staging) + NormalizeSlow + SplitInHalf faithfulness. All
  castle-byte-identical, all 2-cold-reviewed.
- **CASTLE: Model body BYTE-IDENTICAL** (the castle is at parity, GUID aside).
- **UNATCO: NOT at parity yet.** Whole-map compiled byte-% ≈ **18.9–19.1%** (flat across the recent arc —
  see the reframe below for why). Committed (pre-repartition) incremental tree is byte-identical through
  a **prefix of 1764 nodes** (was 1637 before §54); normals are now editor-correct (twins 86→2).

## THE PIVOTAL REFRAME (§53 — read this before touching anything)
The long **normal-twin campaign (§42–§52) is PARITY-IRRELEVANT for UNATCO's whole-map byte-%.** It was
real, correct engineering (the UNATCO node-plane *normals* are now editor-faithful, castle stayed
byte-identical), but:
- Closing the normal twins 86→2 moved the whole-map byte-% by ~0 and the repartition emit-order (node-56)
  by **zero** — the 2 residual sub-ULP twins round to *shared* node-plane keys, contributing nothing.
- §45's "topology byte-identical 1637/1637, parity in reach" was an **N=105-limited illusion**: the
  committed tree IS byte-identical through N=105, then diverges **structurally** for brushes past 105.

**The actual UNATCO gap is a STRUCTURAL BSP divergence, not normals or precision.** Do NOT re-chase the
normal/precision family — it is closed and a dead end for UNATCO whole-map parity.

---

## THE TWO OPEN FRONTS (the path to UNATCO parity)

### Front 1 — committed-tree PASS-STAGING (tractable; keeps landing correct prerequisite fixes)
UnrealEd builds the world in two passes: **pass-1 STRUCTURAL** brushes (incremental CSG → then a
`bsp_build` REPARTITION), then **pass-2 SEMISOLID/NONSOLID detail** brushes (incremental, NOT
repartitioned). Native was mis-routing some brushes between passes:
- **§54 (LANDED): PORTAL brushes belong in pass-1** (structural, entering the repartition soup as a
  non-CSG splitter), not pass-2. Native deferred them → the committed tree dropped the portal the editor
  keeps. Fixed at `bspcsg.rs::build_geometry_bspcsg` (`detail_pass = pf&0x28 && !PF_Portal`). This
  extended the byte-identical committed prefix **1637→1764** and reproduced **+84** editor node-planes
  (shared 5669→5753, only-editor 645→561), castle byte-identical, regression added.
- **RESUME HERE:** the next committed-tree divergence is **node 1764, born in brushes (106, 159]**
  (native `(0,0,1)@30` vs editor `(0,1,0)@-834`). Bisect (106,159] to the first diverging brush. Prime
  suspects: the 2nd portal `Brush362` (idx 107 — should already be fixed by §54; verify) or the first
  **SEMISOLID `Brush416`** (idx 111). **Key open question if it's a semisolid:** does UnrealEd also
  process SEMISOLIDS structurally (pass-1, pre-repartition)? If yes, native's pass-2 deferral is wrong
  for semisolids too (a broader, higher-risk pass-staging change — gate carefully). Tooling is ready:
  `harness/editor-tree-oracle/editor_struct_unatco_n.py` (editor committed-tree dump at any N,
  auto-builds golden{N}) + `committed_tree_diff.py` (intrinsic-structural vs w-twin comparator) vs native
  `UEDCLI_BSPCSG_TREE_STRUCT` NOREPART. (An agent was mid-bisect when this checkpoint was taken; it had
  only confirmed the gate castle has 0 detail/portal brushes = the pass-staging changes are castle-safe
  by construction. No uncommitted code — tree is clean at `e0a566f10`.)

### Front 2 — the DEEP lever: the axis-aligned REPARTITION over-split (§36/§53)
Even with a perfect committed tree, native's `bsp_build` **repartition over-splits**: with the more-correct
(portal-containing) soup, native emits **6371 nodes vs golden 6314** (+57), and those surplus planes are
**broad axis-aligned walls**, not any single brush's face. This is the **whole-map byte-% gate** — the
coarse % will not reach parity until this lands (it is why §54 nudged the coarse % down −0.18pp even while
improving the true agreement: the +57 node overshoot shifts array positions). Characterized as **large,
oracle-driven, no known static castle-safe fix** — the §20/§36 emit-order thread. This is the hard one.
Extending the committed prefix (Front 1) is necessary but not sufficient; Front 2 is the eventual blocker.

---

## LESSONS / TRAPS (hard-won — do not re-trip)
- **§40 raw-vs-kept trap:** compare only COMMITTED / post-rollback trees. Both native `trace_node_add`
  and the editor oracle NADD log PRE-rollback → phantom graze divergences. Fooled §26–§29/§39.
- **N=105-limited illusion (§53):** a byte-identical prefix at some N does NOT mean parity — bisect to the
  FIRST divergence over the full brush range, not a truncated one.
- **Coarse-% denominator artifact:** when node COUNT differs, positional byte-% can regress even as true
  agreement (shared node-planes / matched bytes) rises. Judge fixes by shared-planes + matched-bytes +
  committed-prefix, not the coarse % alone (§54).
- **Editor gdb "frozen transcript" is a FALSE wedge signal:** an agent blocked inside one long gdb driving
  call looks idle (transcript stops growing) but is working. Do NOT kill on transcript-mtime; wait for the
  completion notification. (Cost a premature kill this session — the data had already been captured.)
- **Editor gdb stability (§52):** per-call gdb *position filters* CRASH the rebuild (Critical-Error
  dialogs); UNCONDITIONAL breakpoint logging is stable. Guardrail every editor run (tracked bg, ≤15-min
  timeout, retry-once).
- **Report-don't-force:** several plausible fixes were correctly REVERTED when they regressed the castle
  or didn't reproduce golden bits (naive normal recompute, root_outside flip, weld reconstruction §49).
  The castle gate is non-negotiable.

## Metric & harnesses (all under `harness/`)
- `ground_truth_bytediff.py` — THE metric (RAW Model-body bytes, never normalized).
- `persec_bytematch.py` — compiled per-section positional %.
- `build_ued_golden.py` — self-built UnrealEd golden (MAP NEW → re-add → `MAP REBUILD; BSP REBUILD <opt>
  OPTGEOM ZONES` → MAP SAVE; needs `--quiet-reads ≥30` at UNATCO scale).
- `editor-tree-oracle/` — gdb `bspAddNode` capture; `editor_struct_unatco_n.py` (committed tree at any N),
  `committed_tree_diff.py` (structural vs w-twin comparator).
- `derisk-normal-weld/` — the §46–§52 normal decode probes (`calcnormal_trace.py`, `paste_cn_output.py`,
  `rebuild_calcnormal_capture.py`, `golden_normal_rule.py`, `node_normal_twincount.py`, …).
- `build_native_{castle,unatco,…}.py`, `unatco_subset.py`, `bsp_health_check.py`, `vectors_attribution.py`.

## Concurrency note
A separate session actively edits config-session files (config.py/dispatch.py/cli.py/uprops.py/movers.py/
tree_io.py/*.toml) and `board/*.md`, and leaves `native-32.log` modified. Commit ONLY your own files by
explicit pathspec (never `git add -A`); leave the concurrent session's files untouched. See the memory note
`board-files-check-foreign-hunks`.

## Where the detail lives
- `sections/92-bspbrushcsg-reallevel-port-plan.md` §11–§54 — the full decode/fix/refutation trail.
- `direction/materialize.md` + `rationale/MIGRATION.md` — the byte-identity target, bspValidateBrush, and where the retired ledger's entries went.
- Auto-memory `native-parity-effort-state.md` — compressed state + this resume pointer.

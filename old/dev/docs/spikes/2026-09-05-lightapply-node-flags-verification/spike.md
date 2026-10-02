# Verification of the N=26 `NF_BoxOccluded` "stray write" claim — refuted, better explanation found

Independent review of `dev/docs/spikes/2026-09-05-lightapply-node-flags/spike.md`'s conclusion
("STOP — the marks are not occlusion. They are a 1024-byte-stride stray write"), per the owner's
request to re-derive or refute with rigor before any exclusion/fix decision. **Verdict: refuted.**
The pattern is fully explained by an already-documented, disassembly-confirmed real mechanism in
`URender::OccludeBsp` — not memory corruption, and not a fixed-camera dependency either.

## Method and a constraint up front

No live editor access was available in this worktree: `uned/DeusExAssets` is a symlink to
`/home/neob91/Games/LutrisDX/drive_c/DX`, which does not exist in this sandbox. I could not run
`golden_pipeline_probe.py` or any gdb capture myself. Everything below is re-derivation from the
prior agent's own committed logs plus cross-referencing already-committed, disassembly-backed
documentation the prior agent cited but did not fully apply.

## Confirmed correct (re-derived independently)

- **Field/offset is really `NodeFlags`, not a misdiagnosis (hypothesis 3, refuted).** Three
  independent sources agree: the `IsCsg` predicate disasm (`0xf68bb mov dl,[ecx+0x37]`, spike
  2026-07-15 §60), the live capture in this spike, and a third, separate spike
  (`2026-08-31-node-flags-live-verify`, not authored by either of us). The stride is 64 bytes/node,
  confirmed against the probe's own GDB script (`*($nodes+$i*64+0x37)`).
- **The offset arithmetic in the spike's table is right.** Read the raw logs directly
  (`logs/golden-pipeline-unatco-n26-surf28.log`, `logs/maploadreplay-unatco-n26-surf28.log`):
  golden N=26 has exactly nodes 16, 32, 48 at `flags=0x10` (isolated bit) and no others in that
  residue class (0, 64 are `0x00`); the `MAP LOAD` replay has 17, 33, 49 (`0x18`, i.e. `0x10|0x08`),
  65 at `0x10`. `16*64=1024`, `17*64=1088`, etc. — matches the spike's table exactly.
- **Gap found: the N=27 claim is unverified.** `dev/docs/spikes/2026-09-05-lightapply-node-flags/
  harness/` and `logs/` contain only the two N=26 captures above — no log, no script invocation
  trace, for an N=27 run anywhere in the repo or `_scratch/`. The central claim used to argue
  "geometry independence" (same node indices on an entirely different, 90-node tree) rests on an
  unlogged, unreproduced run. I could not rebuild it myself (see constraint above). This should be
  re-captured with a committed log before anyone treats it as settled.

## The actual mechanism (already on file, not cross-referenced by the prior spike)

`dev/docs/board/to-build/native-materialize/port-urender-getvisiblesurfs-so-each-light-gets/
overview.md` (committed 2026-09-02, three days before the "stray write" spike, and the very board
item `visible_surfs.rs`'s own doc-comment cites) already disassembled the box-occlusion step the
prior spike traced to `render.dll 0x100193db`. Its step 4:

> Bound-box occlusion (`0x1001932c`): skipped when `node->iRenderBound == -1`; else
> `BoundVisible(...)` ... `0` -> `NodeFlags |= NF_BoxOccluded (0x10)` ... **Amortization trap: the
> box test only runs when `NodeFlags & 0x10` is already set OR `((iNode ^ *(0x1005fa24)) & 0xf) ==
> 0`, and that counter is bumped only in `DrawWorld` — which this path never calls — so the same
> fixed 1/16 of nodes is tested for every light.**

This single, pre-existing fact reproduces every property the prior spike measured, with no need for
a stray/mis-strided write:

| observed property | explained by |
|---|---|
| exactly every 16th node (1024 = 16 x 64-byte stride) | `& 0xf` is a mod-16 test — the "1024 bytes = the 0x400x0x400 raster face size" coincidence the prior spike flagged is the wrong reason: right number, unrelated cause |
| same 3 indices across golden N=26 (twice) | `iNode mod 16` vs the counter is content-independent by construction, not by accident |
| same 3 indices at (claimed, unverified) N=27 | same — if the N=27 claim reproduces, this mechanism predicts it exactly; a stray-write theory has no principled reason to land on the same mod-16 class after a geometry change |
| flags never change across 1400 rays / 5 lights | the gating counter is bumped only by `DrawWorld`, which a headless `MAP IMPORT -> MAP REBUILD -> LIGHT APPLY -> MAP SAVE` batch never calls — so the tested residue class never advances for the entire session |
| `MAP LOAD` pipeline: base shifts by exactly +1 node, count 3->4 | consistent with exactly one incidental `DrawWorld`/redraw firing somewhere inside `MAP LOAD`'s command handling (bumping the global counter 0->1) that a bare `MAP IMPORT` into an already-open empty level does not trigger; the shift is a small, discrete +1, not the unbounded/random shift a wall-clock-timer-driven repaint or heap-history-sensitive corruption would produce |

## Hypothesis 2 (fixed camera viewpoint) — refuted on architecture, not just measurement

The task asked me to check whether the marked nodes correlate with a fixed default/editor camera.
They cannot, by construction: `GetVisibleSurfs` (`render.dll 0x100187b0`) opens a fresh **per-light**
offscreen viewport at **that light's `Location`** for each of the six cube faces (disassembly-
confirmed, same board item, "opens a `0x400 x 0x400` offscreen viewport at the light's Location") —
there is no persistent "the editor's camera" state feeding this code path at all, so a live probe of
`GCameraLocation`/viewport camera globals would not have been informative even if I'd had editor
access. The marked-node pattern is gated by `iNode mod 16` against a frame counter, not by spatial
visibility from any single viewpoint.

## Verdict

Not hypothesis 1 (memory-safety stray write), not hypothesis 2 (camera-state recipe hazard as
framed), not hypothesis 3 (misdiagnosed offset). **A fourth explanation, already on file and now
connected to this bug for the first time:** `NF_BoxOccluded` is a real, geometry-driven box-occlusion
result, but the editor amortizes the (expensive) box test across frames via a global counter that
only advances on a viewport redraw (`DrawWorld`). The golden-build recipe never opens or paints a
viewport between `MAP REBUILD` and `LIGHT APPLY`, so that counter is frozen at whatever it happened
to be left at (apparently 0 for a fresh `MAP IMPORT`, 1 after a `MAP LOAD`) for the entire
`LIGHT APPLY` batch — meaning only 1/16 of the tree ever gets box-tested, and the shadow-ray walker
(which does not strip `0x10` at a crossing, see the parent spike) reads that badly-undersampled cache
as if it were complete.

This is real UED22 behavior, not corrupted memory — but it is very unlikely to match a normal
interactive editing session, where the viewport paints continuously and the counter cycles through
all 16 residues within seconds, before a human ever presses "Rebuild Lighting". The golden-build
recipe's headlessness is what exposes it.

## Recommendation

Do not exclude these surfaces as an inconsequential reference defect yet — that framing assumes the
bit is noise, and it measurably is not (it flips real shadow results on three real surfaces via a
real, if starved, occlusion test). Before an owner ruling:

1. Re-capture the N=27 claim with a committed log — it currently has none.
2. Confirm the amortization-counter theory live: read `*(0x1005fa24)` at `LIGHT APPLY` entry in both
   pipelines, and check whether it is 0 (golden) / 1 (`MAP LOAD`) as predicted.
3. Test the actual fix this implies: force >=16 viewport redraws (e.g. open a camera and issue
   enough `CAMERA UPDATE`/equivalent redraws, or find another way to trigger `DrawWorld`) between
   `MAP REBUILD` and `LIGHT APPLY` so the counter cycles through every residue and every node gets a
   real box test before lighting bakes. If that makes the golden build deterministic and its
   `NF_BoxOccluded` set matches what a full, un-amortized box-occlusion pass computes, this is a
   **recipe fix** (and a real feature `visible_surfs.rs` could then faithfully port), not a defect to
   mask.

None of this was run live here (see the environment constraint above) — this is a documentary and
arithmetic re-derivation, not a new probe. Someone with working `DeusExAssets` access should run
step 2 and 3 before treating either verdict as final.

## Live follow-up (this worktree) — the address is wrong, the mechanism is real

This worktree's `uned/DeusExAssets` symlink is equally broken, but the actual asset chain has since
moved to `~/.uedcli` (here `$UEDCLI_HOME/config.toml`) pointing at `dev/games/deusex/{System,
Textures,Sounds,Music,Maps}` — an absolute host path shared across worktrees, present and populated
in this sandbox. `bin/test` builds `uedcli_native`; a fresh `.venv` plus that gave working editor
access, confirmed by running the real golden pipeline end to end. All three open questions were run
live with a new harness, `harness/counter_and_flags_probe.py` (based on the parent spike's
`golden_pipeline_probe.py`, minus its `--isurf` gate — captures the counter + full `NodeFlags` array
at the first `illuminateSurf`/walker entry, unconditionally, then detaches). Trunks: fresh N=26/N=27
subsets of `dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx` (this worktree's extraction orders actors
differently from the historical `_scratch/bsp-parity-proj` trunk — e.g. actor 26 here is `Brush511`,
not `Brush514` — so absolute node counts/indices below are NOT the parent spike's 80-node numbers;
the counter/residue relationship is what was tested here, not exact reproduction of surf 28's
`Light155` divergence). Logs: `logs/n26-baseline.log`, `logs/n26-baseline-run2.log`,
`logs/n27-baseline.log`, `logs/n26-camera-only.log`, `logs/n26-newcameras3.log`,
`logs/n26-newcameras16.log` (the `--redraws N` variant, `logs/n26-redraws20.log`, is subsumed by
`n26-camera-only.log` — see below).

**1. The counter address is wrong.** `*(int*)0x1005fa24` reads `269422604` (`0x100f100c`) — not 0,
not 1, not small. It is IDENTICAL across two independent fresh-process runs of the same N=26 build,
across N=26 vs N=27 (different geometry, different node counts: 660 vs 670), and after 20
`REDRAWALLVIEWPORTS` calls between `MAP REBUILD` and `LIGHT APPLY` (`n26-redraws20.log`). A value
that never moves under genuinely different amounts of engine work, across fresh processes, is not a
live per-frame counter — `0x100f100c` reads like an in-module pointer/constant (`render.dll` loads
around `0x10000000`), not `URender`'s frame count. **The board item's cited address is refuted as the
literal counter location.**

**2. But the qualitative mechanism it describes is real and fully reproduced.** Grepping each run's
full node dump for the five members of one residue-mod-16 class shows the box-occlusion test
tracking a hidden counter exactly as the formula `(iNode ^ counter) & 0xf == 0` predicts, even though
`0x1005fa24` isn't that counter:

| run | class tested (residue mod 16) | the class's outcome | flagged node |
|---|---|---|---|
| N26 baseline, no camera ever opened | 0: `{0,16,32,48,64,...}` | 0=`0x08` (unrelated bit), 16/32/64=`0x00`, **48=`0x18`** | 48 |
| N26 baseline, repeat | same | identical | 48 |
| N27 baseline (different tree, 670 nodes) | 0: `{0,16,32,48,64,...}` | 0/16/32/48=`0x00`, **64=`0x10`** | 64 |
| N26 + one `CAMERA OPEN` (no further redraws) | 1: `{1,17,33,49,65,...}` | 1=`0x08`, 17/33/65=`0x00`, **49=`0x10`** | 49 |
| N26 + `CAMERA OPEN` + 20x `REDRAWALLVIEWPORTS` | 1 (same as above — no further shift) | identical to the row above | 49 |
| N26 + 3 distinct new `CAMERA OPEN`s | 3: `{3,19,35,51,...}` | **51=`0x10`** | 51 |
| N26 + 16 distinct new `CAMERA OPEN`s | 0 (wraps back) | **48=`0x18`**, byte-identical to the untouched baseline | 48 |

Every `CAMERA OPEN` — its documented one-time initial-creation paint (`rendering.md`) — advances the
real (still-unlocated) counter by exactly 1; 16 of them wrap it back to 0 and reproduce the baseline
byte-for-byte. `REDRAWALLVIEWPORTS` issued after a camera is already open advances nothing (consistent
with `rendering.md`: it changes state without painting under headless SoftDrv). So: **the amortization
counter is real, live-confirmed, and paint-driven — just not at `0x1005fa24`.** That address should be
struck from the board item; the real counter is still unlocated.

**3. Forcing redraws does not make the golden build's box-occlusion complete.** Every experiment above
relocates which ONE of 16 residues gets a real box test for the ENTIRE `LIGHT APPLY` batch — it does
not cover more than 1/16 of eligible nodes in a single run. `LIGHT APPLY` is one atomic engine call
over every light; nothing in `commands.md` exposes a per-light hook to interleave a paint event
between lights, so there is no console-level way to cycle the counter through all 16 residues within
one lighting pass. A recipe fix (insert N `CAMERA OPEN`s before `LIGHT APPLY`) only **relocates** the
under-tested set; it cannot make it disappear. **No recipe-level fix is recommended** — this differs
from the parent spike's "stray write" framing (real, if starved, occlusion, not memory corruption)
but reaches the same operational conclusion: UNATCO's box-occlusion-sensitive divergence is not
reachable by a faithful port (the amortization is real UED22 behavior, but no `LIGHT APPLY`-time
recipe can un-starve it) and not fixable from the console. This still needs an owner decision — accept
the affected surfaces as a documented reference defect (with a bound, the way the N8 base-fp exclusion
is bounded), or rebuild the reference some other way. Do not mask it on an agent's authority.

## CORRECTION — "the address is wrong" was itself a bug: `render.dll` is relocated

A coordinator-relayed review flagged a real lead this spike's first pass missed: all 3 samples above
landed on residue 0 with no camera ever opened, which — if that's a deterministic fresh-process
invariant, not incidental state — is a portable native algorithm, not an unfixable artifact. Re-tested
live, with a corrected probe. **Verdict: the invariant is real and now confirmed with direct
instruction-level rigor across all 5 ladder levels — the "counter address is wrong, refuted" claim
above is WRONG, and the actual bug was in this spike's own memory read.**

**The bug**: `*(int*)0x1005fa24`, read literally, assumes `render.dll` loads at its preferred image
base `0x10000000`. It doesn't — `Editor.dll` also prefers `0x10000000` and wins that address (confirmed:
`illuminateSurf`/the walker hit correctly there in every probe), so Wine's loader relocates `render.dll`
elsewhere — observed live, reproducibly, at `0x015b0000` across every session in this worktree. A
literal read of `0x1005fa24` in that case silently reads `Editor.dll`'s own memory (whatever pointer
happens to sit there), not the counter — which explains the earlier "fixed, pointer-looking,
un-advanceable by `REDRAWALLVIEWPORTS`" result perfectly: that data has nothing to do with rendering at
all. Confirmed via `/proc/<pid>/maps` (`harness/diag_render_base.py`) and cross-checked against the PE
export table (`rdis.py exports Render`), not offset arithmetic alone:
`?GetVisibleSurfs@URender@@...` at file address `0x100187b0`, `?DrawWorld@URender@@...` at
`0x10017680` — both land exactly on real function prologues once remapped to the live base.

**Corrected direct measurement** (`harness/counter_direct_probe.py`, remaps every `render.dll`
address to the live base found in `/proc/pid/maps` before setting breakpoints): breaking on
`GetVisibleSurfs`'s entry (once per light) and logging the counter at each entry, across a REAL,
complete `LIGHT APPLY` run per level:

| level | lights in this build | counter at every `GetVisibleSurfs` entry | `DrawWorld` fires |
|---|---|---|---|
| UNATCO (`N26`) | 12 | 0, all 12 | once, AFTER light 12's last surf |
| WanChai (`N44`) | 10 | 0, all 10 | once, AFTER light 10 |
| Bar (`N250`) | 49 | 0, all 49 | once, AFTER light 49 |
| Island (`N300`) | 159 | 0, all 159 | once, AFTER light 159 |
| OceanLab (`N300`) | 54 | 0, all 54 | once, AFTER light 54 |

Every level, every light, counter is exactly 0 for the entire `LIGHT APPLY` pass — `DrawWorld` (the
only write site to this address in the whole `.text` section, confirmed by a full-module disassembly
grep) fires exactly once, always AFTER the very last light has already finished, too late to affect
any box-occlusion test in that build. **This retroactively validates, rather than refutes, the
original NodeFlags-array evidence** (residue-0 flagged nodes, reproducible across the same 5 levels,
shifting +1 per `CAMERA OPEN`) — that evidence never depended on the buggy address; only the
direct-memory-read cross-check did.

**Conclusion**: every fresh-process headless golden build (`MAP IMPORT → MAP REBUILD → LIGHT APPLY →
MAP SAVE`, no viewport) deterministically box-tests exactly the `iNode % 16 == 0` residue for its
entire `LIGHT APPLY` pass, on all 5 campaign levels regardless of light count. This is a real,
portable, geometry-independent property of UED22's own headless recipe — not incidental process
state — confirming the review's lead.

## Scoping the faithful native fix — `URender::BoundVisible` is a real, unported rendering primitive

Per the review, attempted the actual port: gate native's box-occlusion to `node_index % 16 == 0`
(matching the confirmed invariant) and implement the box-visibility test itself. Traced the call
chain live: `GetVisibleSurfs`'s per-node box check (`render.dll 0x1001932c` onward, file-relative)
calls a virtual method at `[Frame_vtable + 0x80]`; resolved live (`harness/
boundvisible_target_probe.py`, breaks right before the `call eax` and reads the pushed `FBox` argument
off the stack) to a STABLE target, remapped and identified via the PE export table:

```
?BoundVisible@URender@@UAEHPAUFSceneNode@@PAVFBox@@PAVFSpanBuffer@@AAUFScreenBounds@@@Z
int URender::BoundVisible(FSceneNode*, FBox*, FSpanBuffer*, FScreenBounds&)
```

at file address `0x10012100`. Live-captured box arguments are real level-space AABBs (e.g.
`[-2736,-1504,-80]-[1776,1616,416]`), confirming the call site and argument decode are right.

Disassembling `BoundVisible` itself (`/tmp/boundvisible_full.txt`, not committed — regenerable via
`rdis.py dis Render 0x10012100 0x1bf0`): it classifies each of the box's corners against the frame's
view planes (an outcode-style test building a bitmask 0–0x1f from per-axis `comiss` compares), has
an early-return path (`ret 0x10`, matching the 4-argument `__thiscall`) for the trivial "corner
comparisons agree, no clipping needed" case at file offset `+0x24c`, and a substantially larger
continuation past that for the partial-visibility/clipping case — genuinely comparable in size and
character to `URender::GetVisibleSurfs` itself (which took real, multi-pass RE effort to port) and to
the `FSpanBuffer` rasterizer this same campaign's WanChai N45 item explicitly scoped as "a real spike,
not attempted yet."

**Not implemented here.** A byte-exact port needs the same rigor already applied to `GetVisibleSurfs`
and the span buffer — full disassembly, a controlled-fixture cross-check, and a review — not a rushed
approximation in this pass. Standing in a cheaper proxy (e.g. reusing the existing per-zone
`SpanBuf::any_visible` reachability check already in `visible_surfs.rs` as a "box visible" stand-in)
would UNDER-occlude relative to the real per-box screen test and is exactly the kind of guessed
approximation `NATIVE-MATERIALIZE.md`'s prime directive forbids ("no hacks just to satisfy a single
package scenario"). Filed as a board item
(`dev/docs/board/inbox/port-urender-boundvisible-box-occlusion-test/`) with the address/signature
handoff above, scoped like the WanChai span-buffer item rather than attempted here.

**Net status**: the residue-0 gate is now a confirmed, portable fact suitable for a faithful native
implementation once `BoundVisible` is ported. Until then this remains exactly where the parent spike
left it — UNATCO N26's `Light155` divergence is not closed by a recipe fix (established above) and
not yet closed by a native port (needs the `BoundVisible` spike) — an open item, not an exclusion.

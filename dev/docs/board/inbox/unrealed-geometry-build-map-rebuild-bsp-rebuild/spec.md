# UnrealEd / UCC.exe geometry, lighting, and paths build — reverse-engineered specification

**Subject:** the real UnrealEd 2.2 editor (Deus Ex-era UnrealEngine-1, UED22 build) as shipped in
`uned/UED22/*.dll`/`UCC.exe`/`unrealed.exe` — specifically what happens when the editor's three build
operations run: geometry/BSP (`MAP REBUILD`/`BSP REBUILD`), lighting (`LIGHT APPLY`), and AI paths
(`PATHS DEFINE`/`PATHS BUILD`) — both as console verbs and as the `UnrealEd.exe` GUI's `Build` dialog
(F8 / Ctrl-B), which is confirmed (§1.5) to dispatch through the identical console-verb strings, not a
separate code path.

**Evidence basis — read this before trusting any claim below.** Every claim here traces to one of:
static disassembly of the actual shipped DLLs (function/RVA cited), a live-driven real UnrealEd
session's observed behavior (console commands + log/export/gdb), or a byte-level diff against a real
editor-written `.dx` package. **No claim here is sourced from, or corroborated by, this project's own
Rust/Python reimplementation** (`uedcli-native/`, `uedcli/`) or its bug tracker — that code is a
separate, unproven hypothesis about the algorithms below, and several of its own open bugs (cited
nowhere in this document) show it does not yet match the editor in all cases. Treat this document,
not that code, as the ground truth to reimplement against.

**Confidence tags used throughout:**
- **[DISASM addr]** — read directly out of the compiled `Editor.dll`/`Engine.dll`/`core.dll` by
  disassembly, with the cited virtual address (VA; subtract `0x10000000` ImageBase for the file RVA).
- **[LIVE]** — observed by actually driving a real, running UnrealEd/UCC.exe session (console
  commands, `Editor.log`, exported `.dx` files, or a `gdb` breakpoint on the live process) and reading
  the result.
- **[BYTE-DIFF]** — established by a positional byte comparison between two real editor-written
  `.dx` files, or a real editor-written file and a hand-decoded structural model of it.
- **[INFERRED]** — the source document itself flags this as inference/hypothesis rather than a
  directly cited instruction or observation. Weaker; called out explicitly wherever used.
- **[OPEN]** — a question the gathered evidence does not settle. Listed in §18.

Every fact is further cited to the specific evidence file it came from (paths relative to
`dev/docs/spikes/2026-07-15-native-materialize/`, or to an earlier top-level spike under
`dev/docs/spikes/`), so a claim can be re-derived and re-verified independently.

---

## 1. What "geometry build" is, and how it's invoked

UnrealEd has no separate "geometry build commandlet" — geometry building is a console-command-driven
operation inside a running editor session (`UCC.exe editor` or `unrealed.exe`), triggered by the
`MAP REBUILD` or `BSP REBUILD` exec verbs.

### 1.1 Two distinct entry points, and empirical proof they are not equivalent

- **`MAP REBUILD`** resolves to `UEditorEngine::Rebuild` **[DISASM Editor.dll 0x65a40]**. It runs
  `csgRebuild` (the per-brush CSG loop, §2) and the tree partition (`bspBuild`, §6), but does **not**
  re-run leaf/zone enumeration: a session driven with only `MAP REBUILD` left the `Leaves` array
  stale/non-1:1 with the level's actual empty cells **[LIVE; `sections/91-leaves-overproduction.md`,
  `sections/87-cause2-shattered-tree.md`, corroborated independently in
  `sections/89-ued-golden-pipeline.md:9-20`]**.
- **`BSP REBUILD <quality> [OPTGEOM] [ZONES] [BALANCE=n] [PORTALBIAS=n]`** resolves to a separate
  exec parser **[DISASM Editor.dll 0x65220]**. Per its decoded dispatch: the visibility/leaf pass
  (`TestVisibility` → `AssignLeaves`, engine vtable slot `+0x264`) runs **only if the `ZONES` keyword
  is given**, and `bspOptGeom` (vtable slot `+0x218`) runs **only if `OPTGEOM` is given**
  **[DISASM, LIVE; `sections/91-leaves-overproduction.md`]**.

**Direct empirical proof these two commands produce different geometry**, driving the real editor on
the real 734-brush UNATCO level **[LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:294-302`]**:

| rebuild command issued | nodes | surfs | vectors | leaf refs/leaf |
|---|---:|---:|---:|---:|
| bare `MAP REBUILD` | 6314 | 3616 | 599 | 9.45 (stale leaves) |
| `MAP REBUILD; BSP REBUILD GOOD OPTGEOM ZONES` | 7273 | 3616 | 599 | 1.00 |
| `MAP REBUILD; BSP REBUILD OPTIMAL OPTGEOM ZONES` | 6859 | 3616 | 599 | 1.00 |

**Non-obvious finding, stated directly by the source:** the interactive `BSP REBUILD GOOD` command
does **not** reproduce the same tree partition as the automatic `csgRebuild`'s own GOOD-equivalent
run inside a bare `MAP REBUILD` — it produces *more* nodes than even `BSP REBUILD OPTIMAL` (7273 vs
6859 vs 6314). "GOOD" is not one deterministic partition in the real editor; the two rebuild code
paths diverge even at nominally the same optimization level. **Surfs and vectors, by contrast, are
invariant across all three** — a real architectural fact: `BSP REBUILD` re-partitions the node tree
but never touches the surf/vector pools (those were already fixed by `csgRebuild`'s CSG pass).

So: `MAP REBUILD` alone gives an incomplete build (stale zones, and per §1.1 a node tree that later
gets discarded and rebuilt differently by any subsequent `BSP REBUILD`). A faithful reproduction that
wants a *complete, final* build must issue the explicit `BSP REBUILD <quality> OPTGEOM ZONES` step —
which, per the table above, itself produces a **different, quality-dependent** node tree, not merely
"the same tree plus zones."

### 1.2 `MAP REBUILD` / `BSP REBUILD` quality and parameter keywords

Per the `0x65220` exec parser, byte-verified defaults when a keyword is omitted
**[DISASM Editor.dll 0x65220; `dev/docs/spikes/2026-06-26-bsp-partition-heuristic-from-binary.md` §4]**:
- `Balance` absent → **50** (`mov edx,0x32; cmove ecx,edx` at `0x1006530b`).
- `PortalBias` absent → **70** (`mov edx,0x46; cmove ecx,edx` at `0x1006533c`), packed into the high
  byte of a combined word (`BalancePacked`) via `shl ecx,8`.
- `Optimization` for a bare rebuild resolves to **OPTIMAL** (stride 1, exact — see §6.2). The
  `GOOD`/`OPTIMAL` label governs which *cleanup* passes run (§7), not the partition scoring itself.

**[OPEN] — still unresolved despite §1.1's empirical table:** whether these parser-parsed
`Balance`/`PortalBias` values (50/70 default, or whatever a user types with `BALANCE=`/`PORTALBIAS=`)
are what actually produces the 6859-vs-7273 divergence above, or whether that divergence instead
comes purely from the `OPTIMAL` vs `GOOD` stride difference (§6.2) with `Balance`/`PortalBias` fixed
at their hardcoded values regardless. A separately decoded call chain —
`csgRebuild → bspRepartition [Editor.dll 0x49fc0] → bspBuild → SplitPolyList → FindBestSplit` — found
`bspRepartition` pushes **hardcoded literal immediates** `Balance=12, PortalBias=0, Opt=GOOD` directly
in its own machine code (`0x1004a02f`/`0x1004a031`), not read from any argument
**[DISASM; `re-raw-zones/findbestsplit-params-decode.md:6-34`]** — and this exact `Balance=12`
weighting (`Score = 12·|F−B| + 88·Splits`, i.e. `100−12=88`) is **independently confirmed** by a
second, separately-dated decode pass reading the same instructions
**[DISASM; `sections/92-bspbrushcsg-reallevel-port-plan.md:744-747`]**, and reported byte-exact against
a real 95-brush castle level (1156/1156 node match). This makes it very likely that `bspRepartition`'s
world-tree call *always* uses `Balance=12/PortalBias=0`, regardless of what a user types on `BSP
REBUILD BALANCE=`/`PORTALBIAS=` — but this was not directly A/B-tested (build the same brush set via
`BSP REBUILD BALANCE=12 ...` vs `BSP REBUILD BALANCE=90 ...` and diff) by any evidence gathered, so it
remains formally open. See §5.3 for the full three-call-site breakdown.

**A separate, real, live-measured fact about the GOOD-mode stride heuristic itself** — on the real
734-brush UNATCO map's CSG-root poly soup (NumPolys=2449, stride=122 under `GOOD`), the sparse-strided
sample scores a horizontal splitter candidate *worse* (score 100) than a slanted-wall candidate (score
24), while a full stride-1 scan of the identical soup inverts the ranking (horizontal split scores
2676, "4.6× better" than the slanted wall at 12328) **[LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:749-755`]**.
This is a genuine, observed property of the real editor: `GOOD` mode's stride-based candidate sampling
can and does pick a globally poor splitter on real content, because it only ever samples a fraction of
the candidate polys — not a hypothetical edge case.

### 1.3 The full build sequence a faithful reproduction must issue

Live-verified procedure that produces a complete, reproducible build **[LIVE;
`sections/89-ued-golden-pipeline.md:15-20`]**:

```
MAP LOAD FILE=<level>            (or MAP NEW + paste/import the brush/actor set)
MAP REBUILD                      csgRebuild + world-tree repartition (§2, §6)
BSP REBUILD OPTIMAL OPTGEOM ZONES   forces bspOptGeom (§7.3) and TestVisibility/zoning (§8) to run,
                                     AND re-partitions the node tree again (§1.1 — not idempotent)
LIGHT APPLY                      (optional — lighting bake; a rebuild invalidates existing lighting)
MAP SAVE FILE=<out>
```

**Determinism, live-verified:** running this exact sequence twice on the same 161-actor castle trunk
(95 Brush, 62 Light, 1 ZoneInfo, 1 SkyZoneInfo, 1 PlayerStart, 1 LevelInfo) produced two `.dx` files
of identical size (448,858 B) whose Model bodies are **100.00% byte-identical across all 17 sections**
— the only difference in the entire file is 270 header bytes (package GUID + save timestamp)
**[LIVE, BYTE-DIFF; `sections/90-castle-ued-rebaseline.md:37-44`]**. The real editor's build is a
reproducible fixed point given identical input and identical command sequence.

### 1.4 `MAP SAVE` — package write mechanics

**[DISASM `core.dll` string table]** `UObject::SavePackage`'s embedded string literals show phase
order: `SaveExports → SaveImportMap → SaveExportMap → RewriteSummary`, then a literal
`"Save.tmp"`/`"Moving '%s' to '%s'"` pair — the package is serialized into a temp file, its header is
patched last inside that temp file, then the temp file is moved onto the destination path. (This is
extracted from the wide-string table per the methodology in §21, not from live behavior — treat the
*existence and order* of these phases as solid, the exact move-vs-copy mechanism as unconfirmed.)

`MAP REBUILD` invalidates existing lighting — a subsequent `LIGHT APPLY` is required to rebuild it if
lighting is wanted in the output; `PATHS`-related data is not wiped by a geometry rebuild.

### 1.5 The GUI `Build` dialog (`UnrealEd.exe`, F8 / Ctrl-B) — confirmed sends the same exec strings

**[DISASM `unrealed.exe` + `Editor.dll` wide-string tables]**. `unrealed.exe` is the WxWindows GUI
frontend; per the project's established methodology (§18), its wide-string table holds printf-style
templates that get formatted and handed to the same `Exec()` the console uses (already established
for other GUI actions, e.g. `CAMERA UPDATE FLAGS=%d MISC1=%d MISC2=%d …`). Direct extraction from
`unrealed.exe`'s string table confirms this holds for the `Build` menu/dialog too — it is not a
separate code path from the console verbs documented throughout this spec, it is the *same* verbs,
string-formatted from dialog controls:

```
'MAP REBUILD VISIBLEONLY=%d'
'BSP REBUILD'  ' LAME'  ' GOOD'  ' OPTIMAL'  ' OPTGEOM'  ' ZONES'  ' BALANCE=%d'  ' PORTALBIAS=%d'
'LIGHT APPLY SELECTED=%d VISIBLEONLY=%d'
'PATHS DEFINE'
'PATHS BUILD'
```

The `BSP REBUILD` line is five separate string fragments concatenated based on which dialog controls
are set — quality is a radio group (`&Lame`/`&Good`/`&Optimal`), `OPTGEOM`/`ZONES` are checkboxes
(`&Optimize Geometry`/`&Build Visibility Zones`), `BALANCE=%d`/`PORTALBIAS=%d` come from two
`msctls_trackbar32` sliders labeled `Minimize Cuts`↔`Balance Tree` and `Ignore Portals`↔`Portals Cut
All`. Two adjacent string-table entries, `15` and `70`, sit immediately next to those two slider
labels respectively — `70` exactly matches the console's own independently-disassembly-confirmed
default `PortalBias` (§1.2), which is strong (though not itself instruction-level-confirmed — a
dialog-resource-table parse would be needed to be fully certain) evidence that these are the dialog's
default slider positions, and that the **long-standing "classically 15" Balance folklore refers to
this GUI default, not the console's own omitted-argument default of 50** (§1.2) — two different
defaults for two different invocation paths, previously conflated.

**The `Build` submenu / F8 dialog exposes four independent scopes, not one combined action**
(`unrealed.exe` menu-item strings: `Rebuild &BSP Only`, `Rebuild &Geometry Only`, `Rebuild Lighting
Only`, `Rebuild AI Paths`, `&Build All`; the `Build Options` dialog's own tab strip: `Geometry` |
`BSP` | `Lighting` | `Paths`):

| Menu item | Exec string(s) sent |
|---|---|
| **Rebuild Geometry Only** | `MAP REBUILD VISIBLEONLY=<checkbox>` alone |
| **Rebuild BSP Only** | `BSP REBUILD <quality> [OPTGEOM] [ZONES] BALANCE=<n> PORTALBIAS=<n>` alone — re-partitions/optimizes the *existing* geometry without re-running CSG |
| **Rebuild Lighting Only** | `LIGHT APPLY SELECTED=<n> VISIBLEONLY=<n>` alone |
| **Rebuild AI Paths** | `PATHS DEFINE` then `PATHS BUILD` |
| **Build All** (Ctrl-B; tooltip: `"Build All (as per current build settings)"`) | all of the above, in order: geometry → BSP → lighting → paths |

This resolves an item this spec previously flagged as open (§18 below): "Geometry Only" and "BSP
Only" being separate GUI actions confirms `MAP REBUILD` (→ `csgRebuild`, §2) and `BSP REBUILD` (→
`bspRepartition`, §5.3) really are two independently-invokable operations with distinct scopes, not
one operation under two names — and it confirms **`Build All`'s default sequence is exactly the
two-step `MAP REBUILD; BSP REBUILD <quality> OPTGEOM ZONES` sequence** this spec's §1.3 already
established empirically by live-driving the console. The GUI does not do anything the console verbs
can't reproduce.

The dialog also has a checkbox `&Only Rebuild Visible Actors?` (→ `VISIBLEONLY=`) and, on the
Lighting tab, `&Apply selected lights/lights in selected zone descriptors only` (→ `SELECTED=`/
`VISIBLEONLY=` on `LIGHT APPLY`). `Editor.dll`'s own wide-string table independently confirms
`SELECTED=`, `VISIBLEONLY=`, `LOWOPT`, `HIGHOPT` as tokens its exec parser recognizes as argument
keys — i.e. the parser side agrees with the GUI's template side, not just the GUI's own claim about
itself.

A `Build` progress/results panel shows: `Brushes`, `Zones`, `Polys`, `Nodes`, a `Ratio` (format
`%1.2f:1`), `Max Depth`, `Avg Depth`, `Points`, `Lights`, `Paths` counts — confirming these are all
values the real editor computes and surfaces after a build (a useful checklist for what a
reimplementation's own reporting should be able to reproduce), though the exact formula for `Ratio`/
`Max Depth`/`Avg Depth` was not decoded here.

A confirmation dialog specific to `PATHS BUILD` reads: *"This command will erase all existing
pathnodes and attempt to create a pathnode network on its own. Are you sure this is what you want to
do?"* / *"NOTE: This process can take a VERY long time."* — a genuine user-facing warning that the
console verb has no equivalent guard for (driving `PATHS BUILD` headlessly skips this confirmation
entirely, per the general "driving is fire-and-forget, dialogs don't block a scripted `EXEC`"
behavior documented in `dev/docs/unrealed/quirks.md`).

---

## 2. Top-level pipeline: `csgRebuild`

`UEditorEngine::csgRebuild` **[DISASM Editor.dll 0x4a650]** is the driver a geometry rebuild runs
through. Decoded structure **[DISASM; `dev/docs/spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` §2]**:

1. `EmptyModel` — clears the level's world `UModel` (Nodes/Surfs/Verts/Points/Vectors/Zones all reset).
2. Iterates the level's brushes **in actor order** (`ULevel::Brush()`, `AActor::IsStaticBrush`) — no
   re-sorting by any heuristic. `MAP SENDTO FIRST/LAST` reorders the underlying actor list this loop
   walks; nothing else changes brush processing order. **The last operation touching a region of space
   wins** — this is the direct mechanism behind "brush order determines the final geometry."
3. For each brush in that order, applies its CSG operation via `UEditorEngine::bspBrushCSG` (a virtual
   call, `vtable+0x214`) — the whole of §3 below. **Before CSG proper, each brush is first run through
   `bspValidateBrush` (§3.0)** and, for portal brushes, forced-flag handling (below).
4. After all brushes: the world tree is repartitioned (`bspBuild`, via `bspRepartition`, §6), then
   `bspRefresh` (§7.1), `bspMergeCoplanars` (§7.2), `bspOptGeom` (§7.3, but see §1.1's open question on
   whether this runs unconditionally or only under `BSP REBUILD ... OPTGEOM`), `bspBuildBounds`
   (§9).

Portals get special flag handling before CSG (decoded at `Editor.dll 0x4a800-0x4a821`
**[DISASM; `dev/docs/spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` §3]**): a brush
with `PF_Portal` set has any `PF_Semisolid` bit stripped and `PF_NotSolid` forced on, **before**
`bspBrushCSG` sees it — a zone-portal brush is unconditionally non-colliding and non-solid,
regardless of how it was authored. **A real portal brush is processed in the same structural,
pre-repartition CSG pass as ordinary solid brushes, not deferred to a later pass** — live-observed on
a real portal brush (`PolyFlags = PF_Portal|PF_TwoSided|PF_NotSolid|PF_Invisible`): it produces exactly
2 committed nodes in the pre-repartition tree, coplanar-antiparallel to an existing solid wall, and its
faces are valid `FindBestSplit` candidates (non-CSG splitters that carve nothing but still participate
in partition scoring) **[LIVE gdb; `sections/92-bspbrushcsg-reallevel-port-plan.md:2199-2214`]**. A
census of all 120 shipped Deus Ex maps found every one of 978 brush-level portal brushes is `CSG_Add`;
zero are `CSG_Subtract` **[LIVE content census; same doc, `:2254-2257`]** — a fact about shipped
content, not a hard engine constraint.

---

## 3. Per-brush CSG: `bspBrushCSG`

**[DISASM Editor.dll 0x355e0]**. Applies ONE brush's CSG operation (Add / Subtract / Intersect /
Deintersect) into the level's world `UModel`. Source lineage confirmed genuine: an `appFailAssert` in
`FPoly::SplitWithPlane` embeds the original source path
`C:\GameDev\UnrealTournament\Engine\Src\UnFPoly.cpp` — UED22's geometry code is the UnrealTournament
(v469-era) engine lineage, i.e. the well-documented `UnFPoly.cpp`/`UnBsp.cpp`/`UnEdCsg.cpp` algorithm
family **[DISASM; `dev/docs/spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` §1]**.

Signature: `bspBrushCSG(GEditor, ABrush* Actor, UModel* Model, DWORD PolyFlags, ECsgOper CsgOper,
UBOOL bBuildBounds, UBOOL bMergePolys)`. `ECsgOper`: Active=0, Add=1, Subtract=2, Intersect=3,
Deintersect=4 **[DISASM; `sections/82-bspbrushcsg-port-decode.md:90`]**.

### 3.0 `bspValidateBrush` — the per-brush pre-CSG link pass

**[DISASM Editor.dll 0x37290]**. Before `bspBrushCSG` runs its filter passes, the real editor runs a
per-brush pre-pass that assigns each of the brush's polys an `iLink` so that coplanar, same-facing
(dot > threshold), same-texture, same-axes, same-flags faces belonging to **one brush** end up sharing
a single `FBspSurf` once merged — `bspMergeCoplanars` (§7.2) later fuses the linked fragments using
this seed. This runs after `FPoly::Finalize` has already produced the winding-derived normal, not
against a possibly-stale authored one. This is a genuine, distinct pipeline stage, separate from
`bspBrushCSG`'s own filter recursion (§3.2-3.5), and is what lets e.g. a multi-facet tessellated dome
cap collapse to a single surf the way the real editor's output does
**[DISASM; `sections/92-bspbrushcsg-reallevel-port-plan.md:405-415`]**. It also logs
`"BspValidateBrush linked %i of %i polys"`; `linked < total` indicates the brush is not watertight (an
open edge, T-junction, or self-intersection) **[DISASM; `dev/docs/spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` §5]**.

### 3.1 Control flow

```
Brush = Actor->Brush
NotPolyFlags = (CsgOper==Add) ? 0 : (PF_NotSolid|PF_Semisolid = 0x28)
TempModel = GEditor->TempModel; TempModel->EmptyModel(1,1)
Orientation = Actor->BuildCoords(&Coords, &Uncoords)      // brush->world transform, §3.1a

LOOP 1 (transform, ALL operators):
  for each brush poly:
    copy it
    PolyFlags = (poly.PolyFlags | argPolyFlags) & ~NotPolyFlags
    set Actor / iBrushPoly / iLink
    FPoly::Transform(Coords, PrePivot, Location, Orientation)   // world-space transform, §3.1a
    snap Base onto the plane if |Normal·(Vertex[0]-Base)| > 1e-4
    accumulate into TempModel->Polys

if CsgOper in {Intersect, Deintersect}: branch to the two-phase tail, §3.6 — skip below.

LOOP 2 (grow world tree, Add/Subtract only):
  if Model.Nodes.Num == 0 and CsgOper == Add:
    // CONVEX-SEED SHORTCUT for the first brush into an empty world — §3.1b
  else:
    for each TempModel poly:
      seed/share iLink into a new-or-existing FBspSurf
      bspFilterFPoly(AddBrushToWorldFunc | SubtractBrushFromWorldFunc, Model, poly)
        // filters the brush's OWN faces DOWN the growing world tree, adding new nodes

if Model.Nodes.Num != 0 and !(PolyFlags & 0x28):
  bspBuild(TempModel, Opt=LAME(0), Balance=0, PortalBias=0, RebuildSimplePolys=0)
      // a PLAIN convex partition of the brush's OWN faces — no bevel/expansion planes
  TempModel->BuildBound()
  FilterWorldThroughBrush(Model, TempModel, CsgOper, iNode=0, &TempModel->Bound)
      // cuts EXISTING world faces against the brush's own temp BSP

bspCleanup(Model)     // UNCONDITIONALLY, per brush (not once at the end) — §3.5
```

**[DISASM; `re-raw-zones/bspbrushcsg-filter-decode.md` §1-2, `sections/82-bspbrushcsg-port-decode.md`
§1, `re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`]**.
`bspBuild`'s temp-brush call was initially disassembled as `PortalBias=1`; a later live-oracle
differential established the correct value is `PortalBias=0` **[DISASM, LIVE;
`sections/82-bspbrushcsg-port-decode.md:94-129,655-659`]**.

**No bevel/expansion planes exist anywhere in this pipeline** — a strong, explicitly-stated finding
from full disassembly of the filter half **[DISASM; `re-raw-zones/bspbrushcsg-filter-decode.md`,
`sections/82-bspbrushcsg-port-decode.md:28-50`]**. Watertightness is emergent from exactly two
mechanisms: (1) brush faces filtered down the world tree land as new nodes bounded by every ancestor
plane, and (2) world faces cut by the brush's own plain convex temp BSP (built only from the brush's
own face planes).

### 3.1a The brush → world transform — `ABrush::BuildCoords` / `FPoly::Transform`

**[DISASM Engine.dll 0x111390 (`BuildCoords`), 0x152360 (`FPoly::Transform`), core.dll helper RVAs]**

```
PointXform  = ((UnitCoords * PostScale) * Rotation) * MainScale
VectorXform = Transpose(UnitCoords / MainScale / Rotation / PostScale)   // inverse-transpose — covariant

FPoly::Transform:
  V' = (V - PrePivot).TransformVectorBy(PointXform) + Location
  N' = SafeNormalSlow(N_local.TransformVectorBy(VectorXform))
```
Normals and texture axes are mapped by the inverse-transpose of the vertex map, confirming texture
axes must be pre-cancelled by `(L⁻¹)ᵀ` — a covariant, not naive, transform.
`FCoords::operator*(FScale)` multiplies per-column by scale; `operator/(FScale)` divides per-axis via
`divss`; `TransformVectorBy` is three dot products against the frame's axes; `SafeNormalSlow` computes
`1/(f32)sqrt((f64)SquareSum)` — the same double-widened-magnitude normalize used throughout (§13).

**The composed matrix element for a diagonal-`PostScale`, identity-`MainScale` brush is
`M[i][k] = f32(f32(PostScale_i · R[i][k]) · MainScale_k)` — a two-stage f32 rounding, not one
double-precision matmul narrowed once.** Since every real DX rotate+scale brush has `MainScale =
identity`, the dominant real-world effect is that the editor stores `FVector Scale` itself as
float32, not double — e.g. on a cardinal 180° rotation the cross-term `R[0][1]=-sin(180°)=8.742278e-08`
(§13's trig-table artifact) combined with an f32-stored scale factor yields a specific 1-ULP-different
bit pattern from the double-precision-computed equivalent
**[DISASM, LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:1680-1687,1759-1768`]**.

### 3.1b Convex-seed construction for the first `Add` brush into an empty world

**[LIVE gdb, real UNATCO level, `oracle-105.log`]**: when the world tree is empty
(`Model.Nodes.Num==0`) and the incoming brush is `CSG_Add`, the real editor does **not** filter that
brush's polys one-by-one through a trivial empty tree via the ordinary LOOP-2 path. It instead
constructs the brush's own polys directly as a convex seed at the world-tree root: nodes 0-5 observed
with `parent=0, place=NODE_ROOT(3)` for the first node and `place=NODE_FRONT(1)` chaining the rest,
`iLink` 0-5, each face `Reverse()`d to face inward — bases/normals matching the brush's 6 authored
faces node-for-node. `Model.RootOutside` stays `0` (solid exterior) throughout; the editor does not
flip world polarity to accommodate a leading Add brush, it seeds the brush's faces structurally
instead **[LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:1186-1191,1276-1280`]**.

### 3.2 The filter recursion — `FilterEdPoly` / `FilterLeaf`

**[DISASM Editor.dll 0x32bf0 (`FilterEdPoly`), 0x33130 (`FilterLeaf`), 0x33b80 (`FBspNode::IsCsg`)]**

```
FilterEdPoly(node, EdPoly, outside):
  classify EdPoly against node's plane via SplitWithPlane(base, normal, VeryPrecise=false)  // ±0.25 band, §6.4
  SP_Front:    outside' = outside || IsCsg(node);  descend into node.iFront
  SP_Back:     outside' = outside && !IsCsg(node);  descend into node.iBack
  SP_Split:    recurse BOTH children with their respective split fragment + outside'
  SP_Coplanar: enter the coplanar cascade (§3.3) -> FilterLeaf
  if the target child index == -1: call FilterLeaf directly instead of recursing
  if EdPoly.NumVertices >= 14: SplitInHalf(EdPoly) first (a vertex-overflow guard, unrelated to §6.1's
    node-storage split at 16 verts)

IsCsg(node) = node.NumVertices>0 && !(node.NodeFlags & (NF_NotCsg|NF_IsNew /* = 0x21 */))
```

**Directly disassembly-confirmed: there is no dead-node (`NumVertices==0`) skip anywhere at the top
of `FilterEdPoly`** — a node's plane is read and split against unconditionally regardless of whether
the node is live; the only vertex-count gate in this function is the `>=14` split-in-half guard, which
is unrelated **[DISASM; `sections/82-bspbrushcsg-port-decode.md:749-757`]**.

### 3.3 The coplanar cascade — `EPolyNodeFilter` (the four/six-way classification)

**[DISASM Editor.dll 0x32d91, cross-checked live against a differential build]**

`FCoplanarInfo` fields: `iOriginalNode, iBackNode, FrontLeafOutside, BackNodeOutside, ProcessingBack`.
On the first coplanar hit in a descent:
```
Dot = Node.Normal · EdPoly.Normal
Dot >= 0:  descend node.iFront first (facing side, seed = outside||IsCsg); defer node.iBack (seed = outside&&!IsCsg)
Dot <  0:  descend node.iBack  first (facing side, seed = outside&&!IsCsg); defer node.iFront (seed = outside||IsCsg)
```
The facing side's result → `frontOutside`; the deferred side's independent result → `backOutside`.
Final classification from the pair:

| (frontOutside, backOutside) | value | name |
|---|---|---|
| (in, in) | 3 | F_COPLANAR_INSIDE |
| (out, out) | 2 | F_COPLANAR_OUTSIDE |
| (out, in) | 5 (see discrepancy note) | F_COSPATIAL_FACING_OUT |
| (in, out) | 4 (see discrepancy note) | F_COSPATIAL_FACING_IN |

This seeding/dispatch mechanism is cross-checked against a live N=2-brush castle differential trace
(15→14 nodes matching the editor) and against a full-castle build (1158 native-decoded vs 1156 editor
nodes) **[DISASM, LIVE; `sections/82-bspbrushcsg-port-decode.md` §7b]**.

**[OPEN — direct citation conflict between two evidence documents on the last two labels.]** One
decode (`re-raw-zones/bspbrushcsg-filter-decode.md` §3, its `FilterLeaf@0x33130` final table) assigns
`(out,in)→4 FACING_IN, (in,out)→5 FACING_OUT`; the other (`sections/82-bspbrushcsg-port-decode.md`
§4.2) assigns them the other way round: `(out,in)→5, (in,out)→4`. Both are cited to disassembly by
their own document. The former document contains a longer, later-dated correction log and a
live-verified differential trace tied to these exact field roles, so it is treated as the
higher-confidence value in the table above — **but this is not independently re-resolved here**, and
a reimplementer relying on the exact numeric filter values (rather than their behavioral meaning, which
both documents agree on) should re-verify against the binary directly before depending on it.

A **second** coplanar hit while already inside a coplanar cascade triggers an `appFailAssert`
(treated as front) **[DISASM Editor.dll 0x32d97]**.

### 3.4 Per-operator face-survival rules

Two independent filter passes exist per Add/Subtract brush, each dispatched through leaf-callback
functions selected by the brush's `CsgOper` **[DISASM; `re-raw-zones/bspbrushcsg-filter-decode.md` §2,
`sections/82-bspbrushcsg-port-decode.md` §3]**:

**Pass 1 — LOOP 2, brush poly filtered down world tree, ADDS new world nodes:**

| CsgOper | callback | adds a node on filter value(s) | reverses winding? |
|---|---|---|---|
| Add | `AddBrushToWorldFunc` [0x31770] | `F_OUTSIDE(0)`, `F_COPLANAR_OUTSIDE(2)`, and the "facing-out" cospatial case gated `!PF_Semisolid` | no |
| Subtract | `SubtractBrushFromWorldFunc` [0x348c0] | `F_INSIDE(1)`, `F_COPLANAR_INSIDE(3)` only — **not a mirror of Add**, no cospatial case, no semisolid gate | **yes** — `FPoly::Reverse()` wraps the `bspAddNode` call only; the plane used for descent/classification stays the brush's original outward-facing normal |

Both call `bspAddNode(Model, iNode, ENodePlace, NF_IsNew, EdPoly)`.

**Pass 2 — `FilterWorldThroughBrush` (FWTB), existing world face filtered down the brush's own temp
BSP, cuts/deletes/re-adds world faces:**

| filter value | Add re-adds? | Subtract re-adds? |
|---|---|---|
| 0 OUTSIDE | yes | yes |
| 1 INSIDE | no (discard) | no (discard) |
| 2 COPLANAR_OUTSIDE | yes | yes |
| 3 COPLANAR_INSIDE | no (discard) | no (discard) |
| 4 COSPATIAL_FACING_IN | no (discard) | **yes** |
| 5 COSPATIAL_FACING_OUT | no (discard) | no (discard) |

(Subject to the §3.3 numbering caveat for which physical case is labeled 4 vs 5 — the table above uses
the higher-confidence source's labeling.)

Mechanism: a world node not freshly added this pass is reconstructed as an `FPoly` (keeping its
original surf link) and filtered down the brush's own convex temp BSP. **Re-add fires only when the
fragment's `PolyFlags` bit 31 is set** — `FPoly::SplitWithPlane` sets this bit on both output halves
**only on a genuine `SP_Split`** (never on a plain Front/Back/Coplanar return)
**[DISASM Engine.dll 0x1518b0 @0x151ad9/0x151b09]**. A re-added fragment becomes a `NODE_Plane` node
chained onto the tail of the original node's coplanar chain, sharing the original surf.

**Post-filter reconciliation** **[DISASM Editor.dll 0x3348b]**: a global discard counter (`GDiscarded`,
reset per straddling node at `0x3343f`, incremented on each discard-path leaf hit at `0x349ee`) tracks
whether anything actually landed interior this pass. If **`GDiscarded != 0`** (the face genuinely
enters the brush), the original node is marked dead (`NumVertices=0`, `Nodes.Remove` at `0x34050`
deletes the original) and the re-added outside fragments are kept. If **`GDiscarded == 0`** (the face
only grazed the brush — every fragment landed outside), the re-added duplicate fragments are **rolled
back** (removed) and the original face is kept whole, unmodified. This exact reconciliation rule was
independently re-derived and cross-checked a second time from the same instructions, confirming it
**[DISASM; `sections/92-bspbrushcsg-reallevel-port-plan.md:1537-1541`]**.

### 3.5 `bspCleanup` / `CleanupNodes` — the per-brush dead-node splice

**[DISASM Editor.dll 0x36160 (driver), 0x32100 (`CleanupNodes` worker)]**. Runs at the tail of
**every** Add/Subtract `bspBrushCSG` call, not once at the very end of the whole rebuild. Recurses
`iFront`/`iBack`/`iPlane` children first (clearing transient flag bits on each), then on the way back
up, for each dead node (`NumVertices==0`):

- **Has an `iPlane` (coplanar-chain) successor `P`:** promote `P` into the dead node's slot in the
  tree. `P` inherits the dead node's `iFront`/`iBack` children — **swapped iff `Dot(deadNode.Normal,
  P.Normal) < 0`** (opposite-facing normals; exact `0.0` threshold, `FPlane::operator|`). The parent's
  link to the dead node is repointed to `P`. At the tree root, `P` is copied wholesale into the root
  slot and marked dead itself.
- **No `iPlane` successor:** if the dead node still has both children, it stays as a pure splitter
  with no polygon; otherwise the parent is repointed straight past it to its one surviving child (or
  `-1`).

Dead nodes are **never removed from the node array** — indices stay stable; a dead node becomes
unreachable garbage in the array, not a hole. This splice is load-bearing for byte-parity: it is what
makes the *next* brush's descent see the correct tree shape rather than a dead chain-head that would
flip a splitter's effective front/back order **[DISASM; `sections/82-bspbrushcsg-port-decode.md` §8]**.

### 3.6 Intersect / Deintersect — a distinct two-phase algorithm

**[DISASM Editor.dll 0x35ab3 onward]**. Neither operator grows the world tree; instead the **builder
brush itself** is refilled with the result (`Actor->Brush->Brush->EmptyModel(1,1)`).

- **Phase 1:** each transformed builder-brush face (from the shared LOOP 1, with solidity bits
  stripped by the same `0x28` mask) is filtered **down the world tree**, via one of two leaf
  callbacks selected by `CsgOper`: `IntersectLeaf_P1` keeps `{F_INSIDE(1), F_COPLANAR_INSIDE(3)}`;
  `DeintersectLeaf_P1` keeps `{F_OUTSIDE(0), F_COPLANAR_OUTSIDE(2)}` — exact complements. No winding
  reversal in this phase.
- **Phase 2** (only if `Model.Nodes.Num != 0` — degrades to Phase-1-only on an unbuilt world): build
  the builder's own convex temp BSP (same LAME/Balance=0/PortalBias=0 parameters as §3.1), then
  `FilterWorldThroughBrush` clips each straddling **world** face down into the builder's hull:
  `IntersectLeaf_P2` keeps `{1, 3, 5=F_COSPATIAL_FACING_OUT}`, no reverse; `DeintersectLeaf_P2` keeps
  `{1, 3, 4=F_COSPATIAL_FACING_IN}` **and reverses** kept fragments before appending. Both share a
  common tail: a fragment survives only if `Fix()` leaves it with `>= 3` vertices.
- Phase-2 fragments ("caps") inherit the surrounding **world surface's** texture and `PolyFlags`
  (masked `& 0x3cffffff`).
- **Finalize:** result polys are transformed back into builder-local space via the brush's own
  `BuildCoords`, `Fix()`ed, and stripped of their world-side `Actor`/`iBrushPoly` references.

**[DISASM; `re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`]**.

### 3.7 Normal computation and storage — decoded, live-gdb-confirmed

This is the most heavily re-verified mechanism in the whole evidence base — settled by breakpointing
the actual running editor during a real `MAP REBUILD` and a real `EDIT PASTE`, not by disassembly
alone.

**`FPoly::CalcNormal` is called ZERO times during `MAP REBUILD`** — live-verified with an
unconditional breakpoint on a real UNATCO rebuild (5878 `bspAddNode` calls captured, 0 `CalcNormal`
calls) **[LIVE gdb; `sections/92-bspbrushcsg-reallevel-port-plan.md:2100-2101`]**. Stored face normals
are therefore **carried through world CSG unchanged** — they are fixed earlier, at brush-model
construction time (paste/import), not recomputed during the geometry rebuild itself.

**The storage rule at brush-construction time is gated on CSG operation**, confirmed against real
level content **[LIVE gdb + real-file cross-check;
`sections/92-bspbrushcsg-reallevel-port-plan.md:1938-1943`]**:
- **`CSG_Add` brush:** the stored world-space normal is the **authored T3D `Normal=` value verbatim**
  — `CalcNormal`'s local-winding recomputation is performed but its result is discarded. Verified: all
  80 slanted 45° faces of a real castle-level Add brush retain their exact authored normal bit-for-bit.
- **`CSG_Subtract` brush (non-mirrored, pure rotation):** the stored normal is instead
  `SafeNormalSlow(Rotate(CalcNormal(local_winding)))` — recomputed from local winding, then rotated,
  then renormalized. Verified: all slanted subtract-brush faces on a real dome and several real UNATCO
  wedge brushes carry this rotated/renormalized value, not the authored one.
- **`FPoly::Transform` applies a SECOND `SafeNormalSlow`** on top of whatever `CalcNormal` already
  produced — since `CalcNormal`'s own output magnitude isn't bit-exactly `1.0`, this second
  renormalization measurably shifts the final stored bits by 1-2 ULP from the raw `CalcNormal` output.
  Confirmed by exact-bit match against 19/19 non-axis-aligned real dome-brush normals extracted from a
  real editor-built `.dx` package, reproduced by `calc_normal` + f32-dot/f64-sqrt renormalize.
- **Axis-face exception:** `CalcNormal` of a large non-square axis-aligned rectangle (doubled area
  `> 2^24`) loses precision in its reciprocal-square-root step and rounds to `0.99999994` (1 ULP under
  unit) — yet the real editor's stored value for such faces is the exact `±1.0`. A pinned numerical
  artifact independent of the Add/Subtract question.
- **One case is honestly left unresolved by the source material rather than forced**: a coincident
  Add/Subtract shared-surface pair (2 faces) where neither the authored value nor either normalize
  variant reproduces the real stored bits — attributed to an order-dependent surface-ownership
  decision the evidence does not claim to have decoded.

**Live-verified paste-time input fidelity**: during a real `EDIT PASTE` of a real dome brush, all 78
`CalcNormal` calls captured via breakpoint received vertex inputs 100% bit-identical to the authored
T3D vertices, in identical winding order (no cyclic rotation, no reversal) — ruling out any vertex-pool
perturbation at paste time. The per-facet `CalcNormal` output itself (breakpointed right after
`NormalizeSlow` returns, at Engine.dll `0x150620` — an earlier attempted breakpoint site was on a
degenerate-case branch skipped by every valid face) is bit-for-bit identical, for all 78 faces of the
real dome, to a from-scratch offline recomputation over the brush's local pre-transform winding —
confirming `CalcNormal`'s arithmetic is exactly, deterministically reproducible offline
**[LIVE gdb; `sections/92-bspbrushcsg-reallevel-port-plan.md:2024-2119`]**.

`bspNodeToFPoly` **[DISASM Editor.dll 0x365b0]** simply preserves whichever normal ended up stored on
the surf when reading a node back out — it never recomputes at read time either.

### 3.8 Watertightness validation

Covered in §3.0 (`bspValidateBrush`) — a genuine per-brush pre-CSG pass, not part of `bspBrushCSG`'s
own filter logic. `bspBrushCSG`'s filter recursion itself (§3.2-3.5) contains no separate
watertightness check of its own; watertightness of the *tree* is an emergent property of the two-pass
filter.

### 3.9 Constants and thresholds (all read from `.rdata`, address-cited)

| Constant | Value | Where | Effect |
|---|---|---|---|
| `THRESH_SPLIT_POLY_WITH_PLANE` | 0.25 | Engine `0x206780` | ordinary front/back/split/coplanar classify band (§6.4) |
| `THRESH_SPLIT_POLY_PRECISELY` | 0.01 | Engine `0x1fee1c` | the "very precise" classify band (used elsewhere, e.g. portal filtering, §8.2) |
| `SMALL_NUMBER` (size²) | 1e-8 | Core `0xa0a40` | `NormalizeSlow` zero-length floor (~1e-4 uu length) |
| colinear/coincident vertex collapse | ~1e-4 (`9.999999e-05`) | immediate `0x38d1b717` | `RemoveColinears` drop threshold |
| `THRESH_POINTS_ARE_SAME` | 0.002 | Engine + Editor | per-axis box test, not Euclidean — strict `<` on each of dx/dy/dz independently |
| `THRESH_POINTS_ARE_NEAR` | 0.015 | Engine + Editor | near-point tests |
| `THRESH_NORMALS_ARE_SAME` | 2e-5 | Editor | `bspMergeCoplanars` coplanar-group test (§7.2) |
| `THRESH_VECTORS_ARE_NEAR` | 0.0004 | Editor | texture-vector near-equality (`TryToMerge`, §7.2) |
| `THRESH_VECTORS_ARE_PARALLEL` | 0.02 | Engine + Editor | parallelism tests |
| Base-plane snap | 0.0001 | Editor `0x100dcb18` | LOOP-1 base-vertex correction onto the poly's own plane |
| `bspMergeCoplanars` normal-match | 0.9999 (dot) | Editor | coplanar-group normal-equality test |
| `PF_NotSolid` | 0x08 | | |
| `PF_Semisolid` | 0x20 | | |
| `PF_Portal` | 0x04000000 | | |
| `PF_Invisible` | 0x01 | renders no, collides yes | |
| `PF_TwoSided` | 0x100 | | |
| `NF_NotCsg` | 0x01 (NodeFlags) | | |
| `NF_IsNew` | 0x20 (NodeFlags) | | |
| Surf `PolyFlags` storage mask | `& 0x3cffffff` | Editor `0x34fa9` | applied when a surf's flags are written |

**[DISASM; `dev/docs/spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` §4d,
`re-raw-zones/bspbrushcsg-filter-decode.md` §4, `dev/docs/spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` §2]**

### 3.10 Point and vector pool management — `bspAddPoint` / `bspAddVector`

Every world vertex and every stored normal/texture-axis is deduplicated against the model's shared
`Points`/`Vectors` pools rather than appended unconditionally — this determines the pool **indices**
a from-scratch implementation must reproduce, independent of getting the CSG/partition algorithms
themselves right.

**`bspAddPoint`** **[DISASM Editor.dll 0x35430, calling Engine.dll `UModel::FindNearestVertex`
0x1adeb0 → recursive descent 0x1adb60]**:
```
dist = FindNearestVertex(Model, pt, thresh, &out_idx)   // -1.0 sentinel if the model is empty
if dist < 0 or dist > thresh:
    idx = Points.AddItem(pt)      // no match within threshold -> append fresh
else:
    idx = out_idx                 // reuse the existing point
```
`thresh = 0.002` (worldspace call site) or `0.015` (local-space call site) — the same two constants
as `THRESH_POINTS_ARE_SAME`/`THRESH_POINTS_ARE_NEAR` used elsewhere (§3.9).

`FindNearestVertex` descends the BSP tree by `PlaneDot` sign (the same tree the point is being added
into, already partially built) rather than a linear scan. **Descent pruning uses squared distance**
(`dx²+dy²+dz²`, no sqrt — cheap). On the single winning candidate, the **accept test uses a real
distance**: `appSqrt` (`core.dll 0x31720`, `sqrtsd` f64→f32) is applied to the winning squared
distance, and *that* real value is compared against the threshold — **not** a squared-vs-squared
compare. A faithful port must take the sqrt before thresholding, not skip it as a "same result,
cheaper" optimization — it changes which candidate passes right at the threshold boundary. All SSE,
no x87, no rsqrt approximation (same discipline as §11's other findings).

**Critically, this returns the *nearest* existing point within threshold, not the *first* found** —
so the dedup outcome is unambiguous and does not depend on descent/scan order, only on what points
already exist in the pool at the moment each new point is proposed. **The Points/Vectors pool's final
index ORDER is therefore a pure function of the order in which points get *proposed* for insertion**
— which is itself a downstream consequence of the exact node-emission order documented in §3-§5.
Getting `FindNearestVertex`'s own rule right is necessary but not sufficient for a matching pool: the
proposing order (every upstream CSG/split/repartition step, in the exact order the real editor
performs them) has to match too, or the *same* correct dedup rule accepts/rejects different points
and the pools diverge — see §20 for what this looks like when actually attempted.

**`bspAddVector`** **[DISASM Editor.dll 0x35530, helper 0x31ae0]** — the same shape, for normals and
texture axes, at thresholds `2e-05`/`4e-04` (matching `THRESH_NORMALS_ARE_SAME`/
`THRESH_VECTORS_ARE_NEAR`).

Both `bspAddNode`, `bspAddPoint`, and `bspAddVector` append to their respective arrays purely in
tree-walk/proposal order — no hash-map iteration, no RNG, no address-dependent ordering anywhere in
this mechanism.

---

## 4. `FPoly::Finalize` / `Fix` / `RemoveColinears` / `CalcNormal` — the face-survival gate

Every world face passes through `FPoly::Finalize` **[DISASM Engine.dll 0x150ac0]**. This is the gate
where a face can vanish outright ("a hole"):

1. Calls `FPoly::Fix` **[0x150da0]** — collapses near-duplicate vertices (below).
2. **If `NumVertices < 3` → reject.** Logs `"FPoly::Finalize: Not enough vertices (%i)"` (a warning,
   or `appErrorf`/Critical Error if `!NoError`) and returns `-1` — the face does not exist in the world.
3. If `Normal` is all-zero, calls `CalcNormal` **[0x150510]**.
4. **If `CalcNormal` reports zero area → reject.** Logs
   `"FPoly::Finalize: Normalization failed, verts=%i, size=%f"` and returns `-1`.

Note this is consistent with §3.7's live finding: `CalcNormal` here is only reached when `Normal` is
already all-zero going in — it is not an unconditional recompute, matching the observation that a
real `MAP REBUILD` triggers zero `CalcNormal` calls (stored normals are already non-zero by then).

**`RemoveColinears`** **[DISASM Engine.dll 0x151090]** runs two passes over the vertex ring:
- **Pass 1 — coincident vertices.** For each vertex, `Side = V[i]-V[i-1]` crossed with the poly
  Normal, tested via `NormalizeSlow` (fails when squared length `< 1e-8`, i.e. length `< ~1e-4 uu`) —
  consecutive vertices closer than ~1e-4 uu collapse to one.
- **Pass 2 — colinear vertices.** Adjacent side-plane normals compared component-wise, threshold
  `9.999999e-05` — a vertex on a straight edge (parallel neighboring edges) is redundant and removed.
- **After either pass, if `NumVertices < 3`: sets `NumVertices=0`, caller discards the poly.**

**`CalcNormal`** **[DISASM Engine.dll 0x150510]** accumulates a triangle-fan normal (`Σ (V[i-1]-V[0]) ×
(V[i]-V[0])` for `i=2..N`, twice the area-weighted normal, pivoted at vertex 0 — confirmed bit-identical
in op-order against an independent from-scratch reimplementation, §3.7), then `NormalizeSlow`
(magnitude via `(f32)sqrt((f64)mag2)` — sum-of-squares in f32, the square root itself in double then
narrowed, not a direct f32 `sqrtss`). If the summed normal's squared length `< 1e-8`, the polygon is
effectively zero-area: logs `"FPoly::CalcNormal: Zero-area polygon"`, reports degenerate. A sliver
fragment from a near-miss split fails here and is dropped.

**`bspMergeCoplanars`'s second collapse point** (§7.2): even a face that survives initial CSG can be
collapsed later if merging two coplanar polys produces vertices that thin below 3 after
`RemoveColinears` runs again on the merged result.

**[DISASM; `dev/docs/spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` §4,
`sections/92-bspbrushcsg-reallevel-port-plan.md:631-637`]**

---

## 5. `SplitPolyList` / `bspBuild` — tree partition

### 5.1 Recursion structure

**[DISASM Editor.dll 0x34530]**. Signature: `SplitPolyList(Model, iParent, ENodePlace, NumPolys,
PolyList, Opt, BalancePacked, RebuildSimplePolys)`.

```
allocate FrontList/BackList scratch
Split = FindBestSplit(NumPolys, PolyList, Opt, BalancePacked)      // §5.2, the heuristic
if RebuildSimplePolys: Split.iLink = Model.Surfs.Num
iNode = bspAddNode(Model, iParent, ENodePlace, 0, Split)           // exactly ONE node for the splitter
iPlane = iNode
for each other poly P in PolyList (P != Split):
  classify = P.SplitWithPlane(Split.Base, Split.Normal, &Front, &Back, VeryPrecise=false)
  case Coplanar:
    if RebuildSimplePolys: P.iLink = Surfs.Num - 1
    iPlane = bspAddNode(Model, iPlane, NODE_Plane, 0, P)   // chains onto the PREVIOUS coplanar node,
                                                            // via the running iPlane cursor — a linked
                                                            // list of single-poly NODE_Plane nodes,
                                                            // NOT folded into the splitter's own poly
  case Front: append P to FrontList
  case Back:  append P to BackList
  case Split: append Front/Back fragments to their lists;
              if either fragment.NumVertices >= 14: SplitInHalf(fragment) BEFORE it's added to the list
if FrontList non-empty: SplitPolyList(Model, iNode, NODE_Front, ..., FrontList, ...)  // FRONT recursed first
if BackList  non-empty: SplitPolyList(Model, iNode, NODE_Back,  ..., BackList,  ...)  // BACK second
```

Recursion order (front child first, back child second) and the strict-`<` tie-break in `FindBestSplit`
are independently confirmed a second time by a separate decode pass, cross-checked against castle
byte-identity **[DISASM; `sections/92-bspbrushcsg-reallevel-port-plan.md:1382-1385`]**. The same
independent pass also pins a previously-undocumented detail: **the repartition's `Split` arm
additionally forces `SplitInHalf` on any fragment reaching `>=14` vertices** (same threshold and
mechanism as the CSG-filter passes' own vertex-overflow guard, §3.2) — i.e. this guard applies during
final-tree repartition too, not only during per-brush CSG filtering
**[DISASM; same doc, `:1401-1407`]**.

**The load-bearing node-count rule:** *the only `bspAddNode` calls in this whole recursion are the
splitter itself (exactly one) and one per exactly-coplanar input poly (chained via `iPlane`)* — an
empty Front or Back list simply ends that branch of the recursion; **no leaf node, no bound node, no
bevel-plane node is ever emitted.** `#nodes = #input FPolys + #polys actually split into fragments`.
This directly disproves a "leaf-bounding pass" hypothesis: `bspBuild`'s own tail after the top-level
`SplitPolyList` call is only `bspRefresh` + `bspBuildBounds` (§7.1, §9) — no node-tree-expanding pass
exists anywhere in `bspBuild` **[DISASM; `re-raw-zones/bspbuild-splitpolylist-decode.md`,
`sections/80-bspbuild-topology.md`]**.

`bspAddNode` **[DISASM Editor.dll 0x34e80]** separately performs a **>16-vertex storage split**
distinct from the above (an `FBspNode`'s vertex-count field is one byte, capping storage at 16): a
17+-vertex poly is split into a 16-vertex node and an `N-14`-vertex node sharing 2 vertices, itself
recursing through `bspAddNode`.

### 5.2 `FindBestSplit` — the exact scoring heuristic

**[DISASM Editor.dll 0x335d0]**, fully byte-verified with a committed re-assertable harness
(24/24 checks pass against the actual UED22 DLLs)
**[`dev/docs/spikes/2026-06-26-bsp-partition-heuristic-from-binary.md`]**.

Signature: `FindBestSplit(NumPolys, PolyList, Optimization, BalancePortal)`.
`Balance = BalancePortal & 0xFF` (int 0-100); `PortalBias = ((BalancePortal>>8) & 0xFF) / 100.0` (float).

**Candidate stride `Inc`, by `Optimization`:**
- `OPTIMAL (2)` → `Inc = 1` — try every poly, exact.
- `GOOD (1)` → `Inc = NumPolys / 10` (signed division via the `0x66666667` magic-multiply idiom).
- `LAME (0)` → `Inc = NumPolys / 4`.
- Floored at 1.

**The candidate loop is NOT a plain `range(0, num, inc)`.** It processes consecutive *slots*
`k=0,1,2,…`; slot `k` spans indices `[k·inc, (k+1)·inc)`, and the candidate actually used is the
**first eligible** poly in that window (skipping a structural-non-portal poly, scanning forward within
the same window; a fully-structural window yields no candidate that round) — for `inc=1` (OPTIMAL)
this reduces to "every eligible poly"; for GOOD/LAME a naive strided loop picks the wrong subsample
positions **[DISASM; `dev/docs/spikes/2026-06-26-bsp-partition-heuristic-from-binary.md` §2d, fuzz-verified
200,000 random configs against an instruction-level simulator, 0 mismatches]**.

**Structural-splitter candidate skip:** a pre-pass finds whether any poly in `PolyList` lacks the
`0x28` (semisolid|notsolid) mask — sets `all_structural = true` iff none do. Per candidate: if the
poly has the `0x28` mask and is not `PF_Portal` and not `all_structural`, it is skipped as a candidate
(scan continues within the window); otherwise (non-structural, or a portal, or everything is
structural) it's eligible.

**The classification inner loop steps by the SAME `Inc`** — GOOD/LAME score against a subsample of the
other polys too; only OPTIMAL is exact. **Real-world consequence of this, live-measured on the actual
734-brush UNATCO map's CSG-root poly soup** (`NumPolys=2449`, `stride=122` under GOOD): the sparse
sample scores a horizontal-splitter candidate *worse* (score 100) than a slanted-wall candidate (score
24), while a full stride-1 scan of the identical soup inverts the ranking (horizontal split scores
2676, "4.6× better") — a genuine, observed failure mode of `GOOD` mode's sampling on real content, not
a hypothetical **[LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:749-755`]**.

**The score, in float32 SSE arithmetic, exact operation order** **[DISASM, byte-verified instruction
sequence]**:
```
Splits += (poly is a portal) ? 16 : 1     // for each SP_Split result in the classify loop
Score2 = f32((100.0 - Balance) * f32(Splits))          // computed FIRST
Score  = f32(f32(Balance) * f32(abs(Front - Back))) + Score2   // Score2 added LAST — order matters for f32 rounding
if candidate.IsPortal():
    Score = Score - f32(Score2 * PortalBias)             // subtracted last
```
**Tie-break: strict `<` — the earliest (lowest-index) candidate wins a tie.** Fully deterministic, no
RNG, no hidden state. If no candidate is ever selected the real engine `appErrorf`s
(`UnBsp.cpp:476`) rather than silently falling back.

The candidate's splitting plane is built from the poly's **stored** `Normal` + base vertex (an
`FPlane(base, normal)` construction), not recomputed from winding — a faithful port must classify
against the stored plane, which can differ from a winding-recomputed plane for a poly whose stored
normal disagrees with its winding.

### 5.3 Three distinct `bspBuild` call sites — do not conflate their parameters

Three separate, independently decoded call sites push different `(Balance, PortalBias, Optimization)`
tuples into the shared `FindBestSplit`/`SplitPolyList` machinery:

1. **Temp-brush convex partition** inside `bspBrushCSG` (§3.1): `Opt=LAME(0), Balance=0,
   PortalBias=0` — a plain split-minimizing partition of one brush's own faces, fixed, not
   user-configurable **[DISASM; `sections/82-bspbrushcsg-port-decode.md:94-129,655-659`]**.
2. **World repartition**, reached via `csgRebuild → bspRepartition [Editor.dll 0x49fc0] → bspBuild`:
   `bspRepartition` pushes **hardcoded literal immediates** `BalancePacked=0xc` (`Balance=12,
   PortalBias=0`), `Opt=1 (GOOD)` **directly in its own machine code** — not read from any argument,
   not threaded from console input **[DISASM Editor.dll 0x1004a02f/0x1004a031;
   `re-raw-zones/findbestsplit-params-decode.md:6-34`]**. **Independently re-confirmed by a second,
   separately-dated decode pass**, which additionally spells out the resulting score formula
   (`Score = 12·|F−B| + 88·Splits`, `PortalBias=0`) and its GOOD-mode stride
   (`NumPolys/20` via the compiler's `imul 0x66666667; sar 3` idiom), reporting byte-exact agreement
   against a real 95-brush castle level (1156/1156 node match)
   **[DISASM, LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:744-747`]**. Empirically, re-running
   a faithful `SplitPolyList`+`FindBestSplit` on the editor's own reconstructed repartition poly soup
   with `Balance=12/GOOD` reproduces the editor's golden node-for-node at small N, while `Balance=50`
   (the console default) and `Balance=15` ("classic Unreal" folklore) both fail to match
   **[LIVE differential; `re-raw-zones/findbestsplit-params-decode.md:91-98`]**.
3. **`BSP REBUILD`/`MAP REBUILD` console exec-parser defaults** (§1.2): `Balance=50, PortalBias=70,
   Optimization=OPTIMAL` when no keyword is given, byte-verified from the parser at `Editor.dll
   0x65220` itself. **[OPEN]** — whether/how these parsed values reach the actual world-repartition
   `FindBestSplit` call (item 2, whose own immediates are hardcoded and twice-confirmed) is not
   directly A/B-tested by any evidence gathered. Given item 2's strength (two independent decodes,
   byte-exact against a real castle build), it is likely the console-parsed values are dead/vestigial
   for the world-repartition call specifically and only affect something else (or nothing) — but this
   remains formally open pending a direct test: build the same brush set via
   `BSP REBUILD BALANCE=12 ...` vs `BSP REBUILD BALANCE=90 ...` and diff the resulting node trees.

### 5.4 `FPoly::SplitWithPlane` / `SplitWithPlaneFast` — the poly-splitting geometry

**[DISASM Engine.dll 0x1518b0 (`SplitWithPlane`), 0x151f90 (`SplitWithPlaneFast`)]**

Threshold `T` = `0.25` (normal) or `0.01` (`VeryPrecise=true`). Per vertex, signed distance
`d = (V[i]-Base)·Normal`; classify `d>+T` front / `d<-T` back / `-T<=d<=+T` "on" the plane. Whole-poly
decision: `maxd<+T && mind>-T` → **coplanar**; all front → **front**; all back → **back**; else
**split**.

**`SplitWithPlaneFast`** (the classify-only variant `FindBestSplit` uses) is confirmed to use the
*same* `±0.25` band, not a separate threshold — a forced `0.01`-band test on a real corpus fixed one
merge case but symmetrically broke a mirror-image case at the same grid-snap gap, proving one
threshold serves both roles **[LIVE-probed negative test; `sections/82-bspbrushcsg-port-decode.md`
§10.6]**. Per-vertex: front branch sets a `has_front` flag only if `d > +0.25` (not merely `d>0`);
back branch sets `has_back` only if `d < -0.25`. Return: `(no,no)→Coplanar(0)`, `(no,yes)→Back(2)`,
`(yes,no)→Front(1)`, `(yes,yes)→Split(3)`. **The vertex SIDE used for the actual split geometry is the
strict `d<0→back, else front` from the raw sign** — the `±0.25` band only gates the
front/back/coplanar *decision*, not where cut vertices are interpolated
**[DISASM; `dev/docs/spikes/2026-06-26-bsp-partition-heuristic-from-binary.md` §3]**.

**Split-fragment interpolation**: at a front/back crossing between consecutive ring vertices, the cut
point is `P = A + t·(B-A)` where `t` comes from the signed distances of `A`,`B` — computed via a
single `divss` (IEEE-correct float32 division), bit-identical to a native `f32/f32` in any language
with correct IEEE semantics **[DISASM Engine.dll 0x150780; `re-raw-zones/fp-classification-sites.md`]**.

---

## 6. Post-build cleanup and optimization

### 6.1 `bspRefresh` — array GC

**[DISASM Editor.dll 0x36cd0]**. Drops unreferenced surfs, renumbers `node.iSurf` accordingly, and
re-packs the vertex pool contiguously per node in build order. Does not touch Points or Vectors.

### 6.2 `bspMergeCoplanars` / `FPoly::TryToMerge`

**[DISASM Editor.dll 0x36200 (`bspMergeCoplanars`), 0x34b10 (`TryToMerge`, note: Editor.dll, not
Engine.dll)]**. Groups CSG world fragments by predicate: same `iLink` (same source brush face, seeded
by `bspValidateBrush`, §3.0), plane offset agreement `|Normal·(OtherBase-Base)| < 0.001`, normal
agreement `Normal·OtherNormal > 0.9999`, and matching texture UV within `4e-4` (unless
`MergeDisparateTextures` is set). Each group of size > 1 is fixpoint-merged pairwise via
`MergeCoplanarPolys`, then the array is compacted by dropping zero-vertex entries — compaction walks
in **original index order**, it does not cluster a merged group at its head.

`TryToMerge`: vertex cap `NV1+NV2 > 16 → fail`; finds the first shared point in row-major
`(i over Poly1, j over Poly2)` order via the `THRESH_POINTS_ARE_SAME` box test; tests the forward
neighbor for a shared edge, else the backward neighbor; builds the merged ring as all of Poly1
(rotated to the shared edge) then Poly2's vertices minus the two shared ones; runs `RemoveColinears`;
fails if the result collapses below 3 vertices or exceeds 16.

`bspMergeCoplanars` re-running `RemoveColinears` on the merged result means a face that survived
initial CSG can still be collapsed during this pass if the merge produces near-colinear vertices.

**[DISASM; `sections/82-bspbrushcsg-port-decode.md` §7,§9-10]**

### 6.3 `bspOptGeom`

**[DISASM Editor.dll 0x36870]**, validated byte-exact against a real editor-written `Test_Castle.dx`
**[BYTE-DIFF; `42-bspoptgeom-decode.md`]**. Three sub-passes, in order, mutating the `UModel` in place:

**Prologue:** `debugf("BspOptGeom begin")`; a point-merge call `[0x33dc0](Model, 0.25f)` (merges
near-coincident world points within 0.25 uu — empirically a no-op on the golden castle, closest live
point pair 0.76 uu apart); `bspRefresh(Model,0)`; `NumSharedSides` seeded to 4; all `Verts[k].iSide`
initialized to -1. A per-point vertex-occurrence table is built, prepending records in **descending**
`(node, ringpos)` order — explicitly load-bearing for pass 1's first-match semantics.

**Pass 1 — T-junction elimination** **[DISASM 0x36939]**: for every node-ring edge not already shared
with another node, recursively descends the BSP for both edge endpoints (`AddPointLink [0x325e0]`),
using the same `±0.25` plane-band descent as CSG classification, and at each node in the reached
coplanar chain runs a per-node ring scan testing whether the point lies interior to one of that node's
polygon edges.

The ring-scan test **[DISASM 0x326fc-0x32977, corrected 2026-07-18]** is a **cross-product
perpendicular-distance test**, not an along-edge projection (an earlier decode pass had this wrong —
fixing it moved a measured weld count from 22 to 1012 out of the editor's 975 golden welds): for edge
`E = P[cur]-P[prev]`, compute `C = E × N` (edge crossed with node normal), then
`proj = (C·(point-P[cur]))/|C|` — a signed perpendicular distance from the edge line (f32 dot,
f64 `sqrt` for the magnitude). Degenerate guard `|C|² <= 1e-6`; accept band `-0.25 < proj < 0.25`; a
`proj >= 0.25` on any edge aborts the whole node (convex-boundary exit, no further edges checked); an
on-line accept is further bounded to the actual segment by a midpoint-capsule check
(`|E|² * 0.251001 < |point-midpoint|²`, all in f64). **The last matching edge in a full scan wins**
(no early break on the first accept).

The inserter allocates `NumVertices+1` **fresh slots at the end of the `Verts` pool** and splices the
new vertex in — **old ring slots are orphaned, never compacted** (no `bspRefresh` runs after
`bspOptGeom`, only once at its own prologue). This append-and-orphan behavior is the mechanism behind
a large Verts-pool inflation on real content (measured: 16,163 total verts vs 5,496 actually live/
referenced on the castle golden — 10,667 orphans) **[BYTE-DIFF]**. After pass 1, the occurrence table
is torn down and rebuilt over the now-split rings. **The dup-guard table must be updated live** (after
every weld, not built once up front) — a static pre-pass-1 table over-welds by a measurable amount
relative to the editor's own incremental self-avoidance.

**Pass 2 — shared-side linking** **[DISASM 0x36a45]**: for each not-yet-linked edge, find the first
other node traversing the same two points in opposite winding, allocate a fresh side id if unassigned
(`NumSharedSides++`), write it to both endpoints' `iSide`. Purely combinatorial (point indices + ring
positions), no floating point. Byte-exact against the golden: all 16,163 `iSide` values match, final
`NumSharedSides = 2739`.

Pass 1 is idempotent on an already-processed model (a fixpoint, 0 further insertions on re-run).

---

## 7. Zone and portal assignment (`TestVisibility` / "portalize")

Driver **[DISASM Editor.dll 0xaa370, called from `UEditorEngine::TestVisibility` 0xaa940]**, a stack
object `FEditorVisibility` (`sizeof=0x10058`). Sequence: pre-reset every node's `iLeaf[0..1]=-1` and
every surf's `+0x18=-1` field, empty `Model.Leaves`/`Lights` → **Pass A** `AssignLeaves` → **Pass B**
`MakePortals` → **Pass C** `AssignZones` (flood) → **Pass D** `AssignAllZones` (per-node stamping) →
**Pass E** `BuildZoneMasks` → **Pass F** `BuildConnectivity` → **Pass G** `BuildZoneInfo` → `bspCleanup`
/ `bspRefresh` / `bspBuildBounds`. Terminal log line:
`"Portalized: %i portals, %i zone portals (%i fragments), %i leaves, %i nodes"`.

Per §1.1, this whole pipeline only runs under the explicit `ZONES` keyword on `BSP REBUILD` — not as
part of a bare `MAP REBUILD`.

`FEditorVisibility`'s own field layout (editor-only scratch on `GMem`, never disk-serialized —
included here only as a cross-reference aid for re-disassembling any of the passes below, not needed
to reimplement the algorithms themselves) **[DISASM; `re-raw-zones/ctor-fieldmap-6970.md`,
`re-raw-zones/passesBDEFG-ctor.md`]**: ctor at Editor.dll `0xa6970`; `+0x0c Level`, `+0x10 Model`,
`+0x14..+0x10013` a 0x4000-entry ancestor node-path stack (bit `0x40000000` OR'd when descending BACK),
`+0x10014` portal count, `+0x1001c` path-stack depth, `+0x10034` zone-portal count, `+0x10038`
fragment count, `+0x10040` scratch (current zone-portal's surf index, written by Pass B step 4, read by
`BlockPortal`), `+0x10044` global `FPortal*` list head, `+0x1004c` per-node list heads
(`2*Nodes.Num+0x100` entries), `+0x10050` per-leaf list heads (`Leaves.Num` entries). `FPortal` record
itself (0x200 B, ctor `0xa6ab0`): an `FPoly` copy at `+0`, then `iLeafFront +0x1d8`, `iLeafBack +0x1dc`,
`iNode +0x1e0`, four intrusive-list-next pointers `+0x1e4..+0x1f0`, `iZonePortalSurf +0x1fc` (init -1).

### 7.1 Pass A — `AssignLeaves` (leaf enumeration)

**[DISASM Editor.dll 0x100a7760]**. Pure DFS over the BSP tree, `iChild[0]` (BACK) then `iChild[1]`
(FRONT) — the coplanar `iPlane` chain is never read by this pass. Seeded at the root with
`Outside = Model.RootOutside`. **Ground truth: `RootOutside == 0` for both a real UNATCO level and a
real castle test level's serialized `.dx` trailer** — read directly from real package files, settling
that this flag is not a per-level author toggle producing observed cross-level differences
**[LIVE, read from real `.dx` files; `sections/92-bspbrushcsg-reallevel-port-plan.md:929-931,965-971`]**.

```
ChildOutside(side, Outside, ExtraFlags=4):
  FRONT (side 1): Outside || IsCsg(node, ExtraFlags)
  BACK  (side 0): Outside && !IsCsg(node, ExtraFlags)
  IsCsg(node, ExtraFlags) = NumVertices>0 && (NodeFlags & (ExtraFlags|0x21)) == 0

AssignLeaves(iNode, Outside):
  for side in {BACK, FRONT}:
    NewOutside = ChildOutside(side, Outside, 4)
    if iChild[side] != -1: recurse AssignLeaves(iChild[side], NewOutside)
    else if NewOutside: append a fresh FBspLeaf {iZone = Leaves.Num (its own pre-append index),
                                                   iPermeating=-1, iVolumetric=-1, iExclusive=~0u64}
                        store its index into node.iLeaf[side]
    // else (NewOutside==false, i.e. solid): iLeaf[side] stays -1, no leaf created
```

**No merge/dedup at leaf creation** — every terminal-empty side unconditionally gets a brand-new leaf;
"one leaf per convex empty region" is literal (a region is exactly one terminal BSP cell).

Because `ExtraFlags=4` is always passed, the mask tested is `0x25 = 4 | NF_IsNew(0x20) |
NF_NotCsg(0x01)` — **a node with NodeFlags bit `0x04` set is transparent to solidity during leaf
assignment**: `Outside` is *not* flipped across such a node, so it subdivides one contiguous empty
region into two independently-leaved terminal cells without acting as a solid boundary. This is how a
portal face splits leaves without this pass ever inspecting `PF_Portal`/Surf data at all — confirmed
by an exhaustive scan finding zero reads of any Surf or PolyFlags field anywhere in the function.
(This pass touches only `Model`, `Nodes[].iChild/iLeaf/NumVertices/NodeFlags`, and the `Leaves` array.)

**[DISASM; `re-raw-zones/passA-leafenum-7760.md`, `re-raw-zones/passA-portalbuilder.md`]**

### 7.2 Pass B — `MakePortals` (portal-graph construction)

**[DISASM Editor.dll 0x100a9750]**, plus helpers `BuildInfiniteFPoly [0xa7ae0]`,
`MakePortalsClip [0xa9970]`, `FilterThroughSubtree [0xa9030]`, `AddPortal [0xa72a0]`,
`BlockPortal [0xa7870]`.

Per node, recursively:
1. Build a **65536-half-extent** ("WORLD_MAX") quad lying on the node's own plane
   (`BuildInfiniteFPoly`, from the node's surf `pBase`/`vNormal`).
2. `MakePortalsClip`: clip that quad against every ancestor plane on an inline ancestor stack
   (16384-entry headroom, no bounds check), keeping the fragment inside this node's convex cell, then
   hand it to `FilterThroughSubtree` rooted at this node with callback `AddPortal`.
3. Recurse into `iChild[1]` (FRONT) then `iChild[0]` (BACK).
4. After the subtree returns, walk this node's coplanar `iPlane` chain; for every chain member whose
   surf has `PF_Portal` set, fetch its **real, stored polygon** (`bspNodeToFPoly`) and re-filter it
   through the **chain-head's** subtrees with callback `BlockPortal` (not the flagged node's own
   subtrees — a `PF_Portal` face on a non-head chain member has no `iLeaf` of its own).

`FilterThroughSubtree`: two-phase — filters a fragment down the home node's BACK subtree first; every
resulting back-leaf fragment is then re-filtered down the home's FRONT subtree; every resulting
front-leaf landing invokes the callback with `(frontLeaf, backLeaf)`. Classification uses
`FPoly::SplitWithNode(Model, iNode, VeryPrecise=1)` (`0.01` band) — fragments above 14 vertices are
pre-split.

`AddPortal`: drops any landing touching solid space (`iF==-1 || iB==-1`); otherwise allocates a
0x200-byte `FPortal` record and threads it into four intrusive linked lists (global, per-node,
per-front-leaf, per-back-leaf). `FPortal` layout: `+0x1d8 iFrontLeaf, +0x1dc iBackLeaf, +0x1e0 iNode,
+0x1fc iZonePortalSurf (init -1)`.

**`BlockPortal` — the exact zone-barrier rule**, the load-bearing distinction:
```c
if (iF==-1 || iB==-1) return;
for each FPortal P in the global list:
  if (P.iFrontLeaf,P.iBackLeaf) unordered-equals (iF,iB):
    P.iZonePortalSurf = <the triggering PF_Portal surf's index>
```
So: **a leaf-adjacency `FPortal` record is a zone barrier if and only if its unordered leaf-pair
coincides with a leaf-pair landing produced by re-filtering the real, stored polygon of some
`PF_Portal`-flagged coplanar-chain node.** Every other `FPortal` (the bulk of the graph, generated by
the generic infinite-quad construction in step 2) keeps `iZonePortalSurf==-1` and is a non-blocking
interior adjacency. This stamping is purely additive bookkeeping on records the generic mechanism
already created — `BlockPortal` never creates a new `FPortal`.

**Only `PF_Portal` is ever tested as a flag anywhere in this pass** — no other PolyFlags bit
(semisolid, invisible, two-sided) and no NodeFlags bit participates in the barrier decision.
**No area/size gating exists anywhere in Pass A or Pass B** — no minimum-portal-area threshold beyond
the 14-vertex split guards.

**[DISASM; `re-raw-zones/passA-portalbuilder.md`, `re-raw-zones/passB-makeportals-9750.md`,
`sections/70-zones-portalization.md`]**. `SplitWithNode`'s exact return-code mapping is
**[INFERRED]** from caller branch structure (not independently disassembled at its own call site);
the coplanarity epsilon it uses internally is not decoded.

### 7.3 Pass C — `AssignZones` (zone flood)

**[DISASM Editor.dll 0x100a93c0]**, "Found %i zones". **Not** a graph BFS/union-find over portals —
a **relabel-by-scan over the leaf array**, cross-confirmed by two independent decode passes reaching
the identical algorithm:

- **Phase 1 — union by relabel:** walk the global portal list; for every record with
  `iZonePortalSurf == -1` (i.e. NOT a real zone-portal barrier), read `A = Leaves[iLeafFront].iZone`,
  `B = Leaves[iLeafBack].iZone`, then **scan the entire `Leaves` array**, rewriting every leaf with
  `iZone==A` to `iZone=B`. O(portals × leaves), not a rank/pointer union-find. Barrier-stamped records
  are skipped — leaves on either side of a real portal stay in different classes unless connected some
  other way.
- **Phase 2 — compaction:** relabel surviving classes to dense ids `0..N-1` in leaf-index order
  (relies on Pass A's "label = own array index" seeding invariant to stay correct).
- **Phase 3 — remap to engine zone numbers 1..63:** `Leaves[i].iZone = (denseId % 63) + 1` — a
  **silent modulo wrap**, not a clamp or error, if class count exceeds 63. Zone 0 is reserved for
  "outside"/solid.
- **Final write:** `Model.NumZones = Clamp(N+1, 1, 64)`.

Pass C writes **only** `Leaves[i].iZone` and `Model.NumZones` — no node field, no `ZoneMask`, no
`Zones[]` array entries. Numbering is order-sensitive: the portal list is built by **prepend**
(LIFO — reverse of Pass B's creation order), so a byte-exact port must reproduce Pass B's exact
traversal order to get matching zone *numbers* (not just matching membership).

**[DISASM; `re-raw-zones/passC-zoneflood-93c0.md`, `re-raw-zones/passC-zonesetter.md`]**

### 7.4 Pass D — `AssignAllZones` (per-node zone stamping)

**[DISASM Editor.dll 0x100a7400]**. Recursive, front child first then back
(`Outside` is threaded through the recursion signature but is read nowhere in this pass's own body —
dead for this pass's output). Per node in each coplanar chain (skipping `NF_IsNew` fragments):

1. Rebuild the node's polygon via `bspNodeToFPoly`.
2. Re-filter it through the **chain head's** subtrees via `FilterThroughSubtree` (back first, then
   front per back-landing) — reports every maximal fragment separating a specific
   `(frontLeaf, backLeaf)` pair.
3. Per landing: create a new `NF_IsNew` coplanar fragment node
   (`bspAddNode(Model, iNode, NODE_Plane, ..., poly)`), compute
   `side = (dot(chainHead.Plane.Normal, poly.Normal) < 0)`, and write
   `iZone[side] = (backLeaf==-1) ? 0 : Leaves[backLeaf].iZone`,
   `iZone[side^1] = (frontLeaf==-1) ? 0 : Leaves[frontLeaf].iZone`.
4. **Reconciliation, per chain node** (fragments span the newly-appended node range): collect
   `Zone[0]/Zone[1]` = last-nonzero-wins across all fragments. If **all fragments agree** per side, all
   the fragments are killed (`NumVertices=0`) and the agreed pair is written directly onto the
   **chain-head's own node** (`iZone[0..1]`). If fragments **disagree** (a face genuinely spans two
   zones — e.g. a water-surface portal wall), the **original source node** is zeroed instead, and only
   the fully-zoneless (both sides zero) fragments are killed — the multi-zone face survives as its
   per-zone-pair fragment set. **The stamping target in both the match and mismatch case is always the
   chain HEAD's node**, even when the source polygon came from a different, non-head chain member.

No `FBspSurf` write happens in this pass (fragments inherit `iSurf` from the source node via
`bspNodeToFPoly`'s `iLink`, so `bspAddNode`'s "allocate a new surf" branch is never taken).
`ZoneMask` is not computed here either — a fragment node just copies its parent chain-tail's
`ZoneMask` verbatim (the real OR-recurrence is Pass E).

**[DISASM; `re-raw-zones/passD-assignzones-7400.md`, `re-raw-zones/passesBDEFG-ctor.md`]**

### 7.5 Passes E/F/G — masks, connectivity, zone actors

- **Pass E, `BuildZoneMasks`** **[DISASM Editor.dll 0xa8850]** (recursive, returns u64):
  `mask = bit(iZone[0]) | bit(iZone[1]) | recurse(iChild[1]) | recurse(iChild[0]) |
  recurse(iPlane)`, written to `node.ZoneMask`. **Zone 0 sets no bit** — a subtree entirely in zone 0
  gets `ZoneMask==0`, not all-ones. Called twice: once during portalize, again at the top of
  `bspBuildBounds` (§9).
- **Pass F, `BuildConnectivity`** **[DISASM Editor.dll 0xa7960]**: seeds `Zones[i].Connectivity =
  bit(i)` for `i=0..63`; for every node whose surf has `PF_Portal`, ORs
  `Zones[iZone[1]].Connectivity |= bit(iZone[0])` and the symmetric reverse. **Unlike Pass E, this does
  NOT skip zone 0** — a portal touching zone 0 sets bit 0 in the neighboring zone's connectivity
  normally. Live-cross-checked against a real shipped map (`02_NYC_Bar.dx`): observed connectivity
  `zone0=0x1, zone1=0x6, zone2=0x6, zone3=0x8` — exactly self-bit plus portal neighbors
  **[LIVE, DISASM]**.
- **Pass G, `BuildZoneInfo`** **[DISASM Editor.dll 0xa7e60]**: clears every `Zones[i].ZoneActor`;
  resets every level actor's `Region` to `{iLeaf=-1, ZoneNumber=0}`; for each `AZoneInfo`-derived
  actor (excluding `ALevelInfo` itself), computes its zone via `Model->PointRegion` (a real BSP
  descent, in `Engine.dll` — not part of Editor.dll's own code) and binds `Zones[Z].ZoneActor` to the
  **first** `ZoneInfo` landing in each zone (later ones in the same zone counted as duplicates, not
  errors). Also fills reverb probe data and warp-zone frame fields (actor-side only, no `UModel`
  writes). Re-zones every level actor via `ULevel::SetActorZone`.

`Zones[i].Visibility` is **never written anywhere in Editor.dll** — confirmed by an exhaustive
whole-`.text` scan, cross-confirmed on two independent occasions. It stays at `UModel::EmptyModel`'s
init value, all-ones (`0xFFFFFFFFFFFFFFFF`), live-verified on two real shipped maps
(`02_NYC_Bar.dx`, `03_NYC_UNATCOHQ.dx`) **[DISASM, LIVE]**.

**[DISASM; `re-raw-zones/passesEFG-8850-7960-7e60.md`, `re-raw-zones/passesBDEFG-ctor.md`,
`re-raw-zones/bounds-and-zonelayout.md`]**

---

## 8. `bspBuildBounds` — render bounds and collision hulls

**[DISASM Editor.dll 0xaace0]**. No-ops if `Nodes.Num==0`. Sequence:
1. Calls `BuildZoneMasks` again (§7.5 Pass E).
2. Builds 6 quads forming the world cube at **half-extent 32768.0** ("HALF_WORLD_MAX").
3. Resets `Bounds`/`LeafHulls`, sets every node's `iRenderBound`/`iCollisionBound = -1`.
4. Calls the recursive worker `FilterBound(Model, NULL, iNode=0, PolyList=<the 6 world quads>, 6,
   RootOutside)` **[DISASM Editor.dll 0xa8a40]**.
5. `Bounds.Shrink()`; logs `"bspBuildBounds: Generated %i bounds, %i hulls"`.

**`FilterBound`**: recursively splits the current hull-polygon set by each node's plane
(`SplitWithPlane`, `±0.25` band, `>14`-vertex split guard), closes each child's open hull with the
node's own infinite plane-quad (`SplitPartitioner [0xaa000]`), and recurses with the same
`Outside`-propagation convention as CSG filtering.

- **Interior node** (has children) with `iRenderBound==-1`: allocates a new `Bounds[]` entry = the
  AABB of every air-leaf hull-vertex in that node's subtree. **Which nodes get a render bound**: only
  nodes with `>=1` child; pure leaf nodes keep `iRenderBound=-1`. **Numbering**: `iRenderBound` is a
  post-order DFS index over the front/back tree (the root gets the *last* index) — `Bounds[k]` is
  literally the k-th node finished in that traversal.
- **Terminal AIR side** (`Outside||IsCsg`, no child): accumulates vertices into the parent AABB via
  `UpdateBoundWithPolys` (plain `Bound += Vertex[j]`).
- **Terminal SOLID side**: `UpdateConvolutionWithPolys [0xaaae0]` sets
  `Nodes[iNode].iCollisionBound = LeafHulls.Num`, then appends the (deduped) `iBrushPoly` tag of each
  hull-boundary poly to `LeafHulls`, followed by a **`-1` terminator**, then the region's 6 raw
  bitcast-f32 AABB floats — the on-disk `LeafHulls` run format:
  `[plane-node-ref tags…], -1, minX, minY, minZ, maxX, maxY, maxZ`.
  `SplitPartitioner` tags the **front**-child hull face with `iBrushPoly | 0x40000000` (bit 30 =
  "flip this plane's normal for this side"); the back-child face's tag is untouched. **If both sides
  of a node terminate solid, the back-side call overwrites `iCollisionBound`** (front runs first) —
  an explicit must-reproduce ordering detail.

**`FBox::operator+=` quirk** **[DISASM Core.dll 0x185b0]**, load-bearing for byte-exact `Bounds[]`: if
both boxes being combined are valid, it expands normally; **otherwise it fully replaces** `*this =
Other` (including the validity flag) — so a subtree with no air leaves can *replace* an already-valid
accumulated parent bound with an invalid one.

The render bound (`Bounds`) and the collision hull (`LeafHulls`) come from the **same** `FilterBound`
convex-cell-clip computation — one pass feeds both arrays. Neither `Bounds`/`LeafHulls`/
`iRenderBound`/`iCollisionBound` is strictly required for a *rendering* level to function
(`-1`/empty is a legal, live-verified state, only losing frustum-cull optimization) — but per §9.2,
`LeafHulls`/`iCollisionBound` is **required for pawn collision**.

**[DISASM, BYTE-DIFF; `sections/82c-bounds-leafhulls-decode.md`, `re-raw-zones/bounds-and-zonelayout.md`]**

---

## 9. Collision — two distinct algorithms

`UModel::LineCheck` **[DISASM Engine.dll 0xf3c20]** branches on whether `Extent != (0,0,0)`.

### 9.1 Zero-extent line check (`0xf3560`)

Used for e.g. lightmap occlusion / boolean visibility tests. Node-plane recursion:
`FBspNode::IsCsg()` **[DISASM 0xf68b0]** decides solidity (same `NumVertices>0 &&
!(NodeFlags & (NF_NotCsg|NF_IsNew|ExtraFlags))` shape as elsewhere). `iChild[1]` is confirmed the
FRONT/positive (`PlaneDot>=0`) child, `iChild[0]` is BACK — cross-checked against `UModel::PointRegion`
independently. Split branch interpolates the crossing point; terminal outside → sets the global
`GDidHitEmpty` **[DISASM Engine.dll 0x1058f34c]** and returns miss; terminal not-outside → fills
`Result.Location`/`Normal` from the last-crossed node's plane and returns a hit. **`LeafHulls` is
never read in this path.**

### 9.2 Box-sweep `BoxLineCheck` (`0xf42f0`) — actual pawn/actor collision

A **separate function**, not a degraded zero-extent case. Still walks nodes with the same
FRONT/BACK convention and inline `IsCsg` routing, inflating the swept `Extent` by a fixed `1.1×` for
routing purposes only — **but the walk alone never registers a hit.** At a terminal solid leaf, the
function reads `iCollisionBound` from the leaf's parent node; **if `iCollisionBound == -1`, the
function returns with NO hit registered** — there is exactly one `DidHit=1` store site in the whole
function, reachable only through the `LeafHulls` clip path. That clip reads the hull run starting at
`LeafHulls[iCollisionBound]` (§8's format), clips the swept box against each hull plane plus the 6
leaf-bbox faces (pushed out 0.1 units) plus pairwise plane-plane edge intersections, tracking an
entry/exit interval via standard slab clipping; accept condition `T0 > -1.0 && T0 < T1 && T1 > 0.0`.

**`LeafHulls` is not optional for gameplay collision — it is the sole hit source for any nonzero-extent
sweep. There is no node-plane fallback.** A build with topologically-correct BSP nodes/flags/`iLeaf`
but `iCollisionBound=-1`/empty `LeafHulls` everywhere passes every pawn sweep straight through solid
geometry — live-confirmed and A/B-proven: synthesizing one correct hull for a floor's solid leaf and
pointing its node's `iCollisionBound` at it makes the sweep land exactly at `floor + extent`; without
it the pawn's center crosses into solid space and only the *separate* `PointRegion` zone system
(a genuine point test, not a sweep) eventually detects "fell out of world" and freezes it near the
plane — a failure mode that can be mistaken for a landed sweep if not checked carefully.

By contrast, `UModel::PointCheck` **[DISASM 0xf19b0]** (used for `FindSpot`/encroachment, not the
per-frame movement sweep) *does* have an explicit `iCollisionBound==-1` skip that simply returns
non-blocking — hull-less solid space does not block a point-check either.

**[DISASM, LIVE, A/B-tested; `re-raw-zones/linecheck-oracle.md`]**

---

## 10. Lighting rebuild (`LIGHT APPLY`)

Console verb `LIGHT APPLY [SELECTED=<n>] [VISIBLEONLY=<n>] [SHOWINV]`; GUI "Build Lighting" sends the
identical `LIGHT APPLY SELECTED=%d VISIBLEONLY=%d` string (§1.5). Dispatches to
`UEditorEngine::shadowIlluminateBsp(ULevel*, INT selected, INT changedOnly)`
**[DISASM Editor.dll 0xa5e10]**; source path embedded in the binary is
`C:\GameDev\UnrealTournament\Editor\Src\UnShadow.cpp`. This operates against the **already-built**
BSP (`Level->Model->Nodes`) via a line-check against the tree — it is strictly downstream of geometry
build (§1-§9), never upstream of it.

### 10.1 The decisive finding: visibility bits, not intensity

**The bake stores a per-lumel shadow BIT, never a light intensity, colour, or attenuation value.**
For every lit surface, per light that reaches it, the editor stores a 1-bit-per-lumel mask: `1` =
that lumel has clear line-of-sight to the light and is inside its radius; `0` = shadowed or
out-of-range. No brightness, hue, saturation, or sign is baked — those are read from the light
actor's own properties (already present in the level's actor data) and applied by the **game at
render time**, not by the editor at build time. The bake is purely geometric: radius cutoff + BSP
line-of-sight. This collapses "reproduce lighting" to "reproduce a per-lumel BSP ray test", not
"port a light-transport/radiosity model" — Deus Ex's coloured lighting is entirely a render-time
tint of a monochrome bit-plane.

### 10.2 Pipeline

Progress strings in order, confirming four ordered stages: `"Rebuilding lighting"`, `"Computing
visibility"`, `"Allocating meshes"`, `"Raytracing"`.

1. **Reset.** Empties `Model->LightMap` (`UModel+0xa8`) and `Model->LightBits` (`UModel+0xb4`); sets
   every `FBspSurf.iLightMap` (`surf+0x18`) to `-1`. **Every `LIGHT APPLY` invocation discards prior
   lightmap data before regenerating it** — this is the bake's own internal reset, not a claim about
   what a separate geometry rebuild does to lighting (that connection is not directly evidenced — see
   §18 item 6).
2. **Gather lights** ("Computing visibility", `Editor.dll 0xa4ba0`) — a per-**leaf** flood (§10.5)
   determining which surfaces/leaves each light can even reach, before any per-lumel raytracing.
3. **Allocate meshes** ("Allocating meshes", `Editor.dll 0xa5bf0`) — per lightable surface, computes
   the lumel-grid dimensions/scale/pan (§10.4) and stores an `FLightMapIndex`, setting
   `surf.iLightMap`.
4. **Raytrace** ("Raytracing", `Editor.dll 0xa5010`, `illuminateSurf`) — per lumel × per light in the
   surface's list, radius cutoff + BSP shadow ray, packs the resulting bit (§10.3). Run once per
   static surface and once per mover surface (a second pass with `mover != 0`, lighting mover
   surfaces in the mover's base pose).
5. Populates `Model->Lights` (`UModel+0xe4`) as the flattened per-list light-actor references.

### 10.3 The raytrace, per lumel per light

1. **Radius cutoff.** `d² = |P - Light.Location|²`; `R = Light.WorldLightRadius()` (virtual, vtable
   `+0x6c`). If `R² <= d²`: bit=0, no ray cast — cheap reject before any BSP work.
   `AActor::WorldLightRadius` **[DISASM Engine.dll 0x116b50]**: `R = (LightRadius + 1) × 25.0` world
   units, `LightRadius` a `BYTE` at `actor+0x1a1` — the classic UE1 ×25 scale. This radius (plus the
   light's `Location`) is the **only** light property read by the geometric bake; `LightBrightness`/
   `LightHue`/`LightSaturation`/`LightType`/`LightEffect`/`bSpecialLit` are never read here — those
   are render-time only.
2. **Front-of-plane test.** A real-content measurement (0/3497 back-facing entries across a real
   built level's full per-surface light lists) shows the editor never lists a light behind a
   surface's own plane — `d=(Light.Location-Base)·vNormal <= 0` excludes it from the surface's light
   list before raytracing even starts. The exact enforcement point (inferred to be inside the
   gather/visibility pass's renderer-delegation calls) was not itself disassembled to a specific
   branch — the *effect* is measured with 0/3497 exceptions on real content, the *mechanism* inside
   the gather pass is not pinned to an instruction.
3. **Shadow ray.** `Level->Model->LineCheck(...)` (vtable `+0x58` → `UModel::LineCheck`,
   `Engine.dll 0x1ae4c0`; the boolean variant is `UModel::FastLineCheck`, `Engine.dll 0x1ada40` — the
   zero-extent line check already documented in §9.1, reused here rather than a separate lighting-only
   ray primitive). Solid surfaces occlude; non-solid/semisolid/portal/masked do not, per ordinary
   `LineCheck` collision-flag behavior.
4. **Self-shadow bias.** The ray/lumel origin is pushed off the surface by `Normal × 4.0` world units
   (constant `4.0`), to avoid the surface self-occluding its own lumel.

### 10.4 `FLightMapIndex` (40 bytes) and the lumel-grid formula

Fields (in-memory offset): `+0x00 DataOffset` (i32), `+0x04 iLightActors` (i32, `-1` = unreached),
`+0x08 Pan` (3×f32), `+0x14 UScale`/`+0x18 VScale` (f32), `+0x1c USize`/`+0x20 VSize` (compact index,
clamped `[2,256]`).

Scale selection, from `.rdata` constants keyed on the surf's shadow-detail `PolyFlags`: `128` if both
`PF_HighShadowDetail|PF_LowShadowDetail` set, `16` if only High, `64` if only Low, else `32` default.

**Grid-sizing formula — settled only after correcting an earlier wrong disassembly reading, per the
source's own revision history (preserved here rather than presenting the corrected version as if it
were the first attempt):**

```
size        = Clamp(ceil(extent / lumel_scale), 2, 256)             // NOT truncation
texel_scale = (extent + 0.25) / (size - 1)                          // NOT extent/(size-1)
extent      = max((vertex - Base)·TexAxis) - min((vertex - Base)·TexAxis)   // subtract Base FIRST
Pan         = min((vertex - Base)·TexAxis) - 0.125                  // base-relative, NOT raw-world
```

Each correction was caught by a byte-diff against a real editor-built `Test_Castle.dx` (484/484
`FLightMapIndex` records match exactly once all four corrections are applied) — a naive truncating
`size` formula, an `extent/(size-1)` scale formula, a raw-world (not base-relative) extent/Pan
computation, and a wrong `vert·Tex - Base·Tex` operation order (algebraically equal to
`(vert-Base)·Tex` in real arithmetic, but rounds differently in float32 on angled texture axes) were
each individually falsified by this real map before the formula above was confirmed. This history is
worth keeping in a spec, not just the final answer: each of these four naive-seeming variants is
exactly the kind of guess a fresh reimplementation would make and get wrong.

### 10.5 Gather / visibility pass — the per-leaf permeating-light flood

`FEditorVisibility::ActorVisibility` **[DISASM Editor.dll 0xa6d00]**, source path `UnVisi.cpp`. This
is neither pure zone-based nor pure radius-based culling — it is a **radius-gated, BSP-portal
flood-fill with beam clipping**:

- **Seed leaf**: plain BSP descent from the root by `PlaneDot(node.Plane, Light.Location)` sign,
  following children to a terminal `iLeaf`. A light embedded in solid space (`iLeaf==-1`) seeds
  nothing. No coplanar-chain walking, no radius test at the seed.
- **Marking**: appends the light actor's pointer to `FEditorVisibility+0x10054[iLeaf]` (an intrusive
  list, deduped by pointer identity — an already-marked leaf is not re-appended, but flooding still
  continues *through* it; there is no depth guard, termination relies on the beam narrowing to
  nothing).
- **Flood through each portal of the current leaf**, gated on:
  - **side**: `d = (Light.Location - Portal.Base)·Portal.Normal < 0` (light on the leaf's own side).
  - **radius**: `d > -R` (the portal plane itself is within the light's radius).
  - then recurses into the leaf on the portal's other side, **clipping the carried beam polygon**
    (the light's view pyramid) against the portal's edges via `FPoly::SplitWithPlaneFast` before
    recursing — a beam that clips away to nothing simply stops flooding.
- A **non-seed** leaf additionally requires some portal of that leaf to have a vertex strictly within
  `WorldLightRadius` of the light before it can be entered at all.
- A sibling pass (`Editor.dll 0xa9290`) repeats the identical mechanism for fog-volumetric lights
  into `leaf.iVolumetric`, using `WorldVolumetricRadius` (`Engine.dll 0x116bb0`,
  `25×(VolumeRadius_byte + 1)`), gated additionally on the leaf's zone having `bFogZone` set.
  `leaf.iExclusive` (u64, `FBspLeaf`'s 4th field) is never written anywhere in this whole pass —
  stays at its `EmptyModel` init value of all-ones.
- Eligibility gates at the call site: the light pass requires `LightType != 0` and the actor's
  `bStatic|bNoDelete` flag bits; the volumetric pass additionally requires a nonzero
  `VolumeRadius`/`VolumeBrightness`.

This flood populates a **first region** of `Model->Lights` (per-leaf permeating-light lists, indexed
by `FBspLeaf.iPermeating`), distinct from the **second region** populated by §10.2's per-surface
gather (indexed by `FLightMapIndex.iLightActors`) — on one real reference map the two regions occupy
disjoint index ranges `[0, 7455)` and `[7455, 11392)` respectively within the same flat `Model->Lights`
array, discovered by walking every index that actually references the array rather than assuming a
single format.

### 10.6 `LightBits` — exact byte encoding

Per lit surface, its `N` light bit-planes (`N` = the length of its `iLightActors` NULL-terminated
run) are stored consecutively starting at `FLightMapIndex.DataOffset`. Each plane is `USize × VSize`
bits, row-major in V: `VSize` rows, each `ceil(USize/8)` bytes, byte-aligned per row; within a row,
lumel `u` is bit `(u & 7)` of byte `u >> 3`, **LSB-first**. Bit `1` = lit, `0` = shadowed/out-of-range.
Bits above `USize` in a row's final byte are not guaranteed cleared.

Verified by a byte-span reconciliation across three real levels: the gap between consecutive
`DataOffset`s divides exactly by `N × ceil(USize/8) × VSize` with zero exceptions across 2867+2293+621
real records, and the resulting `N` independently matches the `iLightActors` run length to NULL for
every one of those records — two independently-derived measures of the same value agree with zero
mismatches.

### 10.7 `PF_Portal` lightmap-skip mask; `LightMap` array emission order

**Skip mask** (pinned by disassembly of the allocate-meshes gate): a surf is skipped for lightmapping
(`iLightMap` stays `-1`) iff `PolyFlags & 0x400081 != 0`, where
`0x400081 = PF_Unlit(0x400000) | PF_FakeBackdrop(0x80) | PF_Invisible(0x1)`. **`PF_Portal` is NOT in
this mask** — a two-sided water-portal sheet is genuinely lightmapped by the real editor (confirmed:
real lit records on a two-sided portal surface in a reference map).

**Array order**: the on-disk `LightMap` array is emitted in **BSP tree-walk order**, not surf-index
order (a real reference map's record→surf sequence is `[102, 324, 267, 191, 17, …]`, not `[0,1,2,…]`)
— descend from the root, visit the current node's surf (allocating its `FLightMapIndex` record the
first time each lightmappable surf is seen across the whole walk), recurse BACK then FRONT, then step
along the node's own `iPlane` coplanar chain. A surf is marked "seen" on first visit regardless of
whether it's actually lightmappable. This walk reproduces a real map's emission order exactly.
`LightBits` offsets and the per-surf `Lights`-array region follow this same order.

### 10.8 Constants

| Constant | Value | Role |
|---|---|---|
| Light radius formula | `(LightRadius_byte + 1) × 25.0` | `WorldLightRadius`, also the volumetric analogue with a different byte field |
| Self-shadow bias | `Normal × 4.0` uu | ray-origin push-off |
| Lumel-grid scale | 128 / 16 / 64 / 32 (High+Low / High / Low / default) | keyed on shadow-detail `PolyFlags` |
| Lumel-grid size clamp | `[2, 256]` | `FLightMapIndex.USize`/`VSize` |
| Lightmap-skip mask | `0x400081 = PF_Unlit\|PF_FakeBackdrop\|PF_Invisible` | gates `iLightMap=-1` (portal NOT included) |

### 10.9 Confidence notes

Very strong: the bit-not-intensity finding, the `LightBits` byte encoding (byte-span reconciliation,
zero exceptions across 2867+2293+621 real records), the grid formula (484/484 exact against a real
map, with the wrong intermediate readings explicitly falsified rather than silently dropped), the
`LightMap` emission-order walk, and the `PF_Portal` skip-mask correction — all cross-checked against
real editor-written `.dx` bytes, not disassembly alone. Weaker/explicitly flagged by the source: the
front-of-plane test's enforcement point (effect measured at 0/3497 exceptions, mechanism not
instruction-pinned); the exact semantic naming of `FPoly::SplitWithPlaneFast`'s `SP_Back`/`SP_Split`
enum values inside the visibility flood (behavior exact-as-quoted, semantic label inferred from
convention); `actor+0x28`/`zoneinfo+0x27c`'s exact bit meanings (inferred from standard UE1
declaration order, not independently re-proven here). **Not established by either source read for
this section**: what a *geometry* rebuild does to already-baked lighting data at the instruction
level (only the bake's own self-reset was found, not a `MAP REBUILD`-side confirmation) — carried
forward as an open item, §18.

---

## 11. Paths rebuild (`PATHS DEFINE` / `PATHS BUILD`)

Console verbs `PATHS DEFINE` / `PATHS BUILD [LOWOPT|HIGHOPT]`; GUI "Build Paths" sends `PATHS DEFINE`
then `PATHS BUILD` (§1.5). Both dispatch through `FPathBuilder::buildPaths(ULevel*, INT opt)`
**[DISASM Engine.dll 0x177770]** — note this lives in `Engine.dll`, not `Editor.dll` (the AI
navigation graph is a runtime/gameplay structure the editor happens to also be able to build, unlike
the BSP/lighting machinery which is editor-only).

### 11.1 Pipeline: `definePaths` vs `createPaths` vs `Prune`

`buildPaths`'s own sequence: strip stale auto-`PathNode`s → `undefinePaths` → **`definePaths`**
(place markers) → acquire a scout pawn → set scout collision params → **`createPaths(opt)`** (build
all `FReachSpec`s) → destroy scout → refresh markers → log `"Built Paths: %d"`.

- **`definePaths`** **[DISASM Engine.dll 0x178c10]** only **spawns auto-marker `NavigationPoint`s** —
  an `InventorySpot` under every `Inventory` actor, a `WarpZoneMarker` under every `WarpZoneInfo`
  actor — and builds **zero** `FReachSpec`s. Logs `"DevPath: Defining paths."`. So `PATHS DEFINE` run
  standalone (as its own console verb) yields markers only, no edges — it is a strict subset of what
  `PATHS BUILD` runs internally as its own second stage, not a separate half of the graph.
- **`createPaths`** is where every `FReachSpec` edge is actually built (§11.3-11.4).
- **`Prune`** **[DISASM Engine.dll 0x176790]** runs last, marking redundant edges (§11.6).

### 11.2 `FReachSpec` — fields and on-disk layout

On-disk, inside `ULevel.ReachSpecs` (a `TArray`, compact-index count), byte-exact against a 100-real-map
corpus (`level_roundtrip.py`, 100/100 exact):

```
FReachSpec:
  i32 Distance          // path cost
  ci  Start              // object ref -> source NavigationPoint
  ci  End                // object ref -> destination NavigationPoint
  i32 CollisionRadius    // largest pawn radius that fits this edge
  i32 CollisionHeight    // largest pawn height that fits this edge
  i32 reachFlags         // bitmask, §11.5
  u8  bPruned            // 1 = kept for AI fallback, excluded from routing
```

Variable serialized length (17-21 bytes, `Start`/`End` are 1-3-byte compact indices). Edges are
**directed** — `Start→End` one-way; a bidirectional connection is two separate records.

In-memory shape (28 bytes, `ULevel+0x8c`): same fields, `Start`/`End` as raw `AActor*` pointers
instead of compact-index refs. Each `NavigationPoint` additionally carries three `16×INT` arrays
indexing into `ReachSpecs` (`-1` = empty slot): `upstreamPaths[16]` (incoming), `Paths[16]`
(outgoing, used for routing), `prunedPaths[16]` (pruned edges kept as fallback) — this per-node
array's exact on-disk property-tag encoding was not independently byte-verified against a real level
by the sources read (flagged open, §18).

### 11.3 Reachability test — the scout sweep and the trace

`createPaths` builds the graph with a **scout pawn** sized `SetCollisionSize(Radius=52.0,
Height=40.0)` **[DISASM Engine.dll 0x10177a4f]**. For each candidate node pair, `findBestReachable`
**[DISASM Engine.dll 0x193dd0]** **sweeps the scout's collision size from `(18.0, 39.0)` up to a max
radius of `70.0`**, recording the *largest* size that still successfully traverses — that becomes the
stored `CollisionRadius`/`CollisionHeight`. A resulting radius `< 24` marks the edge bot-only; the
default marker/PathNode height is `48.0`.

**Candidate-pair distance bound**: `createPaths` only attempts a connection between two
`NavigationPoint`s within squared straight-line distance **16384 (128²)** on its near pass, extended
to **640000 (800²)** on its extended `TestReach` pass — an effective maximum node spacing of roughly
800 uu.

**The trace** dispatches on the scout's `Physics` mode via `APawn::Reachable(Dest)`
**[DISASM Engine.dll 0x17d8f0]**:
- `walkReachable` **[0x1846e0]** — steps the scout's collision **cylinder** from start toward end in
  segments of `MAXTESTMOVESIZE = 128.0` (base step `16.0`), applying gravity/step-up/max-fall with a
  slope-parabola constant of `0.8`, capped at roughly 100 iterations; success sets `R_WALK`.
- `flyReachable` / `swimReachable` / `jumpReachable` **[0x1822c0 / 0x183c90 / 0x182c50]** set
  `R_FLY`/`R_SWIM`/`R_JUMP`; jump uses a max jump height of roughly `48.0` and hands off landing to
  `walkReachable`.

This is confirmed to be a **cylinder trace consuming the scout's collision size against world
geometry** — i.e. genuinely dependent on the built BSP's collision (§9), not a pure line-of-sight or
graph-distance heuristic — but the specific low-level primitive it calls (whether this routes through
`BoxLineCheck`/`LeafHulls`, §9.2, the same way pawn movement does, or a separate sweep routine) is not
named by instruction in the source material read for this section; treat "traces against built
collision" as confirmed and "which exact collision primitive" as open (§18).

**Stored cost** (`FReachSpec.Distance`) is the straight-line Euclidean distance
`(End.Location - Start.Location).Size()` cast to `INT` — the trace decides whether an edge *exists*,
not its stored cost. Multi-hop composition (`FReachSpec::operator+`, `Engine.dll 0x193a20`):
`Distance=a+b`, `Radius=min(a,b)`, `Height=min(a,b)`, `flags=a|b`.

**Special hardcoded edges** (`addReachSpecs`, `Engine.dll 0x1770a0`): a Lift's `LiftCenter→LiftExit`
edge is hardcoded `Distance=500, Radius=60, Height=60, flags=R_SPECIAL`; Teleporter/WarpZone edges
also carry `R_SPECIAL`, bypassing the trace entirely.

### 11.4 `ReachFlags` bit constants

| Flag | Value | Confidence |
|---|---|---|
| `R_WALK` | 1 | [DISASM] `walkReachable` sets it directly |
| `R_FLY` | 2 | [DISASM] `flyReachable` sets it directly |
| `R_SWIM` | 4 | [DISASM] `swimReachable` sets it directly |
| `R_JUMP` | 8 | [DISASM] `jumpReachable` sets it directly |
| `R_DOOR` | 16 | [INFERRED] — standard UE1 enum shape, not independently binary-confirmed |
| `R_SPECIAL` | 32 | [DISASM] `addReachSpecs` writes it for Lift/Teleporter/WarpZone edges |
| `R_PLAYERONLY` | 64 | [INFERRED] — standard UE1 enum shape, not independently binary-confirmed |

5 of 7 bits are disassembly-confirmed; `R_DOOR`/`R_PLAYERONLY` remain inferred only (§18). Membership
test `FReachSpec::supports(r, h, flags)` **[DISASM Engine.dll 0x11aa40]**: an edge serves a query
pawn iff `spec.CollisionRadius>=r && spec.CollisionHeight>=h && (spec.reachFlags & flags)==flags`.

### 11.5 `LOWOPT` / `HIGHOPT`

Maps to `opt=0`/default `opt=1`/`opt=2`, passed straight through as `buildPaths`'s second argument
into `createPaths(opt)`. **What `opt` actually changes inside `createPaths` was not decoded by the
sources read** — no branch gated on `opt` was disassembled — this is confirmed only as a numeric
pass-through, not as a described algorithmic difference (§18).

### 11.6 Pruning

`Prune` **[DISASM Engine.dll 0x176790]**: for each node `N`, for every incoming `A→N` and outgoing
`N→B` pair, if a direct edge `A→B` already exists and the two-hop route is nearly as good — the
decoded rule is `combined(A→N→B).Distance <= 1.2 × direct(A→B).Distance` and the direct edge adds no
reachability the combined route lacks — the direct edge is pruned: `bPruned=1`, removed from
`A.Paths[]`/`B.upstreamPaths[]` (shift-compacted, `-1`-filled) and appended to `A.prunedPaths[]`.
Pruned specs **stay in the array** (kept as an AI expensive-path fallback) but are excluded from the
primary `Paths[]` walk routing uses.

### 11.7 Geometry dependency and survival across `MAP REBUILD`

**Path building requires the already-built BSP** — the reachability trace runs "against the built
level BSP", strictly downstream of geometry build, the same ordering constraint as lighting (§10).

**Survival across `MAP REBUILD`**: `dev/docs/unrealed/commands.md` states paths are not wiped by
`MAP REBUILD`, unlike lighting. The read sources support this **structurally, not by a direct
disassembly citation of the rebuild routine**: `ULevel.ReachSpecs` (`ULevel+0x8c`) is serialized
directly on the `ULevel` object itself (`ULevel::Serialize`, `Engine.dll 0x16a660`), **not** inside
the `Model`/BSP object — whereas lighting data (`LightMap`/`LightBits`) lives *inside* `UModel`
(`+0xa8`/`+0xb4`, §10.4), the object `MAP REBUILD`/`csgRebuild` reconstructs (§2). Since a geometry
rebuild reconstructs the `Model` `ULevel.ModelRef` points at but does not itself touch the separate
`ULevel.ReachSpecs` array, survival is the structurally consistent outcome — but this is an inference
from where each data structure lives, not a cited instruction confirming the rebuild routine
deliberately preserves `ReachSpecs` (§18).

`ULevel` load performs no path validation or rebuild on its own; reachspecs are consumed lazily only
by AI (`findPathToward`/`Reachable`) — several real shipped levels ship with `ReachSpecs.Count==0`
and load/play fine for a human, with AI navigation simply absent (falling back to direct
movement/idle) rather than the level failing to load.

### 11.8 Ground-truth numbers

A real shipped level (`01_NYC_UNATCOIsland.dx`) carries **12,514 reachspecs**, decoded byte-exact — the
largest of a 100-real-map round-trip corpus, all 100/100 byte-exact (spanning a 22-actor test map up
to the 12,514-reachspec level above). No path-*node*-count ground truth was found in the sources read
(only the edge/reachspec count above).

### 11.9 Confidence notes

Strong: `FReachSpec`'s on-disk layout (100/100 real maps byte-exact), 5 of 7 `ReachFlags` bit values,
`definePaths`/`createPaths`/`Prune` pipeline order and the `Prune` criterion, the scout-sweep
mechanism and its numeric constants, the special hardcoded Lift/Teleporter/WarpZone edges. Weaker/
explicitly open: `R_DOOR`/`R_PLAYERONLY`'s exact values (inferred from convention only),
`LOWOPT`/`HIGHOPT`'s actual internal effect (numeric pass-through confirmed, algorithmic difference
not decoded), which exact low-level collision primitive `Reachable`'s trace calls, the per-node
`Paths[16]`/`upstreamPaths[16]`/`prunedPaths[16]` array's on-disk property-tag encoding, and the
paths-survive-`MAP REBUILD` claim's mechanism (structural inference, not a direct rebuild-routine
citation).

---

## 12. Serialized `UModel` on-disk format

`FBspNode` (0x40 bytes in memory; ~43 bytes typical serialized size, varies with compact-index
encoding) **[BYTE-DIFF against `DXOnly.dx`; `sections/50-model-ondisk-layout-and-render.md`]**:

| Field | Encoding | In-memory offset |
|---|---|---|
| `Plane` (X,Y,Z,W) | 4×f32 | `+0x00` |
| `ZoneMask` | u64 | `+0x10` |
| `iVertPool` | compact index (ci) | `+0x18` |
| `iSurf` | ci | `+0x1c` |
| `iChild[0]` (BACK) | ci | `+0x20` |
| `iChild[1]` (FRONT) | ci | `+0x24` |
| `iPlane` (coplanar chain next) | ci | `+0x28` |
| `iCollisionBound` | ci | `+0x2c` |
| `iRenderBound` | ci | `+0x30` |
| `iZone[0]`, `iZone[1]` | byte, byte | `+0x34`, `+0x35` |
| `NumVertices` | byte in memory; ci on disk | `+0x36` |
| `NodeFlags` | byte | `+0x37` |
| `iLeaf[0]`, `iLeaf[1]` | i32, i32 (fixed-width, NOT ci) | `+0x38`, `+0x3c` |

`FBspSurf` stride 0x40 bytes: `Texture` ref at `+0x0`, `PolyFlags` (u32) at `+0x4`, plus `pBase`,
`vNormal`, `vTextureU`, `vTextureV`, `iLightMap`, `iBrushPoly`, `iZone[0..1]`, `iActor` (exact
serialized field order and count not independently re-derived by this evidence pass beyond `+0x0`/
`+0x4` — treat other `FBspSurf` field offsets as needing direct re-verification before depending on
them).

`FBspVert`: `ci(iVertex) + ci(iSide)`, `iVertex` indexes `Points`, `iSide` is a shared-edge id from
`bspOptGeom` §6.3 (`-1`=unlinked). Followed on disk by `Model.NumSharedSides` (i32).

`FBspLeaf` stride 0x14 bytes: `iZone`, `iPermeating`, `iVolumetric`, `iExclusive` (u64).

`FZoneProperties` (the `Zones[64]` array, `UModel+0x104`, stride 0x18): `ZoneActor` ref at `+0`,
`Connectivity` (u64) at `+0x8`, `Visibility` (u64) at `+0x10` — confirmed via three independent
serializer/`EmptyModel`-init sites.

Trailing `UModel` array serialization order, confirmed by hand-decoding a real `.dx`: … → `Zones` →
`Polys` (object ref) → `LightMap` (`TArray<FLightMapIndex>`, 32 B/elem) → `LightBits`
(`TArray<BYTE>`) → `Bounds` (`TArray<FBox>`, 25 B serial / 28 B in-memory, base `Model+0xc0`) →
`LeafHulls` (`TArray<INT>`, base `Model+0xcc`) → `Leaves` → an unidentified trailing int array
(portal/leaf-node list — not independently identified) → tail `RootOutside` (`Model+0xf0`), `Linked`
(2×i32).

Ground-truth byte-diff of a real `Test_Castle.dx` (249,287 B body) vs a hand-reconstruction, section
by section, established real per-section sizes/counts: Nodes 54,034 B/1156 elems, Surfs 8,930 B/485,
Points 24,422 B/2035, Bounds 12,102 B/484 (confirms 25.0 B/elem), LeafHulls 15,466 B/3866 ints, Leaves
4,585 B/384. Only `NumZones` (4 B) and the trailing `RootOutside`/`Linked` (8 B) were byte-identical
between the two files at the raw positional level; everything else differed in node-emit order and
object-table renumbering even where the underlying multiset content matched (plane multiset was
1156/1156 identical; first positional divergence at node 51) **[BYTE-DIFF;
`sections/82b-ground-truth-byte-diff.md`]**.

**Structural fact, independently confirmed:** BSP split planes are serialized inline as 4 floats per
node (`FBspNode.Plane`) and **never** populate the `Vectors` array — only `FBspSurf.vNormal`/
`vTextureU`/`vTextureV` reference `Vectors`.

### 12.1 Export/import table ordering — NOT (yet) shown to be a deterministic function of the trunk

This is the single largest known obstacle to whole-*package* byte-exactness, separate from every
geometry/lighting/paths algorithm question in §1-§11 — those describe the `UModel`/`ULevel` payload
content correctly; this is about the numbering of the package's own **export table** (every object
the package defines, including every Brush actor and every referenced texture) that fields like
`FBspSurf.iActor`/`texture_ref` index into.

**Measured** (per-field byte-diff of the real, editor-built `Test_Castle.dx`'s 485-entry `Surfs`
section against a structurally-correct reconstruction of the same content) **[BYTE-DIFF;
`sections/83-surf-ref-order-session-artifact.md`]**: every *geometric* surf field
(`vNormal`/`vTextureU`/`vTextureV`/`iLightMap`/`iBrushPoly`/`iZone`/`poly_flags`) is **100% byte-exact
(485/485)**. Only two fields diverge, both **object-table index fields**, both **0% positional
match**: `iActor` (the owning brush's export-table index) and `texture_ref` (an import-table index).
In both cases the field resolves to the **correct referent by name** (485/485 for both) — the object
being referenced is right, only the **table position** the editor assigned it differs.

**The divergence is not explainable by any trunk-derivable ordering rule tested:**
- Export order is not `Actors[]`/trunk order (`LevelInfo0`, `Actors[0]`, is export #8; the brush
  block is non-contiguous in the export table).
- It is not name-hash order and not lexicographic order (same-name-prefix, random-suffix actors
  *cluster* in the table, which is inconsistent with a hash, but the order within a cluster isn't
  alphabetical either).
- A sweep of every deterministic-from-trunk candidate ordering topped out at **~40%** raw match; the
  editor's own actual brush order, merely compacted to small indices (i.e. "what if this were the
  right order, just re-based"), reaches **~92%** — meaning the *ordering itself*, not an offset or
  base, is the gap, and no trunk-derivable rule reproduces that ordering.

**The open, load-bearing question** (this measurement is against a **hand-authored** `.dx` — a map
edited over a long session of CSG rebuilds, moves, and paste-duplications, whose export order plausibly
reflects that editing *history*, not a clean deterministic function of final content): would a **clean
`MAP IMPORT`** of a T3D trunk into a fresh level produce export/import tables in trunk order (or some
other deterministic order), unlike a hand-edited map's accumulated-history order? **This is untested**
— no editor-materialized-from-a-clean-trunk `.dx` was produced and compared. It is the single
experiment that would settle whether whole-package byte-exactness is reachable via a deterministic
export-order rule, or whether it requires reproducing the exact sequence of editor operations a map
was authored with (not generally recoverable from a T3D trunk alone).

**A related, distinct residual**: the `Points` pool itself (§3.10's dedup algorithm, correctly
decoded) was measured, in the same comparison, to genuinely differ in *membership*, not just
order — 484 points present only in the editor's pool, 133 only in the reconstruction's, 1551 shared
(i.e. neither a subset nor superset of the other) — consistent with §3.10's point that
`FindNearestVertex`'s dedup rule is order-sensitive: getting the rule right is not sufficient if the
proposal order (every upstream step, exactly) doesn't also match.

**[OPEN]** — carried into §18 and §20.

---

## 13. Float32 precision — reproducibility requirements

**Build provenance, decisive, not inferred:** `Editor.dll`/`Engine.dll`/`core.dll` all report MSVC
linker version 14.32 (Visual Studio 2022) and `TimeDateStamp` 2022-10-29 — this is a **2022 MSVC
rebuild**, not the 1999 retail original **[DISASM; `41-fp-model-x87-vs-sse.md`]**. 32-bit MSVC has
defaulted to `/arch:SSE2` since VS2012, so scalar float arithmetic compiles to `movss`/`addss`/
`mulss`/`divss`/`comiss` on XMM registers, each rounded to IEEE-754 binary32 immediately — no 80-bit
x87 extended-precision accumulation chain.

**Whole-`.text` census** (both DLLs): 15-21 stray x87 arithmetic instructions total (attributable to
linear-sweep mis-decode of embedded data, not real FP code), **zero** `fldcw`/`fnstcw` (rules out any
precision-control-word trick), thousands of SSE-scalar and SSE-packed instructions, **zero FMA**
(rules out fused-multiply-add reordering). SSE-to-x87 ratio ≈2600:1.

**Per-site verdicts, all SSE scalar unless noted:**
- `FPlane::PlaneDot` **[Core.dll 0x24e60]**: a specific packed-then-horizontal-reduce shuffle
  sequence (`mulps`/`shufps 0xb1`/`addps`/`movhlps`/`addss`), not a naive left-to-right dot product —
  a faithful port must match this exact reduction shape, not just the mathematical result.
- `SplitWithPlane`/`SplitWithPlaneFast` classify: SSE `comiss` vs `±0.25`/`±0.01`.
- Split-parameter division: `divss` — IEEE-correct, bit-identical to any correct `f32/f32`.
- `CalcNormal` (Newell's method): SSE, delegates normalization to `NormalizeSlow`.
- **`FVector::NormalizeSlow`** **[Core.dll 0x249d0]** — the path `CalcNormal` actually uses for surf
  normals: squared length in f32, widened to f64 (`cvtps2pd`), **`sqrtsd`** (f64 sqrt), narrowed back
  to f32 (`cvtsd2ss`), then an f32 `divss` reciprocal. No rsqrt approximation, no x87. Exactly
  reproducible as `((sumsq as f64).sqrt() as f32)` then `1.0f32 / that`.
- `FindNearestVertex` (point-pool dedup): descent pruning on squared distance (no sqrt), but the
  accept test on the winning candidate uses a real distance via `appSqrt` (f64 `sqrtsd` → f32)
  compared against the real (not squared) `0.002`/`0.015` thresholds.
- `FindBestSplit`'s score: integer-dominant; the only fractional term is `PortalBias/100.0`
  (`cvtdq2ps`+`divss`).

**One residual x87 site found, and why it doesn't matter here:** `FVector::Normalize`
**[Core.dll 0x24940]**, a *different* function from `NormalizeSlow`, does use genuine 80-bit
`fld1;fdivrp;fstp` for its reciprocal. But `CalcNormal` (the surf-normal path) calls `NormalizeSlow`,
not `Normalize` — so stored surf normals are unaffected by this x87 site. Flagged as a residual that
should be cross-referenced to confirm no CSG-build caller reaches `Normalize` instead.

**Rotation-table precision artifact — a distinct, real source of float32 error, gated on any
rotated/scaled brush.** UnrealEd's rotation trig table (`GMath.TrigFLOAT[8192]`, used by every
`ABrush::BuildCoords` call, §3.1a) is built as `_TRIG[k] = f32(sin(f32(k·2π/16384)))` — **the angle
argument is cast to float32 BEFORE calling `sin`, not after** — affecting the majority of entries
(8973 of 16384). Lookup: `gmath_sin(uu) = _TRIG[(uu>>2) & 16383]`, `gmath_cos(uu) =
_TRIG[((uu>>2)+4096) & 16383]` (the known UE1 `CosTab` formula). Numeric fingerprint:
`sin(180°)` in this table is `-8.742278e-08`, not the exact `0.0` a double-precision `sin(π)` gives.
A directly observed real-world consequence: a real 180°-yaw brush (`Brush639`) in the real UNATCO
level produces a plane offset of `-311.99997` (exactly 1 float32 ULP off the mathematically exact
`-312.0`) in the real editor's own committed BSP tree, traceable directly to this table's
float32-precast-then-`sin` construction **[DISASM, LIVE gdb bit-dump of the real committed tree;
`sections/92-bspbrushcsg-reallevel-port-plan.md:1566-1569,1602-1607`]**. A faithful reimplementation
must build its own trig lookup table with this exact precast-then-`sin` order, not a mathematically
"more accurate" double-precision `sin`, to reproduce real rotated-brush geometry bit-for-bit.

**Stated conclusion of the evidence:** bit-exact geometry reproduction is reachable using plain
IEEE-754 `f32` arithmetic end-to-end — an extended-precision (f64/f80) emulation layer would be
*wrong*, not merely unnecessary. The remaining risk for a faithful port is matching each operation's
**exact instruction-level reduction order** (e.g. `PlaneDot`'s specific shuffle-based horizontal sum,
or the trig table's precast order), not a precision-model gap.

**[DISASM; `41-fp-model-x87-vs-sse.md`, `re-raw-zones/fp-classification-sites.md`,
`81-phase0-feasibility.md`, `sections/92-bspbrushcsg-reallevel-port-plan.md`]**

---

## 14. Ground-truth reference numbers (for validating a reimplementation)

All captured by actually driving a real UED22 editor session (`MAP REBUILD; BSP REBUILD OPTIMAL
OPTGEOM ZONES`, or equivalent) and reading its output, or by structurally parsing a real shipped
`.dx` — not from any reimplementation **[LIVE, BYTE-DIFF]**.

| Level | Actors | Nodes | Surfs | Points | Verts | Zones | Leaves | Bounds | LeafHulls |
|---|---|---|---|---|---|---|---|---|---|
| Castle (`Test_Castle.dx`) | 95 Brush + 62 Light + 1 ZoneInfo + 1 SkyZoneInfo + 1 PlayerStart + 1 LevelInfo | 1156 | 485 | 2035 | 16,163 | 4 | 384 | 484 | 3866 (ints) |
| UNATCO batch golden (734 brushes, `BSP REBUILD OPTIMAL OPTGEOM ZONES`) | — | 6859 | 3616 | — | — | 7 | — | 3641 | — |
| UNATCO shipped (`03_NYC_UNATCOHQ.dx`) | — | 5188 (2890 solid / 2251 semi / 47 other) | 3589 | 9671 | 82,487 | 7 | 2266 | 3142 | — |
| Catacombs (`10_Paris_Catacombs.dx`) | 1283 Brush + 18 DeusExMover of 2710 | 11,420 | 6491 | 19,570 | 174,458 | 17 | 4485 | 6012 | 48,321 |
| HK Market (`06_HongKong_WanChai_Market.dx`) | 1304 Brush + 23 DeusExMover | 11,849 | 5224 | 17,115 | 174,179 | **5** | 3800 | 4839 | 43,545 |

**UNATCO rebuild-command sensitivity** (§1.1's table repeated for reference — the same 734-brush level,
three different command sequences): bare `MAP REBUILD` → 6314 nodes/3616 surfs/599 vectors (stale
leaves, 9.45 refs/leaf); `+ BSP REBUILD GOOD OPTGEOM ZONES` → 7273 nodes; `+ BSP REBUILD OPTIMAL
OPTGEOM ZONES` → 6859 nodes — surfs and vectors identical (3616/599) across all three.

Notes on reading this table:
- Castle's batch-golden and the shipped file are **99.89% raw-positional-byte-identical**, 70.17% of
  sections fully byte-identical; the differing sections (Nodes/Surfs/Lights) differ only in embedded
  object-reference renumbering, not in geometry — the topology numbers above are shared by both files
  **[BYTE-DIFF; `sections/90-castle-ued-rebaseline.md`]**.
- UNATCO's batch-golden vs its shipped file diverge substantially (Nodes higher in the batch golden,
  Leaves lower) purely from **build procedure**: the shipped file was built incrementally by a human
  over time, the golden by one batch rebuild of the same final geometry. This is a genuine fact about
  the editor — identical final brush geometry does not guarantee identical BSP topology if the *build
  history* differs **[LIVE; `sections/89-ued-golden-pipeline.md:111-134`,
  `sections/92-bspbrushcsg-reallevel-port-plan.md:98`]**.
- HK Market's 5 zones despite 1330 densely-packed brushes and no explicit extra `ZoneInfo` actors is a
  real fact about the editor's zone-merging behavior on dense additive geometry, not a bug in any
  measurement **[LIVE; `sections/85-hkmarket-parity.md`]**.
- A **world-only, unlit** batch build is the correct parity target for geometry-only comparison. A
  full-trunk build (including point actors whose classes fail to resolve without the full game content
  loaded) can silently CSG-in extra brush-bearing actors (e.g. `DeusExMover`, which carries its own
  brush) as plain world geometry — measured contamination on the castle trunk: 7669 nodes / 3860 surfs
  (full+lit) vs 6314 / 3616 (world-only, note: bare `MAP REBUILD` numbers) — a 21%+ inflation from
  actors that should never enter world CSG at all **[LIVE; `sections/89-ued-golden-pipeline.md:70-81`]**.
- The real castle CSG-root poly soup, immediately before final repartition, is **853 polys**, producing
  the final 1156-node/485-surf/26-vector/384-leaf/4-zone tree
  **[LIVE; `sections/92-bspbrushcsg-reallevel-port-plan.md:15-17`]**.

**Determinism**: two independent batch builds of the same trunk, driven with the identical command
sequence, are 100.00% Model-body byte-identical (§1.3) — the real editor's build given identical input
*and identical commands* is a reproducible fixed point, so any divergence between a reimplementation
and a golden capture is a fidelity gap in the reimplementation, not build-to-build noise. (This does
NOT mean different *commands* — e.g. `MAP REBUILD` alone vs plus `BSP REBUILD` — converge to the same
result; §1.1 shows they don't.)

---

## 15. Binary map (consolidated function/RVA table)

All addresses are file RVAs as `pefile` reports them (ImageBase `0x10000000` for every DLL below;
subtract nothing further).

| Function | Module | VA | Role |
|---|---|---|---|
| `UEditorEngine::csgRebuild` | Editor.dll | `0x4a650` | per-brush CSG loop driver (§2) |
| `UEditorEngine::Rebuild` (`MAP REBUILD`) | Editor.dll | `0x65a40` | console entry point (§1.1) |
| `BSP REBUILD` exec parser | Editor.dll | `0x65220` | console entry point, quality/keyword parsing (§1.1-1.2) |
| `bspValidateBrush` | Editor.dll | `0x37290` | per-brush pre-CSG link/watertightness pass (§3.0) |
| `UEditorEngine::bspBrushCSG` | Editor.dll | `0x355e0` | apply one brush's CSG (§3) |
| `ABrush::BuildCoords` | Engine.dll | `0x111390` | brush→world transform construction (§3.1a) |
| `FPoly::Transform` | Engine.dll | `0x152360` | apply the transform to a poly (§3.1a) |
| `FilterEdPoly` | Editor.dll | `0x32bf0` | tree-descent classify recursion (§3.2) |
| `FilterLeaf` | Editor.dll | `0x33130` | terminal classification (§3.2-3.3) |
| `FBspNode::IsCsg` | Editor.dll | `0x33b80` | node-solidity predicate (§3.2, §7.1, §9.1) |
| `AddBrushToWorldFunc` | Editor.dll | `0x31770` | Add leaf callback, Pass 1 (§3.4) |
| `SubtractBrushFromWorldFunc` | Editor.dll | `0x348c0` | Subtract leaf callback, Pass 1 (§3.4) |
| FWTB leaf callback (Add) | Editor.dll | `0x31b90` | Pass 2 re-add/discard (§3.4) |
| FWTB leaf callback (Subtract) | Editor.dll | `0x34980` | Pass 2 re-add/discard (§3.4) |
| `FilterWorldThroughBrush` post-filter reconcile | Editor.dll | `0x3348b` | keep-vs-rollback (§3.4) |
| `bspCleanup` / `CleanupNodes` | Editor.dll | `0x36160` / `0x32100` | per-brush dead-node splice (§3.5) |
| `bspNodeToFPoly` | Editor.dll | `0x365b0` | rebuild an FPoly from a stored node (§3.7, §7.2, §7.4) |
| `bspAddNode` | Editor.dll | `0x34e80` | add one node+surf, >16-vert storage split (§5.1) |
| `SplitPolyList` | Editor.dll | `0x34530` | partition recursion (§5.1) |
| `FindBestSplit` | Editor.dll | `0x335d0` | partition heuristic (§5.2) |
| `bspBuild` | Editor.dll | `0x35ef0` | tree-build driver (§5) |
| `bspRepartition` | Editor.dll | `0x49fc0` | world-repartition wrapper, hardcoded params (§5.3) |
| `bspRefresh` | Editor.dll | `0x36cd0` | array GC (§6.1) |
| `bspMergeCoplanars` | Editor.dll | `0x36200` | coplanar-fragment merge (§6.2) |
| `FPoly::TryToMerge` | Editor.dll | `0x34b10` | pairwise poly merge (§6.2) — note: Editor.dll, not Engine.dll |
| `bspOptGeom` | Editor.dll | `0x36870` | T-junction elim + shared-side link (§6.3) |
| `AddPointLink` | Editor.dll | `0x325e0` | bspOptGeom pass-1 descent (§6.3) |
| `UEditorEngine::TestVisibility` / `portalize` | Editor.dll | `0xaa940` / `0xaa370` | zone/portal driver (§7) |
| `AssignLeaves` (Pass A) | Editor.dll | `0xa7760` | leaf enumeration (§7.1) |
| `MakePortals` (Pass B) | Editor.dll | `0xa9750` | portal graph (§7.2) |
| `BuildInfiniteFPoly` | Editor.dll | `0xa7ae0` | portal quad construction (§7.2) |
| `MakePortalsClip` | Editor.dll | `0xa9970` | ancestor-clip (§7.2) |
| `FilterThroughSubtree` | Editor.dll | `0xa9030` | 2-phase leaf-pair finder (§7.2, §7.4) |
| `AddPortal` | Editor.dll | `0xa72a0` | portal record allocation (§7.2) |
| `BlockPortal` | Editor.dll | `0xa7870` | zone-barrier stamping (§7.2) |
| `AssignZones` (Pass C) | Editor.dll | `0xa93c0` | zone flood (§7.3) |
| `AssignAllZones` (Pass D) | Editor.dll | `0xa7400` | per-node zone stamp (§7.4) |
| `BuildZoneMasks` (Pass E) | Editor.dll | `0xa8850` | `ZoneMask` OR-recurrence (§7.5, §8) |
| `BuildConnectivity` (Pass F) | Editor.dll | `0xa7960` | `Zones[].Connectivity` (§7.5) |
| `BuildZoneInfo` (Pass G) | Editor.dll | `0xa7e60` | `Zones[].ZoneActor` binding (§7.5) |
| `bspBuildBounds` | Editor.dll | `0xaace0` | render bounds + collision hulls driver (§8) |
| `FilterBound` | Editor.dll | `0xa8a40` | recursive bound/hull worker (§8) |
| `SplitPartitioner` | Editor.dll | `0xaa000` | hull-face plane tagging (§8) |
| `UpdateBoundWithPolys` | Editor.dll | `0xaaa20` | air-side AABB accumulate (§8) |
| `UpdateConvolutionWithPolys` | Editor.dll | `0xaaae0` | solid-side hull emit (§8) |
| `FPoly::SplitWithPlane` | Engine.dll | `0x1518b0` | poly split/classify vs plane, precise (§5.4) |
| `FPoly::SplitWithPlaneFast` | Engine.dll | `0x151f90` | classify-only, used by `FindBestSplit` (§5.2, §5.4) |
| `FPoly::SplitWithNode` | Engine.dll | (not independently pinned) | used by zone/portal filtering (§7.2, §7.4) |
| `FPoly::Fix` | Engine.dll | `0x150da0` | near-duplicate vertex collapse (§4) |
| `FPoly::RemoveColinears` | Engine.dll | `0x151090` | coincident+colinear vertex removal (§4) |
| `FPoly::CalcNormal` | Engine.dll | `0x150510` | normal + zero-area detection (§4, §3.7) |
| `FPoly::Finalize` | Engine.dll | `0x150ac0` | the face-survival gate (§4) |
| `FPlane::PlaneDot` | Core.dll | `0x24e60` | signed point-plane distance (§9, §13) |
| `FVector::NormalizeSlow` | Core.dll | `0x249d0` | f32→f64-sqrt→f32 normalize, used by `CalcNormal` (§13) |
| `FVector::Normalize` | Core.dll | `0x24940` | x87-based normalize, NOT the surf-normal path (§13) |
| `UModel::LineCheck` | Engine.dll | `0xf3c20` | collision dispatcher (§9) |
| Zero-extent line check | Engine.dll | `0xf3560` | (§9.1) |
| `BoxLineCheck` | Engine.dll | `0xf42f0` | pawn/actor sweep collision (§9.2) |
| `UModel::PointCheck` | Engine.dll | `0xf19b0` | point/box overlap, hull-optional (§9.2) |
| `UModel::PointRegion` | Engine.dll | `0xf5db0` (cross-ref) | which zone a point is in |
| `UObject::SavePackage` phases | core.dll | (string-extracted) | `MAP SAVE` mechanics (§1.4) |

---

## 16. Confidence summary by subsystem

| Subsystem | Confidence |
|---|---|
| `csgRebuild` top-level sequence | [DISASM], corroborated across two independently-dated spikes |
| `bspValidateBrush` pre-CSG link pass | [DISASM], single decode, watertightness-logging behavior cross-cited from a second, independent spike |
| `bspBrushCSG` control flow, LOOP1/LOOP2, temp-BSP+FWTB structure, convex-seed shortcut | [DISASM] + [LIVE gdb] cross-checked twice independently, consistent |
| Per-operator (Add/Subtract) leaf-survival tables | [DISASM], but see the open §3.3 label-numbering conflict between two sources |
| Coplanar/cospatial 4-way classification mechanism | [DISASM] + [LIVE differential] for the seeding rule; the exact 4-vs-5 label mapping is [OPEN] |
| Intersect/Deintersect two-phase algorithm | [DISASM], single source, internally consistent, not independently cross-checked by a second decode |
| Normal computation/storage (Add=authored, Subtract=recomputed) | [DISASM] + [LIVE gdb breakpoint evidence, multiple independent breakpoint sites] — very strong, the most heavily re-verified mechanism in this document |
| `FPoly::Finalize`/`Fix`/`RemoveColinears`/`CalcNormal` | [DISASM], address-cited for every threshold |
| `SplitPolyList`/`bspAddNode` node-emission rule (no bevel/leaf-bound pass) | [DISASM], corroborated by a second independent decode pass, explicitly overturns an earlier working hypothesis |
| `FindBestSplit` scoring, stride, tie-break | [DISASM], byte-verified with a committed re-assertable harness (24/24 checks); GOOD-mode real-content failure case [LIVE]-measured |
| Which `(Balance,PortalBias,Opt)` triple the console `MAP REBUILD`/`BSP REBUILD` verbs actually drive | [OPEN] for the exact mechanism, but [LIVE]-proven that the two commands produce genuinely different node trees |
| Whether `MAP REBUILD` alone runs `bspOptGeom`/zones | zones: [LIVE]-confirmed does not run (two independent live sessions); `bspOptGeom`: still [OPEN] |
| `bspOptGeom` (T-junction elim + shared-side link) | [DISASM] + [BYTE-DIFF] byte-exact against a real golden — high confidence |
| `bspMergeCoplanars`/`TryToMerge` | [DISASM], single decode, internally detailed and consistent |
| Zone/portal pipeline (Passes A-G) | [DISASM], cross-checked live against real shipped maps for several passes (leaf-flood, connectivity, visibility-field), `RootOutside` ground-truth confirmed |
| `bspBuildBounds`/`FilterBound`/`LeafHulls` | [DISASM] + [BYTE-DIFF] against a real golden |
| Collision: zero-extent LineCheck | [DISASM] |
| Collision: `BoxLineCheck` requiring `LeafHulls` | [DISASM] + [LIVE A/B test] — strong |
| `UModel` on-disk field layout | [BYTE-DIFF] for `FBspNode`/`FBspVert`/array ordering; `FBspSurf`'s full field list beyond the first two fields is **not independently re-verified** by this evidence pass |
| Float32/SSE determinism of the real DLLs | [DISASM] whole-binary census — very strong, decisive (2022 SSE2 rebuild, zero FMA, zero fldcw); trig-table precast artifact [LIVE]-confirmed on real rotated content |
| Ground-truth topology numbers (§14) | [LIVE] + [BYTE-DIFF], multiple real levels, cross-validated by determinism replay |
| GUI `Build` dialog → exec-string dispatch (§1.5) | [DISASM] direct wide-string extraction from `unrealed.exe`, cross-confirmed by `Editor.dll`'s exec-parser arg-key vocabulary — strong for *which strings get sent*; the `15`/`70` GUI default-slider-value reading is [DISASM]-suggestive but not confirmed to instruction level (would need a dialog-resource-table parse) |
| Lighting bake: bit-not-intensity storage model, `LightBits` byte encoding, lumel-grid formula | [DISASM] + [BYTE-DIFF], byte-exact against real `.dx` files (484/484 grid records, zero-exception byte-span reconciliation) — very strong |
| Lighting bake: per-leaf permeating-light flood (`ActorVisibility`) | [DISASM], single decode, internally detailed; the front-of-plane test's *mechanism* (vs its measured *effect*, 0/3497 exceptions) is [OPEN] |
| Lighting-vs-geometry-rebuild interaction (does `MAP REBUILD` wipe lighting, and how) | behavioral claim [LIVE] via `commands.md`; the mechanism is [OPEN] — not directly disassembled in either source read for §10 |
| `FReachSpec` on-disk layout, pipeline order, scout-sweep reachability trace | [DISASM] + [BYTE-DIFF], 100/100 real maps byte-exact for the layout |
| `ReachFlags` bit values | 5/7 [DISASM]-confirmed; `R_DOOR`/`R_PLAYERONLY` [INFERRED] only |
| `LOWOPT`/`HIGHOPT`'s actual algorithmic effect | [OPEN] — only the `opt=0/1/2` numeric pass-through is confirmed |
| Paths survive `MAP REBUILD`, unlike lighting | behavioral claim [LIVE] via `commands.md`; the mechanism is a structural inference (object-layout argument, §11.7), not a direct rebuild-routine citation — [OPEN] |
| `bspAddPoint`/`bspAddVector` pool dedup rule (§3.10) | [DISASM], nearest-not-first, address-cited thresholds — strong for the *rule*; whether an implementation's *proposal order* matches closely enough to reproduce the real pool is a separate, [OPEN], empirically-hard question (§20.2) |
| Export/import table ordering (§12.1) | [BYTE-DIFF] for the *measurement* (not trunk-derivable on the one map tested) — strong; the underlying *rule* (if any) is [OPEN], gated on an untested clean-reimport experiment |
| BSP repartition matching the real editor at production scale (700+ brushes) | [DISASM]-verified algorithm, [LIVE]-verified small-scale (95 brushes, byte-identical); [OPEN] and [LIVE]-**disproven** at real scale (measured 57-node surplus, root cause not pinned) — see §20.2 |

---

## 17. What this document does not establish

- **`FBspSurf`'s complete on-disk field layout and order** beyond `Texture`/`PolyFlags` at `+0x0`/
  `+0x4` — not independently re-derived here to the same level of certainty as `FBspNode`.
- **The exact move-vs-copy mechanism of `MAP SAVE`'s final `Save.tmp` → destination step** — the
  phase order is solid (string-table evidence), the actual Win32 call is not confirmed either way.
- **`SplitWithNode`'s exact return-code mapping and internal coplanarity epsilon** (used by the
  zone/portal/bounds filtering passes) — inferred from caller branch structure, not independently
  disassembled at its own definition.
- **The unidentified trailing `TArray<INT>` in the `UModel` serialization** between `Leaves` and the
  `RootOutside`/`Linked` tail (§12) — its purpose was not identified.
- **The exact resolution of the coincident Add/Subtract shared-surface normal case** (§3.7) — honestly
  reported as unresolved by the source material rather than forced to a plausible-looking answer.
- **What a geometry rebuild does to existing lighting/paths data, at the instruction level** (§10.2,
  §11.7) — both interactions are documented behaviorally elsewhere in this project but neither was
  traced to a specific instruction by the sources read for this document.
- **`LOWOPT`/`HIGHOPT`'s actual effect on path building**, and **which collision primitive the paths
  reachability trace calls** (§11.3, §11.5).
- **Why the correctly-decoded BSP repartition algorithm (§5) diverges from the real editor by dozens
  of nodes at real (700+ brush) scale**, despite matching node-for-node at small (95-brush) scale
  (§20.2) — narrowed to a soup-content difference upstream of repartition, not further pinned.
- **Whether export/import table ordering is ever a deterministic function of the trunk** (§12.1,
  §20.3) — the one experiment that would settle this (a clean re-import, diffed) was not run.

---

## 18. Open items requiring direct live verification

1. **[§1.1, §1.2, §5.3] Does `MAP REBUILD`'s `UEditorEngine::Rebuild` (`0x65a40`) call the same
   `csgRebuild` (`0x4a650`) whose own disassembled tail unconditionally runs `bspOptGeom`, or a
   different/partial path? Does the console-parsed `Balance`/`PortalBias`/quality from `BSP REBUILD`
   (`0x65220`, defaults 50/70/OPTIMAL) ever reach the world-repartition `FindBestSplit` call, given
   that call's own wrapper (`bspRepartition`) pushes hardcoded literal `Balance=12/PortalBias=0/GOOD`
   directly in its machine code (now independently confirmed twice)?** Partially answered: §1.1's
   empirical UNATCO table proves `MAP REBUILD` alone and a subsequent `BSP REBUILD` genuinely produce
   different node counts (6314 vs 6859/7273), and `BSP REBUILD GOOD` vs `BSP REBUILD OPTIMAL` also
   differ from each other (7273 vs 6859) — so *something* about the `BSP REBUILD` invocation does
   change the partition, consistent with it re-running `bspRepartition`. What remains unresolved is
   whether the console's `BALANCE=`/`PORTALBIAS=` keywords specifically have any effect, given
   `bspRepartition`'s hardcoded values. Resolve by driving `BSP REBUILD BALANCE=12 ...` vs
   `BSP REBUILD BALANCE=90 ...` on the same brush set and diffing the resulting trees; separately,
   reading `Editor.log` for `"BspOptGeom begin"` after a bare `MAP REBUILD` to settle whether that
   pass ran.
2. **[§3.3] The `F_COSPATIAL_FACING_IN`/`F_COSPATIAL_FACING_OUT` numeric-value swap between two
   source decodes.** Re-disassemble `FilterLeaf@0x33130`'s final classification table directly and
   settle which numeric value maps to which physical case, independent of either prior document.
3. **[§9.2 / broader] `BoxLineCheck`'s hull-plane-count cap** and any other undecoded edge cases in
   the box-sweep collision path beyond what §9.2 covers.
4. **[§12] `FBspSurf`'s complete serialized field list and order.**
5. **[§3.7] The coincident Add/Subtract shared-surface normal case** left unresolved by the source
   material.
6. **[§10.2, §10.9] What a geometry (`MAP REBUILD`) rebuild does to already-baked lighting data, at
   the instruction level.** `commands.md` documents the behavior (a rebuild wipes lighting), and
   `shadowIlluminateBsp`'s own self-reset on every `LIGHT APPLY` is disassembly-confirmed, but no
   source read for this document disassembles the rebuild routine's side of that interaction.
   Resolve by disassembling `csgRebuild`'s `EmptyModel` call (§2) for whether it clears
   `UModel.LightMap`/`LightBits` as part of its known Nodes/Surfs/Verts/Points/Vectors/Zones reset,
   or by baking a level, driving `MAP REBUILD` alone, and reading back `Model.LightMap`/`LightBits`.
7. **[§11.3] Which exact low-level collision primitive `APawn::Reachable`'s trace calls** — confirmed
   to consume the scout's collision size against built world geometry, not confirmed to route through
   `BoxLineCheck`/`LeafHulls` (§9.2) by name in the source material read.
8. **[§11.5] `LOWOPT`/`HIGHOPT`'s actual algorithmic effect inside `createPaths`** — only the
   `opt=0/1/2` numeric pass-through is confirmed; no branch gated on `opt` was disassembled.
9. **[§11.7] Direct disassembly confirmation that `MAP REBUILD` does not touch `ULevel.ReachSpecs`**
   — currently only a structural inference from `ReachSpecs` living on `ULevel` rather than inside
   the rebuilt `Model` object.
10. **[§1.5] Whether the `15`/`70` values found adjacent to the `Build Options` dialog's Balance/
    PortalBias slider labels are genuinely the sliders' default positions**, rather than unrelated
    nearby strings — `70` matching the independently-confirmed console default is suggestive but not
    proof; would need the dialog's compiled resource template parsed directly.
11. **[§20.2] The real-scale (700+ brush) BSP repartition over-split's root cause.** Confirmed to be a
    CSG-filtered-soup-content divergence, not a `FindBestSplit`/`SplitPolyList` algorithm defect, but
    the specific upstream mechanism was not pinned before the investigation was shelved. Resolve via
    live-`gdb` differential bisection against a real running editor building a real large map,
    comparing the exact fragment set/order reaching repartition — substantial effort (prior attempts
    span roughly 2000 lines of bisection notes without closing it).
12. **[§12.1, §20.3] Whether a clean `MAP IMPORT` of a T3D trunk produces deterministic (e.g.
    trunk-order) export/import table numbering**, unlike the session-history-dependent order measured
    on a hand-authored map. A single bounded experiment: import a trunk fresh, save, and diff the
    resulting table order against the trunk order and against the hand-authored golden's order.

---

## 19. Related, not covered

`GMath.TrigFLOAT` (§13) and `ABrush::BuildCoords`/`FPoly::Transform` (§3.1a) are covered only to the
depth needed to explain their role in per-brush transform and float32 fidelity. `AMover`'s own
private-`UModel` collision system is explicitly out of scope for this document — see
`dev/docs/spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` §3 for movers' separate
collision path. (Geometry build, lighting build, and paths build — the three scopes the GUI's `Build`
dialog exposes, §1.5 — are all now covered, §1-§9 and §12-§17 for geometry, §10 for lighting, §11 for
paths.)

---

## 20. Implementation feasibility — is this spec enough to actually build?

**Evidentiary basis for this section only, stated up front:** every other section of this document
is sourced strictly from primary UnrealEd evidence (binary disassembly, live-editor observation),
per the rule at the top of this document. This section is different in kind — it answers a
feasibility question ("if someone builds this, what happens?"), which existing primary evidence
alone cannot answer. For that question, the relevant evidence is the historical record of an actual
implementation attempt inside this codebase (`uedcli-native/`'s CSG/BSP/lighting/paths modules,
since removed) and the git history of what happened to it. This section cites that history as
implementation-outcome evidence, not as a source for any claim about UnrealEd's own internals —
every algorithmic claim anywhere else in this document still stands on its own primary citation.

### 20.1 The direct answer

**For driving the real `UnrealEd.exe`/`UCC.exe` editor** (§1-§11, §1.5's GUI-dispatch mapping): yes,
this spec is sufficient, and this is not a hypothetical — it is what this project's own architecture
settled on for its actual production `level materialize` path. A from-scratch native reimplementation
of the geometry/CSG core was built, developed for weeks, and ultimately **removed** (commit
`fbccd70`, "Remove the native materialize build path") in favor of exclusively driving the real
editor, with the removal commit's own words: *"the native materialize build path... had no CLI caller
and never reached the CSG solidity parity"* and *"flipping [`apply.run_materialize`] to the native
path as its sole path awaits full CSG parity... [an] awaiting condition that was not reached."* If the
goal is "reproduce the real editor's build output," orchestrating the real editor via the console
verbs this spec documents is the only path proven to work end-to-end.

**For a from-scratch native engine that reproduces the real editor's output with no editor at
runtime**: **not yet** — not because this spec's algorithm descriptions are wrong (the individual
mechanisms are disassembly-cited and, where tested in isolation or at small scale, byte-verified),
but because getting all of them to interact correctly, at real (hundreds-of-brushes) production
scale, has been attempted and has not yet succeeded. Three specific, characterized gaps remain, none
of them "we don't know the algorithm" — all three are "we know the algorithm and an attempt built
from it still didn't converge, for a reason not yet pinned":

### 20.2 Gap 1 — BSP repartition over-splits at real scale, root cause not identified

`SplitPolyList`/`FindBestSplit` (§5) is the single most rigorously verified mechanism in this whole
document — byte-verified with a committed, re-assertable disassembly harness (§5.2), and an
implementation built directly from that decode reproduced the real editor's tree **node-for-node** on
a 95-brush castle level (1156/1156 nodes, byte-identical Model body). At real production scale
(a 734-brush UNATCO level), the same algorithm, fed the correct CSG-filtered soup (portal handling
included), produced **6371 nodes against the real editor's 6314** — a 57-node surplus, characterized
specifically as **broad axis-aligned wall planes**, not tied to any single brush's face and not
explained by `bspOptGeom` (independently confirmed to be a GC/weld pass, not a redundant-split
trimmer — §6.3 — and separately, its own decode explicitly rules it out as a fix here: it can't
collapse an over-split tree because the surplus nodes are reachable/live, not garbage). Extensive
live-`gdb`-driven bisection against the real running editor narrowed this to "a structural divergence
in the CSG-filtered soup content feeding the repartition, not a flaw in the partition algorithm
itself" — but the exact mechanism producing that soup-content difference was not pinned before the
investigation was shelved. **This is squarely a §3 (CSG filter) or §3.10 (point/vector pool proposal
order) question, not a §5 one** — some subtlety in exactly which fragments reach the repartition step,
or in what order, differs from the real editor in a way that only shows up past a few hundred brushes.

### 20.3 Gap 2 — export/import table ordering (§12.1)

Independent of geometry correctness: reproducing a real `.dx` file byte-for-byte also requires
reproducing the package's own export/import table numbering, which every actor/texture/brush cross-
reference (`FBspSurf.iActor`, `texture_ref`, and by the same logic `Model.Lights` actor refs,
`Zones[].ZoneActor`, `FReachSpec.Start`/`End`) indexes into. §12.1 measured this is not a
trunk-derivable deterministic function on the one real map tested, and the decisive test — whether a
*clean* re-import produces trunk-order tables, unlike a hand-authored map's session-history-dependent
order — has not been run.

### 20.4 Gap 3 — lighting and paths were decoded but never build-tested

§10 (lighting) and §11 (paths) are sourced from the same caliber of primary evidence as the geometry
sections — disassembly-cited, in the lighting case byte-verified against real `.dx` files (§10.9).
But unlike geometry, a native implementation of these was never carried past a stub: the Rust modules
that once existed for lighting (824 lines) and collision/paths were deleted in the same removal
commit that ended the native geometry effort, having reached only "N-4/N-5 stub" status per that
commit's own description — i.e., **no implementation attempt within this project ever got far enough
to test §10/§11 against real output.** Their algorithmic content is well-evidenced; their
*build-feasibility* is, unlike geometry's, completely untested.

### 20.5 What this means in practice

None of the three gaps above require new disassembly to *understand the algorithm* — every mechanism
they touch is already specified elsewhere in this document. What they require is either (a) further
live-editor-driven differential investigation at real map scale (gdb-instrumented, crash-prone,
previously took weeks of dedicated effort for gap 1 alone and did not close it), or (b) the single
bounded experiment described in §12.1 for gap 2, or (c) simply attempting an implementation of §10/§11
and finding out what breaks for gap 3. None of this was attempted fresh for this document — a live
UnrealEd container is available in this environment (confirmed running), but the scale of gap 1's
own investigation (documented across roughly 2000 lines of prior bisection work, itself inconclusive)
means a proportionate next step is a dedicated, scoped follow-up — not something to rush inside this
synthesis pass. Flagged on the board rather than attempted here.

---

## 21. Evidence index

Primary disassembly/decode documents (all under `dev/docs/spikes/`):

- `2026-06-24-bsp-csg-hole-mechanism-from-binary.md` — `csgRebuild`/`bspBrushCSG` overview,
  `FPoly::Finalize`/`Fix`/`RemoveColinears`/`CalcNormal`, the `±0.25` split-band mechanism, full
  constants table.
- `2026-06-24-bspbuild-partition-heuristic-from-binary.md` and
  `2026-06-26-bsp-partition-heuristic-from-binary.md` — `FindBestSplit` full decode + byte-level
  verification harness, `SplitWithPlaneFast`, `MAP REBUILD`'s `0x65220` parser defaults.
- `2026-06-24-bsp-collision-solidity-movers-from-binary.md` — `UModel::LineCheck`/`PointCheck`
  entry points, solid/semisolid/nonsolid/portal/mover collision semantics, `bspValidateBrush`.
- `dev/docs/unrealed/extracting-from-dll.md` — the extraction methodology (wide-string tables,
  MSVC-mangled export mapping, disassembly harness) used throughout.
- `2026-07-15-native-materialize/re-raw-zones/` — `bspbrushcsg-filter-decode.md`,
  `bspbrushcsg-intersect-deintersect-decode.md`, `bspbuild-splitpolylist-decode.md`,
  `findbestsplit-params-decode.md`, `passA-leafenum-7760.md`, `passA-portalbuilder.md`,
  `passB-makeportals-9750.md`, `passC-zoneflood-93c0.md`, `passC-zonesetter.md`,
  `passD-assignzones-7400.md`, `passesBDEFG-ctor.md`, `passesEFG-8850-7960-7e60.md`,
  `bounds-and-zonelayout.md`, `linecheck-oracle.md`, `ctor-fieldmap-6970.md`,
  `fp-classification-sites.md`, `00-re-brief.md`.
- `2026-07-15-native-materialize/sections/` — `10-bsp-csg-build.md`, `82-bspbrushcsg-port-decode.md`,
  `92-bspbrushcsg-reallevel-port-plan.md`, `80-bspbuild-topology.md`,
  `42-bspoptgeom-decode.md` (top-level, not under `sections/`),
  `70-zones-portalization.md`, `87-cause2-shattered-tree.md`, `91-leaves-overproduction.md`,
  `50-model-ondisk-layout-and-render.md`, `60-leaf-solidity-collision.md`,
  `82b-ground-truth-byte-diff.md`, `82c-bounds-leafhulls-decode.md`, `89-ued-golden-pipeline.md`,
  `90-castle-ued-rebaseline.md`, `84-unatco-generalization-crosscheck.md`,
  `85-hkmarket-parity.md`, `86-catacombs-parity.md`.
- `2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md`, `81-phase0-feasibility.md`,
  `PARITY-STATUS.md` — float-determinism census and methodology status.
- `2026-07-15-native-materialize/sections/20-lighting-bake.md` (1268 lines) and
  `2026-07-15-native-materialize/re-raw-zones/lightflood-6d00.md` — full `LIGHT APPLY`/
  `shadowIlluminateBsp` decode (§10): pipeline, storage layout, `LightBits` encoding,
  `FLightMapIndex`/grid-sizing formula, the raytrace, and the per-leaf permeating-light flood.
- `2026-07-15-native-materialize/sections/30-ulevel-paths-assembly.md` (628 lines) and
  `2026-06-27-decontainerize-uedcli/05-lighting-and-paths.md` — full `FPathBuilder` decode (§11):
  `definePaths`/`createPaths`/`Prune`, `FReachSpec` layout, the scout-sweep reachability trace,
  `ReachFlags`.
- `dev/docs/unrealed/commands.md` (`## Build pipeline` section) and
  `dev/docs/unrealed/leveldesign/kb/actors-collision-pathing.md` §7 — console-verb-level facts for
  `PATHS`/`LIGHT APPLY` already documented before this item, and the file's own confidence-marker
  convention (checked and respected — §7.1's node-spacing guidance is explicitly tagged
  tutorial-corpus by the source file itself and was excluded from this document's load-bearing claims
  accordingly).
- `uned/UED22/unrealed.exe` and `uned/UED22/Editor.dll` wide-string tables — read directly (§1.5),
  not via an existing spike doc: confirms the GUI `Build` dialog's menu items, checkboxes, sliders,
  and their exact `Exec()` string templates, cross-checked against `Editor.dll`'s own recognized
  argument-key vocabulary.
- `2026-07-15-native-materialize/re-raw-zones/fp-classification-sites.md` — also the source for
  `bspAddPoint`/`bspAddVector`'s decoded dedup algorithm (§3.10), in addition to its float-site table
  already cited via §13.
- `2026-07-15-native-materialize/sections/83-surf-ref-order-session-artifact.md` and
  `sections/82b-ground-truth-byte-diff.md` — the export/import table ordering byte-diff measurement
  (§12.1): both are primary byte-diffs against a real editor-written `.dx`, not implementation
  narrative.

**§20 only** draws on a different evidentiary basis, stated in full at that section's head: the git
history and architecture-doc record of an actual (since-removed) native implementation attempt in
this codebase, cited as implementation-outcome evidence — commit `fbccd70` ("Remove the native
materialize build path") and its `dev/docs/architecture.md` diff, `PARITY-STATUS.md`, and
`sections/92-bspbrushcsg-reallevel-port-plan.md` §36/§53/§54 (the repartition over-split
investigation). No claim about UnrealEd's own internals anywhere in this document rests on that
material — only §20's feasibility assessment does.

Explicitly excluded as evidence for every claim about UnrealEd's own behavior throughout this
document: `uedcli-native/src/*.rs`, `uedcli/*.py`, and `dev/docs/board/*` (this project's own
reimplementation and its bug tracker) — see the note at the top of this document.

# OceanLab N=203: `FilterWorldThroughBrush`'s real verdict is CONSUME too — the working hypothesis is REFUTED

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/`. That session's exact next step: a live
gdb capture of UED22's real `FilterWorldThroughBrush` during `Brush482`'s own `bspBrushCSG`, to read
the real `GDiscarded` verdict for the wall face (native node 5154, plane bits `0x3f800000,0x80000000,
0x80000000,0xc3800002`) and compare against native's own CONSUME verdict. The prior session's framing:
"the live capture above now proves UED22's real answer must be [GRAZE], since the face survives all
the way to `bspOptGeom`."

**That capture ran. UED22's own `FilterWorldThroughBrush` also decides CONSUME — the working
hypothesis is REFUTED, not confirmed.** `bspcsg.rs` is unmodified.

## 1. The capture

`harness/capture_fwtb.py`: same gdb-attach recipe as `2026-09-14-oceanlab-n203-addpoint-capture/`
and `2026-09-13-crossing-vertex-live-capture/`. Instead of counting `FilterWorldThroughBrush` call
ordinals to isolate `Brush482`'s own top-level call, this stages the OceanLab N=203 subset TRUNCATED
to N=202 (verified offline this session: actors 177..202 are consecutive brushes `Brush453`..
`Brush482`, `Brush483` is actor #203) — `Brush482` is then the LAST CSG-participating brush the
build processes, so any breakpoint hit matching the wall's exact plane bits is unambiguously part of
its own recursion (no later brush can produce one).

Breakpoint: Editor.dll (nominal VA, `EDITOR_PREF=0x10000000`) `0x1003348b` — the
`cmp DWORD PTR ds:GDiscarded,0` instruction right after `FilterWorldThroughBrush`'s
`bspFilterFPoly`/leaf-func call returns, confirmed by a fresh `objdump` disassembly of
`uned/UED22/Editor.dll` this session (byte-for-byte match to the campaign's existing decode,
`dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-filter-decode.md` §5) —
`10033433: mov ds:GNode,esi` / `10033439: mov ds:GModel,edx` / `1003343f: mov ds:GDiscarded,0` at
entry, `10033483: call bspFilterFPoly` / `1003348b: cmp ds:GDiscarded,0` / `10033492: jne 0x334be`
(commit) at reconciliation. At the breakpoint, `*GModel` gives the world `UModel*`; `*(Model+0x58)`
(`Nodes.Data`, RE'd `2026-09-15-oceanlab-n203-bspoptgeom-points`) + `GNode*0x40` gives the node being
reconciled; its `Plane` (4 floats at `+0x00`) is compared against the wall's exact bits.

Result (`logs/capture.log`):

    FWTB hit=16059 gNode=5154 ... plane=(3f800000,80000000,80000000,c3800002) GDiscarded=1 verdict=CONSUME
    FWTB hit=16067 gNode=5156 ... plane=(...same...)                          GDiscarded=1 verdict=CONSUME
    FWTB hit=16068 gNode=5158 ... plane=(...same...)                          GDiscarded=1 verdict=CONSUME
    FWTB hit=16069 gNode=5160 ... plane=(...same...)                          GDiscarded=1 verdict=CONSUME
    FWTB hit=16070 gNode=5163 ... plane=(...same...)                          GDiscarded=1 verdict=CONSUME
    FWTB hit=16071 gNode=5165 ... plane=(...same...)                          GDiscarded=1 verdict=CONSUME

`gNode=5154` is UED22's OWN node index at this point (not a mapping) — it matches native's own index
exactly, confirming (as expected from N=1..202 being byte-exact) that the two trees are still
identical entering `Brush482`. Every reconciliation hit on this exact plane — node 5154 itself and
its whole coplanar-chain successors (5156/5158/5160/5163/5165, `NODE_Plane` re-add fragments sharing
the same plane) — is CONSUME. **UED22's real `FilterWorldThroughBrush`, at `Brush482`, kills this
entire coplanar chain exactly like native's does.** This is decisive, not probabilistic: `GDiscarded`
is an exact integer tally read directly from the live process.

## 2. Reconciling this with the 2026-09-15 session's Points/Surfs finding

The prior session's `bspOptGeom`-entry capture found BOTH the wall's original point (index
947/950, x-bits `0xc3800002`) and `Brush483`'s own new point (968/970, `0xc3800004`) present as
separate `Points` entries, each independently referenced by its own `Surfs` entry (1053/1055 and
1074/1076) — and concluded the wall's surf is "fully live... not a dead-node ghost." Given §1 above,
that conclusion needs correcting: **the wall's surf (1053/1055) IS a dead-node's surf in UED22's own
tree too** (its owning node dies during `Brush482`, exactly like native's) — the capture only checked
*presence in the `Surfs` array*, not whether any live node still references it. Presence in the array
does not by itself imply liveness (see §3 for what CAN legitimately keep a surf present).

This is confirmed independently, offline, by decoding the FINAL (fully built, all 203 actors, post
`bspOptGeom`/serialize) `native_N203.dx` and `ref_N203.dx` kept from this session's own `ladder_run.py
--keep-native` reproduction (`_scratch/actor-parity/14_oceanlab_lab/{native,ref}_N203.dx`):

    native: point[617] = (-256.0001220703125,    600.000244140625, -1800.0)   -- Brush483's own value
            surf[951] pBase=point[617] ... act=211
    ref:    point[612] = (-256.00006103515625,   600.000244140625, -1800.0)   -- the WALL's own value
            surf[951] pBase=point[612] ... act=47

**Only ONE point/surf survives per side in the final output — not two.** Native's survivor is
`Brush483`'s own new point; UED22's survivor is the wall's ORIGINAL point. This is consistent with
the two coexisting only TRANSIENTLY, at `bspOptGeom` entry (before its own internal
`merge_near_points` pass runs) — and with `merge_near_points` then WELDING them, in UED22's real
build, onto the wall's earlier-created point (its lower/earlier pool position plausibly wins the
tie-break). Native's own `bspoptgeom.rs::merge_near_points` never gets the chance: the wall's point
is already gone from native's pool by the time `Brush483` runs (see §3), so there is nothing there to
weld `Brush483`'s new point onto.

## 3. Where this actually leaves the investigation

This does NOT reopen `FilterWorldThroughBrush` — its classify is now doubly confirmed faithful (this
session's live capture, on top of the disassembly-level port already in `bspcsg.rs`). The divergence
is upstream of the classify decision, in what happens to a dead node's surf/point reference
AFTERWARD, before `bspOptGeom`'s own `merge_near_points` gets a chance to run — but the EXACT step is
not yet pinned, and an earlier draft of this section named the wrong one (caught by review, corrected
here):

`bspcsg.rs`'s own comment at the repartition checkpoint (`bspcsg.rs:3398-3406`) states the OPPOSITE of
what native's own `model.surfs.clear()` there might suggest: **"The editor does NOT rebuild the Surfs
pool at repartition: it keeps the INCREMENTAL-CSG pool ... and only compacts it at `bspRefresh`."**
Native's own clear+rebuild at that checkpoint is a deliberate REORDERING device (split-recursion order
is a pure permutation of the editor's real incremental-pool order), reconciled back to the editor's
true order right after via `canon_surf_keys`/`reorder_surfs_canonical` — not a port of an editor-side
Surfs rebuild. So "repartition clears a dead node's surf because the real `EmptyModel(0,0)` only keeps
live-reachable faces" is NOT an accurate description of either side's real behavior; a draft of this
section made that claim, and it is retracted.

What genuinely IS confirmed, independently, per the campaign's own comments: `bsp_refresh_points_
vectors` (`passes.rs:254`) drops any point no surviving surf's `pBase` (or live vert pool) still
references, cited against a fresh disassembly of the real `bspRefresh` (`Editor.dll 0x10036fb0`-
`0x10037166`) — this step IS independently evidenced-faithful for POINTS. Whether the wall's SURF
itself (not just its point) is still present in native's `Surfs` array by the time this runs — and by
extension whether it's `bsp_refresh_points_vectors` or something upstream of it (the soup extraction
feeding `bsp_build_fpolys`, which the repartition checkpoint's own comment implies walks only live
faces) that actually removes the wall's surf entry in the first place — was NOT checked this session.

This is the SAME "every individual step is faithful, yet the aggregate isn't" frontier the
2026-09-14 session (`dev/docs/spikes/2026-09-14-oceanlab-n203-addpoint-capture/`) already reached and
flagged as needing "a DIFFERENT live capture -- of the real editor's own `Model->Points`/
`Model->Nodes` state at the `bspBuild`/`bspRefresh` checkpoints" -- a materially larger RE task than
this session's capture, not attempted here.

## 4. Next step for whoever picks this up

Two things, in order:

1. **Offline first** (no live capture needed): trace, on native's own kept `native_N203.dx` build (or
   a fresh instrumented run), exactly which step drops the wall's dead-node SURF entry from
   `model.surfs` — is it still present in the pre-clear `canon_surf_keys` snapshot (`bspcsg.rs:3406`)
   at the `Brush482`→`Brush483` repartition boundary, or is it already gone by then (meaning the soup
   extraction feeding `bsp_build_fpolys`, not the clear+rebuild itself, is the real drop point)? This
   narrows exactly which native routine to compare against the real editor before spending a live
   capture on it.
2. **Then a live capture bracketing that exact step**: dump UED22's real `Model->Surfs`/`Points` right
   before and right after whichever real routine that step corresponds to (per-brush, starting at
   `Brush482` through `Brush483`), to see whether the wall's surf (1053/1055) is dropped there too, or
   survives and only gets welded much later at `bspOptGeom`'s own `merge_near_points`.

If UED22's real per-brush pipeline genuinely never drops a dead node's surf the way native's does
(deferring that cleanup to `bspOptGeom`/final `bspRefresh` instead), the faithful fix is in the TIMING
of native's surf/point GC relative to `bspOptGeom`'s merge — not in `FilterWorldThroughBrush` itself.

**Not fixed. No mask, no exclusion proposed**, per `NATIVE-MATERIALIZE.md`'s prime directive: the
working hypothesis this session was scoped to test came back negative, and the honest next step is
further, more precisely targeted investigation — not a guess.

## Repro

    # the live capture (this session):
    UEDCLI_HOME=<...> .venv/bin/python3 \
      dev/docs/spikes/2026-09-15-oceanlab-n203-fwtb-classify/harness/capture_fwtb.py
    # the final-output points/surfs cross-check (needs --keep-native kept native/ref N=203 builds):
    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
      --dx <...>/Maps/14_OceanLab_Lab.dx --from 203 --to 203 --force-ref --keep-native

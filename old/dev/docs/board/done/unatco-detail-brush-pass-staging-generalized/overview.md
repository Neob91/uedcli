+++
priority = "p1"
kind = "debug"
summary = "UNATCO detail-brush pass-staging generalized past portals — surfs/vectors gap closed"
+++

# UNATCO detail-brush pass-staging generalized past portals — surfs/vectors gap closed

Resumed from `dev/docs/spikes/2026-07-15-native-materialize/PARITY-STATUS.md` (committed prefix
stalled at node 1764, brush range (106,159] unresolved). Live gdb captures against the real editor
(ported the `harness/editor-tree-oracle` tooling to this container/rootless-docker environment —
see the harness-port commit) pinned the next divergence to `Brush416` (world-csg idx 111,
`PolyFlags=0x10c` = `PF_NotSolid|PF_TwoSided|0x4`, an ordinary glass/window pane — NOT Portal, NOT
Semisolid). At the N=112 cutoff the real editor's pre-repartition committed tree has 1766 nodes vs
native's pre-fix 1764 — the same "+2 non-CSG splitter" signature §54 found for a portal.

**Fix** (`uedcli-native/src/bspcsg.rs`): `detail_pass` previously deferred every
`NotSolid|Semisolid` brush to the post-repartition pass-2 layer, portals excepted. Generalized to
defer only `Semisolid` brushes — any `NotSolid`-without-`Semisolid` brush (portal or not) now
enters pass 1 as a non-CSG structural splitter, matching spec.md §2's primary disasm-cited
`csgRebuild` structure (a single `bspBrushCSG` loop over all brushes, then one repartition).

**Result, live-verified against the real editor and a fresh from-scratch UNATCO golden build**
(this session, `--no-obj-load` + a raised idle-CPU threshold — see the harness-port commit for
why):
- Committed pre-repartition tree: byte-identical (structurally; ignoring sub-ULP w-twins) through
  the full extent tested — node 3166 / brush 213 (up from node 1764). Closes the (106,213] gap.
- Whole-map (734 brushes, bare `MAP REBUILD` basis, matching `build_ued_golden.py`'s documented
  node/surf/vector basis): **surfs 3615→3616 (golden 3616, EXACT)**, **vectors 599→599 (golden
  599, EXACT — already exact pre-fix)**, nodes 6372→6247 (golden 6314; was +58/+0.9%, now
  -67/-1.1% — similar magnitude, opposite sign), verts 95282→93187 (golden 76488; +24.6%→+21.8%),
  points 10881→10691 (golden 10752; +1.2%→-0.6%). Every dimension improved or stayed exact; no
  regressions measured.
- `cargo test --release`: 51/51 green (added `notsolid_non_portal_brush_enters_pass1_repartition_soup`).
  Castle-safe by construction (0 detail brushes there either way).

**Honest caveat on the new regression test**: unlike the original portal test, my synthetic
single-room fixture does NOT discriminate pass-1-vs-pass-2 routing for this brush class — under a
hand-reverted old formula, the fixture's surf/flag assertions still pass. I could not reproduce the
original portal test's own claimed discrimination either (its own comment cites "bug → 6 surfs",
but reverting `detail_pass` on the current codebase also still yields 7 for that fixture) — this
side-observation suggests **both** pass-1/pass-2 regression tests may have lost their teeth to an
unrelated later change, not something specific to this fix. Not chased further (out of scope); the
real regression coverage for this class of bug is the live oracle capture, not a small synthetic
scene — repartition-order effects only manifest at real tree complexity.

**Open follow-up, NOT done here** — flagged rather than pushed through, since it's a much bigger
lever than this fix: `detail_pass` still defers genuine `Semisolid` brushes to pass 2 (UNATCO has
377 detail brushes total; only the NotSolid-non-semisolid subset was tested live). spec.md §2's
primary disasm decode describes a SINGLE `bspBrushCSG` loop with no flag-based routing at all — if
that generalizes to Semisolid too, the two-pass architecture should be eliminated entirely, not
just narrowed. No live evidence either way yet on Semisolid specifically; the remaining node/verts
residual (-1.1%/+21.8%) is a plausible signature of this open question, or of the separate
axis-aligned repartition-order lever (§36/§53) which this fix did not touch. Needs another live
N-cutoff bisection bracketing the first Semisolid brush before touching `detail_pass` further.

---

## Follow-up session (2026-08-25): bisection closed to the FULL map; Semisolid stays pass-2, live-confirmed

Resumed exactly where the above left off. Ported `native_noropart_struct.py`'s remaining hardcoded
dev-machine paths/import (`native.brush_marshal`, mirroring the `unatco_subset.py` harness-port
fix) so both sides of the committed-tree comparator run in this environment.

**Semisolid bracket (the flagged open question) — live-answered, NO code change:**
`Brush508` (world-csg idx 338, trunk N=361) is the first `Semisolid`-only (`PolyFlags=0x20`) brush
in UNATCO, an 18-quad box-shaped detail brush. Live gdb bracket N=360→361 (trunk-level): editor
committed-tree node count **5922→5922, zero delta** — no new pre-repartition nodes, unlike the
NotSolid/Portal case (which added +2 immediately). Worried this single brush might be a false
negative (e.g. embedded flush in existing solid, so even a true single-pass model would add
nothing there — `AddBrushToWorldFunc`'s cospatial-facing-out case is itself gated `!PF_Semisolid`,
spec.md §3.4 table), so widened the bracket to span UNATCO's whole ~40-brush consecutive run of
pure-Semisolid detail brushes (world idx 338–~378, trunk N=360→400): editor tree **still 5922→5922,
zero delta**, matching native's current (unchanged) pass-2 deferral exactly at both cutoffs
(`committed_tree_diff.py`: 0 structural nodes at N=360 and N=400). **Conclusion: live evidence does
NOT support moving Semisolid brushes into pass 1** — unlike NotSolid, a real Semisolid brush
contributes nothing to the real editor's pre-repartition committed tree over the full tested range.
`detail_pass` (Semisolid-only) is left UNCHANGED; the two-pass architecture does NOT collapse for
this class. (This doesn't settle the *mechanism* — a genuinely single-loop model with the
`!PF_Semisolid` cospatial-gate could also produce this result if every tested Semisolid brush
happens to be cospatial/embedded — but the OBSERVABLE committed-tree behavior, which is what
`detail_pass` needs to match, is unambiguous and consistent over 40+ brushes.)

**Committed-tree bisection — CLOSED to the full 734-brush map, no further fix needed:**
Continued the live N-cutoff bisection past node 3166 (brush 213) with wider jumps (native side is
cheap/instant; the expensive part is the live editor gdb capture — 6 more live captures taken: N=360,
361, 400, 600, 700, 762-full). Native's own committed-tree node count stays flat (5922) from N=360
through N=650 (the long Semisolid run), then grows to 5974 at N=700 and 6368 at the full N=762 — and
at **every one of those checkpoints the live editor capture is structurally IDENTICAL to native**
(`committed_tree_diff.py`: 0 structural nodes, only the usual sub-ULP w-twins, at N=360/400/600/700/762).
**The full-map pre-repartition committed tree is now byte-identical, 6368/6368 nodes, brush 1 through
734 — Front 1 (§92's pass-staging bisection) is CLOSED.** No new `bspcsg.rs` fix was needed beyond what
was already committed in this item (0685806) plus the confirmed-correct Semisolid deferral above; the
existing generalization simply held for the rest of the map. Whole-map post-repartition metrics
unchanged from this item's original measurement (re-confirmed, same build): nodes 6247 (golden 6314,
-1.1%), surfs 3616 (golden 3616, EXACT), vectors 599 (golden 599, EXACT), verts 93187 (golden 76488,
+21.8%), points 10691 (golden 10752, -0.6%) — **the entire residual gap is now isolated to Front 2**
(the axis-aligned repartition over-split, §36/§53 in `sections/92-*.md`), since Front 1 no longer
contributes any divergence. `cargo test --release`: 51/51 green (no Rust changes this session).
Oracle logs for the new checkpoints committed under `harness/editor-tree-oracle/logs/`.

**Not pursued here (bigger, separate lever, out of this item's scope):** Front 2, the repartition
over-split responsible for the whole-map node/vert residual. PARITY-STATUS.md already characterizes
it as large and not statically castle-safe-fixable; needs its own investigation.

**Harness note**: the editor-tree-oracle live-capture pipeline (gdb-attach to the real editor)
is now ported and working in this environment (worktree `bsp-build-parity`) — see the harness-port
commit for the rootless-docker / path-portability / idle-threshold fixes it needed. A genuine
production bug was found and fixed along the way: `uedcli.xfer.cp_in` used raw `docker cp`, which
remounts a container's mounts read-only and fails under rootless docker for a `:ro` bind — mirrors
the already-fixed `cp_out` (`docker exec cat`) for the inbound direction.

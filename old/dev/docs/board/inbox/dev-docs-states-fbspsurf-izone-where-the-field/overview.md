+++
priority = "p2"
kind = "docs"
summary = "dev/docs states FBspSurf iZone where the field is really PanU/PanV — needs the owner's yes to correct"
+++

# dev/docs states FBspSurf iZone where the field is really PanU/PanV

The two u16s after `iBrushPoly` in the on-disk `FBspSurf` are `PanU`/`PanV`, the surface's authored
texture pan — not a zone pair. The code was corrected (the native build was writing 0 there, so every
surface with a non-zero authored pan built with its texture slid across it); the docs still state the
old reading, and dev/docs needs the owner's approval to edit.

Evidence (offline, reproducible):

- Retail `01_NYC_UNATCOHQ.dx` — an editor-built shipped map: all 3570 world surfs hold exactly the
  authored T3D `Pan U=/V=` (mod 65536) of the brush polygon they came from, 408 of them non-zero, 0
  mismatches. Matched by (source brush actor, source poly) against a trunk `level import`ed from that
  same map.
- 12 retail maps: 8189 of 46280 surfs non-zero there, values spanning the full u16 range. A zone
  index is <= 64.
- `Test_Castle.dx`'s all-zero pair (the basis for the old reading) is a map whose polys all have
  `Pan U=0 V=0`.

Places stating the old fact:

- `dev/docs/spikes/2026-07-15-native-materialize/sections/70-zones-portalization.md` §9 "Bug 2 — native
  was WRITING FBspSurf.iZone" — the field identification is wrong, and so is the stated mechanism for
  the black water-pit/backdrop (a small pan offset cannot black out a region; the measured
  before/after improvement stands, the explanation does not).
- same spike, `sections/10-bsp-csg-build.md` (the `iZone[2]` field rows) and
  `sections/83-surf-ref-order-session-artifact.md` (the "iZone 100 % match" row — a castle golden with
  no pans anywhere).
- `dev/docs/unrealed/` has no `FBspSurf` field table today; the corrected fact belongs there, next to
  the T3D `Pan U=/V=` sub-field rule in `unrealed/t3d.md`.

Committed spike harnesses that read the renamed field and now raise `AttributeError` (they import
`uedcli.native.umodel`; each needs `surf.i_zone` -> `surf.pan`), also awaiting the owner's yes:
`dev/docs/spikes/2026-07-15-native-materialize/harness/{ground_truth_triage.py,leaf_dump_nodes.py,lit_diff.py,surf_ref_order_analysis.py}`.
(`dev/docs/spikes/bspspike/umodel_parser.py` and `umodel_serialize.py` are frozen independent copies —
stale naming only, nothing imports them.)

The code-side fact is pinned by `uedcli/tests/test_native_surf_pan.py` (including the retail-golden
non-zero-pan pin), so it will not rot while this waits.

+++
priority = "p3"
kind = "unknown"
summary = "EDIT PASTE of large maps: not size — phantom Brush Model + nested texture names"
+++

# EDIT PASTE of large maps: not size — phantom Brush Model + nested texture names

Rebuilding the Wanchai editor golden (`build_ued_golden.py --world-only --no-light` on 1303
brushes, ~5.2 MB paste) crashed `EDIT PASTE` deterministically in 6/6 runs on 2026-08-29,
after the same full paste had succeeded twice on 2026-08-28. Diagnosed the kicker is NOT
clipboard size (a 600 KB paste of the same brushes also crashed; FreeClinic's 1.3 MB and
NSFHQ's 3.7 MB pastes worked): the poison ingredient is content.

Root causes found (each reproduces and is fixed):

1. **Phantom Brush model.** A `Brush`-class actor whose geometry was dropped during ingest
   (`Brush1688` in wanchaimkt; `a.brush is None`) emits `Brush=Model'MyLevel.ModelNNN'`.
   `_re_add` sends it through MAP IMPORTADD (point path), which allocates that model name in
   the level without the geometry. The later EDIT PASTE imports the real brushes whose model
   names collide with the phantom → "UnrealEd has crashed — a Critical Error dialog is open",
   empty stderr. 6/6 with the import, 2/2 pastes OK once the brushless actor is excluded.
   The committed trunk's Brush1688 HAS geometry, which is why the Aug-28 goldens worked.
   `CLASS.md` and `writes._re_add` do not discuss this.

2. **Flat 2-part `Texture=` names on polys.** Some Wanchai textures resolve only via their
   nested group path (mine `Texture=Catacombs.pa_sqrlight`, committed
   `Texture=Catacombs.Glass.pa_sqrlight`); pasting the flat form can crash EDIT PASTE. The
   committed trunk's ingest emitted qualified names; mine emitted bare ones. Fix: resolve
   flat→nested from the committed trunk (118 names) and rewrite the clipboard before pasting.
   FreeClinic was unaffected because its texture set resolves flat.

Verified end-to-end: a fresh golden built from MY trunk (phantom excluded, nested texture
names applied, chunked at 150 brushes/chunk + idle barrier between chunks) is **bit-identical
at the model level** to the committed golden — nodes 11648, surfs 5284, points 16791, node
planes and resolved surface planes exactly equal. Native wanchaimkt matches it exactly on
nodes/surfs (points +16 only).

Action: none until a golden rebuild needs it — but the two mechanisms are live landmines for
any `_re_add`-driven harness workflow on maps with brushless Brush actors or non-flat-resolvable
texture names.
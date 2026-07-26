# 2026-07-13 semisolid `level materialize` failure — spike harness

Investigation of: a `--solidity semisolid` brush makes `level materialize` fail
(reported as "the editor's MAP SAVE produces no `.dx`"). This dir holds the
**harness**; the durable engine facts are folded into `dev/docs/unrealed/quirks.md`
and the choice into `dev/docs/decisions.md` (2026-07-14).

## Conclusion (2026-07-14) — the report was TWO separate things, only one a real bug

1. **`qualify_level_textures` off-by-one — REAL, fixed.** Nothing to do with semisolids:
   the editor's `OBJ DEPENDENCIES PACKAGE=MyLevel` dump carries, besides one
   `Engine.Polys` block per authored brush, ONE MORE non-empty `Engine.Polys` block —
   the level's own world BSP `Model`, an AGGREGATE of every brush's surviving surfaces.
   `qualify` demanded `#textured-brushes == #non-empty-blocks`, so it raised
   `N vs N+1` on EVERY textured level (any solidity), aborting materialize with no `.dx`
   written. Live-probed structure (`probe_tree.py`, `probe_aggregate.py`): the aggregate
   block's POSITION is not stable — LAST for a 2-brush level (`[6,0,6,0,12,0,0]`, the
   `12` = 6+6), FIRST for the 95-brush castle (an 853-texture block that a positional fix
   zipped onto the first brush → a loud `6-vs-853` raise), MIDDLE for a World-shell level
   (`[6,6,18,6]`). Fix: bind each brush to its block **by content** (matching per-poly
   object-names, `_bare`), leaving the aggregate unclaimed and dropped — position-free.
2. **"semisolid breaks MAP SAVE" — NOT a deterministic bug.** The original one-shot
   failure (castle + 1 semisolid, `--no-verify`) did not reproduce. `probe_lightsave.py`
   (minimal room + semisolid, rebuild→LIGHT APPLY→save) and `probe_bug2.py` (full castle +
   16 semisolids + LIGHT APPLY + save, **run 3×**, with solid+light and semi+no-light
   controls) ALL saved successfully (5/5). The one-off failure was a **transient editor
   wedge** (the editor "wedges silently" — see quirks.md "Stability"), not a
   semisolid/LIGHT-APPLY code bug. Semisolid emission itself is byte-correct (actor-level
   `PolyFlags=32`, not per-poly `Flags=32`) — do NOT change `builders.py`.

Each script drives an ephemeral editor the way `apply.py` / `writes._re_add` does.
MAP EXPORT/SAVE go to the container's `/work` (POSIX) path and are `docker cp`'d out —
the ephemeral container's filesystem is NOT the host, so `FILE=Z:\home\…` would write
inside the container and be invisible to a host read.

Run on the HOST (Python 3.12 + direct docker) from `Tools/uedcli`. To skip the ~90s
editor boot, reuse a booted editor:

```
PYTHONPATH=. python3 dev/docs/spikes/2026-07-13-semisolid-save/probe.py
# reuse:
UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe.py
```

Scripts (run in this order; each writes its `run*.log` under `_scratch/semisolid/`):

- `probe.py` — solid control vs one semisolid; plus Case C makes a brush semisolid the
  editor's OWN way (`MAP SETBRUSH SETFLAGS=32`) and MAP EXPORTs it to read back how the
  editor represents a semisolid (actor `PolyFlags` vs per-poly `Flags`).
- `probe_scale.py` — 16 semisolids: disjoint / overlapping / embedded in a solid wall,
  each vs a solid control on identical geometry.
- `probe_full.py` — the ENTIRE castle trunk (`_scratch/castle/…/maps/foobar`, 95
  brushes) + the exact 16 semisolid ornament brushes from `build_detail.sh` BATCH 3+4,
  vs the same 16 as solid. Textures stripped (geometry isolation).
- `probe_tex.py` — loads real `LUM_CoreTex` and dumps `OBJ DEPENDENCIES` the way
  `qualify.qualify_level_textures` does, for solid / semisolid / nonsolid.
- `probe_watertight.py` — is the level's own world/builder `Model` `Engine.Polys`
  block empty (qualify balances) or non-empty (qualify off-by-one)? lone room / two
  rooms / room+solid-add / room+semisolid-add.
- `probe_castle.py` — a faithful synthetic replica (solid keep+towers with the 16
  buttresses/braziers embedded), kept for reference.
- `probe_lightsave.py` — the step the geometry-only probes skipped: rebuild→**LIGHT
  APPLY**→save, minimal room+cube per solidity, both with and without light. Also dumps
  the RAW `OBJ DEPENDENCIES` so the aggregate block's owner can be inspected.
- `probe_tree.py` — the FULL indented `OBJ DEPENDENCIES` tree for a 2-brush level
  (writes `_scratch/semisolid/tree.txt`): shows the flat "Package MyLevel references:"
  sections and that the world Model's surfaces appear as both an `Engine.Polys` block AND
  an identical-textured `Engine.Model` block (brush inner-Models are empty).
- `probe_aggregate.py` — proves the aggregate block's position is NOT stable and that
  content matching (per-poly object-names) leaves it as the sole unclaimed leftover; also
  checks the `Engine.Model`-duplication signal.
- `probe_bug2.py` — the decisive "is semisolid+LIGHT-APPLY-at-scale a real bug?" test:
  castle + 16 semisolids + LIGHT APPLY + save, repeated 3×, with controls.
```

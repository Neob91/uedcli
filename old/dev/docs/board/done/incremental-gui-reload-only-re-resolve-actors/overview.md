+++
priority = "p2"
kind = "implement"
summary = "Done: Reload now re-reads and re-resolves only the actors whose files moved — 7.9s → 0.17-0.98s on a 2745-actor level, output byte-identical to a full Load"
depends-on = ["gui-reload-rebuild-slow-memoize-scene"]
+++

# Incremental GUI Reload: only re-resolve actors that changed since last Load

Done. Profiling first: this item (and `gui-reload-rebuild-slow-memoize-scene`'s closing note) said
the remaining cost was "genuinely per-actor work" in the sprite/mesh/mover resolvers. It is not. On
oceanlab-lab (2745 actors), warm process, a Load cost 9.7s of which **8.2s was the trunk's own file
I/O** (`read_actor_tree`: 2.6s of per-actor `scandir`, 2.5s reading `actor.t3d`, 2.4s reading the
sidecars), 0.5s T3D parsing, and only 1.5s all three resolvers together. The win is skipping file
reads, not skipping resolution — though both are now skipped per unchanged actor.

Owner ruling 2026-10-03 — the staleness test is each actor DIR's mtime plus `actor.t3d`'s own
mtime+size. The dir mtime catches every write uedcli makes (all land `actor.t3d` via tmp +
`os.replace`, a namespace change in that dir) and anything else writing by rename; the body stat
additionally catches an external in-place rewrite. An in-place rewrite of the `folder`/`labels`/
`order_value` sidecars is knowingly NOT detected: stat'ing all four files costs ~0.95s per
2745-actor Load against ~0.6s for this pair, and those are uedcli-private files it only ever writes
atomically. Measured alternatives offered: dir mtime alone ~0.08s (misses in-place `actor.t3d`
rewrites too), all four ~0.95s.

Shape: `t3dtree.stamp_actor_tree` (one `os.scandir` of `actors/` for the dir mtimes via
`DirEntry.stat`, then one dir_fd-relative stat per body — ~0.6s at 2745 actors, no file reads) +
`t3dtree.read_actor_tree_delta`, which reuses the previous read's parsed `Actor` where the stamp
holds. `serve/trunk_load.py` holds each actor's resolved render data (`_ActorRender`) and feeds the
three resolvers a `Level` of only the changed actors.

The two blockers this item listed both dissolved rather than being built:

- "`_LoadedTrunk`'s flat tables need keying by actor name": not needed. The resolvers already
  return an `owners` entry per poly, so `_localize` splits their existing flat returns per owning
  actor with no resolver change at all — and a cold Load still makes exactly the three whole-level
  calls it made before, sharing one `TextureResolver`.
- "texture indices shared by table POSITION need a stable per-texture-ref registry": not needed,
  and a persistent registry would have been wrong — being append-only, it would strand every
  removed actor's rows in the atlas the GUI ships. Instead each actor's cached polys carry texture
  slots local to its own little table, and the shared table is rebuilt dense per Load in the same
  first-encounter order a full Load produces (deduped by `(entry, group)`, so two refs with
  identical pixels never collapse onto one `AtlasRect.name`).

Code review caught one real defect: `_merge` folded every actor's polys in `level.actors` (name)
order, but `_mover_world_polys` emits movers in `level.order` (the `(order_value, name)` CSG sort),
so mover poly/table/group order silently changed for any level whose ranks don't follow its names —
essentially every real one. The internal joins stayed parallel, so selection and `AtlasRect.name`
were still right, but `web/src/scene/geometry.ts`'s draw groups are built in first-seen poly order,
so two overlapping translucent movers could have composited the wrong way round. `_merge` now walks
twice, each output keeping its own resolver's order. The equivalence tests missed it because they
compared incremental against a cold `load_trunk` — both sides go through `_merge`, so the
pre-change resolver order was never the reference; `test_cold_load_matches_the_resolvers_run_
directly` now pins `_LoadedTrunk` against the three resolvers' direct output under ranks that
reverse name order, and was confirmed to fail if the fix is reverted.

Measured after, oceanlab-lab on the same storage: cold Load 7.9s → Reload with nothing changed
0.98s, Reload with one actor touched 0.17s. nyc-bar (487 actors): 1.05s → 0.009s / 0.10s.
`test_serve_trunk_load.py` pins the real contract — an incremental Load's `_LoadedTrunk` equals a
cold Load's field for field after a move, an add, a remove, a re-texture and a re-rank — and the
equivalence was re-checked on the real 2745-actor level, not just fixtures.

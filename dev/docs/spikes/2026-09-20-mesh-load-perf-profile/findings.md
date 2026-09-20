# `/load` mesh-actor resolution profile — `showcase_bar`, 487 actors

`profile_load.py` in this dir drives the real `POST /load` route handler (via `TestClient`,
`uedcli/serve/app.py`) against `dev/games`'s `showcase_bar` trunk, wrapped in `cProfile`. Run:
`.venv/bin/python dev/docs/spikes/2026-09-20-mesh-load-perf-profile/profile_load.py`.

## Result (measured 2026-09-20, this host)

Whole `/load` call: **13.3s**. Breakdown (cumulative time, from the real profile — not estimated):

| Where | Cumulative | Calls |
|---|---|---|
| `uedcli/serve/app.py:537 load()` (the whole route) | 13.256s | 1 |
| `preview_native.py:457 resolve_mesh_scene_polys` | 9.468s | 1 |
| `preview_native.py:369 resolve_mesh_actor_polys` | 9.466s | 1 |
| `preview_native.py:294 _mesh_actor_polys` (per mesh actor) | 9.039s | 279 |
| `uprops/values.py:507 resolve_class_defaults` | 6.522s | **453** |
| `uprops/uclass.py:15 class_export_index` | 3.298s (2.019s own) | 3952 |
| `utexture.py:781 resolve` | 4.116s | 205 |
| `utexture.py:1012 _decode_ref` | 4.115s | 179 |
| `meshrender.py:106 resolve_skins` | 4.033s | 119 |
| `utexture_decode.py:22 mip0_to_rgb` (own time) | 0.495s | 179 |
| `preview_native.py:582 resolve_actor_sprites` | 2.584s | 1 |
| `str.casefold` (own time, all call sites) | 1.453s | **8,858,467** |

## Root cause — the same bug shape twice, both already-existing caches never shared across the loop

1. **`resolve_class_defaults`** (`uprops/values.py:508`) takes an optional `_pkgs: dict | None`
   memo — every one of its 3 call sites in `preview_native.py` (lines 245, 327, 748) omits it,
   so `pkgs: dict = _pkgs if _pkgs is not None else {}` (line 519) makes a FRESH empty cache on
   every call. Line 327 is the one `_mesh_actor_polys` hits once per actor inside
   `resolve_mesh_actor_polys`'s loop (`preview_native.py:398`) — 279 actors, 453 total
   `resolve_class_defaults` calls across the whole `/load` (mesh + point-actor sprites + movers),
   almost certainly far more than the level's actual distinct-class count.
2. **`resolve_skins`** (`meshrender.py:106`) builds a brand-new `utexture.TextureResolver` on
   every call (`meshrender.py:150`, `resolver = utexture.TextureResolver(list(search_files),
   class_index=class_index)`). `TextureResolver.resolve()`'s own docstring says it is "cached by
   identity per resolver instance" (`utexture.py:781-782`) — a fresh instance per actor means
   that cache never survives past the one actor that built it, so N actors sharing the same skin
   texture each pay for a full decode (`_decode_ref`/`mip0_to_rgb`/`_decode_linear1`) instead of
   one decode shared N ways.

Both are the identical shape to the already-fixed
`gui-serve-rebuilds-classindex-on-every-request` bug (a real, working memo, just never threaded
through the loop that repeats the same work) — in a different subsystem (mesh-actor resolution
inside `/load`, not scene-input resolution inside `/scene`/`/atlas`/`/lightmap`).

## What this is NOT

Not touched by, and not fixed by, the earlier `_scene_inputs_ref` caching work
(`gui-serve-rebuilds-classindex-on-every-request`) — that fix only covers `/scene`/`/atlas`/
`/lightmap`'s `(search_files, index, defaults)` triple; `resolve_mesh_scene_polys` is a
completely separate resolution path called unconditionally from `/load` itself.

## Result AFTER the fix (measured 2026-09-20, same host, same level)

Whole `/load` call: **6.8s** (was 13.3s — a 49% reduction). Measured against this worktree's fixed
code, cross-checkout against the main checkout's `dev/games` (this worktree has no local `dev/games`
of its own — gitignored, not shared across worktrees); `profile_load.py` itself only needed a
path-depth fix (see its own history — it was copied from `_scratch/` into this deeper spike
directory without updating its `parents[N]` indices, caught while re-running it for this update).

| Where | Before | After |
|---|---|---|
| `load()` (whole route) | 13.256s | 6.783s |
| `resolve_mesh_scene_polys` | 9.468s | 1.660s |
| `resolve_mesh_actor_polys` | 9.466s | 1.657s |
| `resolve_class_defaults` calls (whole `/load`) | 453 | 52 |
| `_decode_ref` calls (whole `/load`) | 179 | 69 |

`resolve_mesh_scene_polys`/`resolve_mesh_actor_polys` no longer appear in the unfiltered top-25
profile at all (had to be queried specifically to get the numbers above) — the dominant cost for
this level's `/load` is now `resolve_actor_sprites` (2.6s, point-actor icons, already using its own
shared `ClassDefaults` before this fix, untouched here) and `t3dtree.read_actor_tree` (1.7s, trunk
parsing itself) — neither in this item's scope. `class_export_index`/`str.casefold` overhead (the
spec's own flagged "may not fully disappear" risk) did shrink roughly in proportion to the
`resolve_class_defaults` call-count drop, as expected, but was not separately re-measured in
isolation here.

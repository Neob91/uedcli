# `/load`'s mesh-actor resolution: share the class-defaults and texture-decode caches

Written for a reader with no prior context on `uedcli/preview_native.py`. Root cause is read
directly off the current code — line numbers below are current as of this spec's own commit.
Full profile evidence: `dev/docs/spikes/2026-09-20-mesh-load-perf-profile/`.

## The problem, precisely

Profiling a real `POST /load` against `showcase_bar` (487 actors, 279 of them `DT_Mesh`) shows the
whole call takes 13.3s, 71% of it (9.47s) inside `resolve_mesh_scene_polys` — the mesh-actor
resolution `uedcli serve`'s `/load` handler calls unconditionally, every time, regardless of the
`gui-serve-rebuilds-classindex-on-every-request` fix (which only covers `/scene`/`/atlas`/
`/lightmap`'s separate `_scene_inputs` triple, not `/load` itself).

## Root cause — two existing caches, never shared across the per-actor loop

1. **`resolve_class_defaults`** (`uprops/values.py:508`) already accepts an optional `_pkgs: dict`
   memo — the whole reason it exists is amortizing repeated resolution of the same class
   (`ClassDefaults`'s own docstring: "a cold class resolution costs ~0.1-0.3s ... ~0.01-0.03s
   amortized"). But `_mesh_actor_polys` (`preview_native.py:327`) and `resolve_mover_actor_polys`'s
   `_hidden` closure (`preview_native.py:245`) both call it bare —
   `resolve_class_defaults(actor.cls, resolver=index.resolver())`, no `_pkgs` — so every one of the
   279 mesh actors (and every Mover) gets a **fresh, empty** cache. Measured: 453
   `resolve_class_defaults` calls, 6.52s cumulative, across a level with (per `ClassDefaults`'s own
   docstring figure) 5-60 *distinct* classes — almost certainly two orders of magnitude more calls
   than distinct classes actually touched.

   The board item's own overview and the spike's findings also name a THIRD bare call site,
   `preview_native.py:748`, inside `find_sky_actor` — flagged there for completeness, deliberately
   not addressed here: `find_sky_actor` (def at `preview_native.py:730`) is called only from
   `render_shots` (`preview_native.py:1169`, a sibling call alongside `render_shots`'s own
   `build_scene` call at line 1164 — NOT from inside `build_scene`'s body itself, corrected after
   review). `render_shots` is reached only via `cli/commands/level.py`'s `level photo --native`,
   never from `/load`'s path, so it plays no part in the profiled 13.3s and is out of scope for the
   same reason `level photo`'s other call sites are (see the scope decision below).
2. **`resolve_skins`** (`meshrender.py:106`) builds a **brand-new** `utexture.TextureResolver` on
   every call (`meshrender.py:150`: `resolver = utexture.TextureResolver(list(search_files),
   class_index=class_index)`). `TextureResolver.resolve()`'s own docstring says it is "cached by
   identity per resolver instance" (`utexture.py:781-782`) — a fresh instance per mesh actor means
   that cache dies with the actor that built it, so N actors sharing one skin texture each pay a
   full decode (package load + property/schema walk + RGB conversion) instead of one decode shared
   N ways. Measured: 4.03s cumulative inside `resolve_skins` alone (`_decode_ref`/`mip0_to_rgb`
   underneath it).

**This is the identical bug shape `gui-serve-rebuilds-classindex-on-every-request` already fixed**
(a real, working memo that nothing threads through the loop repeating the same work) — in a
different subsystem. It is also the EXACT bug `resolve_actor_sprites` (point-actor icons,
`preview_native.py:582`) was **already fixed for**, and its own docstring says so explicitly
(`preview_native.py:588-591`): *"`class_defaults` is the caller's shared `classdefaults.ClassDefaults`
memo ... resolving a fresh schema chain per ACTOR instead of once per distinct CLASS was an O(actors)
cost on every request, even a full CSG-cache hit."* `resolve_actor_sprites` is the reference
implementation this fix mirrors: it takes a shared `ClassDefaults` (`class_defaults.for_class(actor.cls)
.defaults`, line 612) and builds exactly ONE `TextureResolver` for its whole call (line 602), not one
per actor. Mesh/Mover resolution never got the same treatment when they were written.

## Proposed fix

**Thread a shared `ClassDefaults` instance and a shared `TextureResolver` through the mesh/Mover
resolution call chain, sourced from `/load`'s own already-built `defaults` (a `ClassDefaults`,
from `_scene_inputs`) — the same object `/load` already passes to `resolve_actor_sprites`.**

Concretely (exact signatures are the plan's job, not this spec's):

- `_mesh_actor_polys` and `resolve_mover_actor_polys`'s `_hidden` closure stop calling
  `resolve_class_defaults(actor.cls, resolver=index.resolver())` directly; they take an optional
  shared `class_defaults: ClassDefaults | None` and, when given, call
  `class_defaults.for_class(actor.cls).defaults` instead — the exact substitution
  `resolve_actor_sprites` already makes. `ClassInfo.defaults` (`classdefaults.py`) is the same
  `dict[tuple[str, int], str]` shape `resolve_class_defaults` returns directly, so this is a
  drop-in value substitution, not a shape change.
- `resolve_skins` takes an optional pre-built `resolver: TextureResolver | None`; only when it is
  `None` does it build its own (today's behavior, unchanged for any other caller). `resolve_skins`
  has two call sites: `preview_native.py:360` (inside `_mesh_actor_polys`, the one this fix
  touches) and `cli/commands/classes.py:212` (`class preview`'s single-mesh thumbnail path,
  unaffected — an earlier draft of this spec wrongly said "exactly one," caught in review). The
  new `resolver` param defaults to `None`, so `classes.py`'s call needs no change and keeps
  building its own resolver exactly as today.
- `resolve_mesh_actor_polys` builds ONE shared `TextureResolver` (when `search_files` is non-empty,
  matching `resolve_actor_sprites`'s own guard) before its per-actor loop — **unconditionally, for
  EVERY caller, `build_scene` included**: unlike `class_defaults` below, this needs no new external
  dependency (it's built from `search_files`, a parameter `resolve_mesh_actor_polys` already takes),
  so there is no reason any caller would want the old one-resolver-per-actor behavior. This is a
  pure internal change from the CALLER's point of view — `resolve_mesh_actor_polys`'s own external
  signature doesn't change, so `build_scene`'s own call to it (`preview_native.py:1030` — line 1013
  is a call to `resolve_mover_actor_polys`, a different function that never builds a
  `TextureResolver` at all, movers use their own authored `Texture`/`TextureU`/`TextureV`; an
  earlier draft of this spec wrongly cited both lines here, caught in review) gets this half of the
  fix for free. Internally, `_mesh_actor_polys` (`resolve_mesh_actor_polys`'s own per-actor
  helper, `resolve_skins`'s sole caller) DOES gain a new parameter to carry the resolver down to
  `resolve_skins` — the "no signature change" claim is about `resolve_mesh_actor_polys`'s own
  external interface, not every function in the chain, the same distinction the `class_defaults`
  bullet below already makes explicit for its own parameter. `resolve_mesh_actor_polys` also
  accepts an optional shared `class_defaults` (see below) to forward into every `_mesh_actor_polys`
  call alongside it.
- `resolve_mesh_scene_polys`/`resolve_mover_scene_polys` (the two `uedcli serve`-specific,
  Load-owned entry points, `preview_native.py:457`/`268`) gain a `class_defaults: ClassDefaults`
  parameter and forward it down.
- `uedcli/serve/app.py`'s `/load` handler and `_get_trunk`'s bootstrap branch — both already have
  `defaults` in scope from `_scene_inputs(project)` and already pass it to `resolve_actor_sprites`
  — now also pass it to `resolve_mesh_scene_polys`/`resolve_mover_scene_polys`.

**Only the `class_defaults` half is scoped to `uedcli serve`'s independent path — the
`TextureResolver` half applies everywhere, `build_scene` included (see bullet 3 above).** The new
`class_defaults` parameter (on `_mesh_actor_polys`, `resolve_mover_actor_polys`'s `_hidden`
closure, and `resolve_mesh_actor_polys`) is optional, defaulting to `None` (today's per-actor-fresh
`resolve_class_defaults` call, unchanged) — because unlike the resolver, it needs an EXTERNAL
`ClassDefaults` instance the caller must already have; `build_scene`'s own calls
(`preview_native.py:1013`/`1030`) — reached via `render_shots` (`preview_native.py:1164`, i.e.
`level photo --native`) — pass none, so they keep today's per-actor class-defaults behavior,
unchanged. `build_scene` has one OTHER caller, `uedcli/serve/app.py`'s `_build_and_publish_geometry`
(`/rebuild`'s handler) — moot for this fix either way, since that call passes
`include_meshes=False, include_movers=False`, and `build_scene`'s own body gates BOTH
`resolve_mesh_actor_polys` and `resolve_mover_actor_polys` behind exactly those flags
(`preview_native.py:1012`/`1021`), so `/rebuild` never reaches either half of this change. `class
preview` never calls `build_scene` at all (it calls `resolve_skins` directly, see the bullet above
— genuinely unaffected, not just unchanged). This mirrors
`resolve_actor_sprites`'s own docstring framing — the O(actors) *class-defaults* cost matters "on
every request, even a full CSG-cache hit," which describes `uedcli serve`'s repeated `/load`, not
`level photo`'s one-shot CLI invocation. Whether `build_scene` has its own `ClassDefaults` instance
already in scope that it COULD pass (getting this half of the fix too, for free, with no further
code change) is not checked here — out of scope for this item; if one is confirmed to exist, wiring
it through is a trivial follow-up, not a new design.

## What this fixes and what it doesn't

- Fixes: `/load` (and the automatic first-request bootstrap) resolves each *distinct* class and
  each *distinct* skin texture once per call, not once per actor referencing it. Expected effect on
  `showcase_bar`: `resolve_class_defaults`'s 453 calls collapse to the level's real distinct-class
  count (5-60, `ClassDefaults`'s own docstring range) and `resolve_skins`'s texture decodes collapse
  to the level's real distinct-skin count — the dominant share of the measured 9.47s.
- Does not fix: the remaining, smaller contributors in the same profile (`class_export_index`'s own
  2.02s tottime across 3952 calls, 8.86M `str.casefold()` calls) — these may shrink automatically
  once the outer memo hit rate improves (fewer distinct classes actually get walked), but are not
  independently investigated or guaranteed fixed here. Re-profile after this lands to see what, if
  anything, is worth a follow-up item.
- `build_scene`/`level photo --native` (one of `build_scene`'s two callers, via `render_shots` —
  the other, `/rebuild`'s `_build_and_publish_geometry`, never reaches either half of this fix at
  all, see the scope paragraph above): the
  `TextureResolver` half applies to it too (a free, incidental speedup, not this item's goal); the
  `class_defaults` half does not, since it needs an external instance this caller doesn't pass (see
  scope decision above) — its own per-actor class-defaults cost, if any, is unchanged. `class
  preview` (`cli/commands/classes.py:212`) is untouched by either half — it calls `resolve_skins`
  directly, never through `resolve_mesh_actor_polys`, so there is no per-actor loop for either
  cache to help with even in principle.
- Does not touch anything the `gui-serve-rebuilds-classindex-on-every-request` fix already covers
  (`/scene`/`/atlas`/`/lightmap`'s `_scene_inputs_ref` cache) — this is a genuinely separate cache,
  a separate subsystem, inside `/load` itself.

## Where to look

`uedcli/preview_native.py` (`_mesh_actor_polys` 294, `resolve_mesh_actor_polys` 369,
`resolve_mover_actor_polys` 222, `resolve_mesh_scene_polys` 457, `resolve_mover_scene_polys` 268,
`resolve_actor_sprites` 582 — the reference implementation), `uedcli/meshrender.py`
(`resolve_skins` 106, its two call sites at `preview_native.py:360` and
`cli/commands/classes.py:212`), `uedcli/classdefaults.py`
(`ClassDefaults.for_class`/`ClassInfo.defaults`), `uedcli/utexture.py` (`TextureResolver.resolve`,
781), `uedcli/serve/app.py` (`/load`'s handler and `_get_trunk`'s bootstrap branch — both already
have `defaults` in scope).

## Testing

A regression test should assert the memoization directly, mirroring how
`gui-serve-rebuilds-classindex-on-every-request`'s own tests count calls: build a small fixture
level with 2+ mesh actors sharing one class and one skin texture, call `resolve_mesh_scene_polys`
with a shared `ClassDefaults`, and assert (via a counting wrapper, or `ClassDefaults.resolutions`,
which already exists and is "read by the perf regression test" per its own inline comment) that the
class resolves once, not once per actor. A second test should confirm `resolve_skins`'s
`TextureResolver` reuse the same way (a spy/counter on `TextureResolver.resolve` or `_decode_ref`).
Re-run `dev/docs/spikes/2026-09-20-mesh-load-perf-profile/profile_load.py` after the fix lands and
record the new numbers in that spike's `findings.md` (do not let the evidence go stale).

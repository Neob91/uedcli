# GUI serve rebuilds the class/schema index on every request

Written for a reader with no prior context on `uedcli/serve/app.py`. Root cause is read directly off
the current code (`_scene_inputs`, `ClassIndex`, `ClassDefaults`, `config.composed_search_files`),
not inferred — line numbers below are as of this spec's own commit.

## The bug, precisely

`uedcli/serve/app.py`'s `_scene_inputs(project)` (line 42) builds `(search_files, index, defaults)`
from scratch:

```python
user_config = config.load_user_config()
search_files = config.composed_search_files(project, user_config)
index = resources.mover_index(None, "uedcli serve", project=project)
defaults = ClassDefaults(packages.schema_resolver(project, user_config))
```

It is called **unconditionally, at the top of every one of 5 routes**: `POST /load` (491),
`POST /rebuild` (522), `GET /scene` (535), `GET /atlas` (571), `GET /lightmap` (599). None of the
5 call sites checks whether a previous call already built an equivalent `index`/`defaults` — each
constructs brand-new objects every time.

**A single GUI "Reload" click fires it 4 times.** `App.tsx`'s `runBuildAction('load', postLoad)`
does `POST /load` then `fetchLevelState()`, which is `Promise.all([fetchScene, fetchAtlas,
fetchLightmap])` (`api.ts:249-252`) — one `/load` + three concurrent GETs, each independently
calling `_scene_inputs()`. The initial page mount does the same 3-way `fetchLevelState()` fetch on
its own (`App.tsx`'s mount `useEffect`), so opening the GUI cold already pays 3 calls before the
user does anything, and every subsequent Reload/Rebuild adds 4 more.

## Why this is expensive, layer by layer

### 1. The composed search path and user config are each recomputed TWICE per `_scene_inputs()` call

`_scene_inputs()` calls `config.composed_search_files(project, user_config)` directly (line 61) —
which itself does one `os.listdir` + sort + extension-filter per composed directory
(`config.py:509-530`; the listing happens inside `composed_search_files` itself at line 521, over
the directories `_composed_dirs_with_provenance` enumerates) — and ALSO calls
`resources.mover_index(None, ..., project=project)` (line 62), which calls
`resources.class_index(project)` (`cli/resources.py:268`), which calls `config.load_user_config()`
**again** (a second, independent config-file read) and then `classindex.ClassIndex.from_project`
(`classindex.py:60`), which calls `config.composed_search_files(project, user_config)` **again** —
a second full directory scan with a second freshly-loaded `user_config`. So one `_scene_inputs()`
call does 2 config loads and 2 full composed-path directory scans, not 1 of each. Over a 4-call
Reload that's 8 config loads and 8 directory scans for zero new information (the package path does
not change mid-Reload).

### 2. A fresh `ClassIndex`/`ClassDefaults` throws away the in-process per-class memo — this is the real cost

`ClassIndex` (`classindex.py:32-45`) and `ClassDefaults` (`classdefaults.py:112-132`) both hold a
per-instance memo dict (`_schemas`/`_pkgs`) that turns a repeat class lookup from a
package-load-plus-decode into a dict read. `ClassDefaults`'s own CLASS docstring (`classdefaults.py:
112-118`, not `__init__`'s — it has none) states the cost this memo exists to amortize: **"a cold
class resolution costs ~0.1-0.3s ... ~0.01-0.03s amortized once the packages are loaded once."**
`ClassIndex._schema()` backs onto the persistent on-disk `schema_cache` (`schema_cache.py`), which
still costs a real `stat` + file read + `marshal` deserialize per package per miss of the
**in-process** memo, even when the on-disk blob is warm — real cost, though `schema_cache.py`'s own
"~0.4s warm" figure is a whole-command total across every package `class list` touches, not a
per-package cost, so it should not be read as "each package costs ~0.4s."

Because `_scene_inputs()` constructs a **new** `ClassIndex`/`ClassDefaults` on every route hit, that
per-instance memo starts empty every time. `POST /load` walks `resolve_actor_sprites` /
`resolve_mesh_scene_polys` / `resolve_mover_scene_polys` over every actor in the level, touching the
class of each — for a level with 5-60 distinct classes (`ClassDefaults`'s own docstring figure)
across hundreds of actors, that is 5-60 on-disk-cache reads-and-deserializes, from zero, **on every
single explicit Load**, even the second Load in the same still-running process where nothing on the
package path changed. This is what produces the observed ~30-60s Reload on a freshly-restarted
process, and a smaller but nonzero repeat cost on every Load after that.

### 3. On a warm trunk, `/scene`/`/atlas`/`/lightmap`'s rebuilt `index`/`defaults` are provably unused — `/rebuild` is different, and DOES need a fresh one

For `/scene`, `/atlas`, `/lightmap`, `_get_trunk`/`_get_payload` (app.py:202-339) check
`_trunk_ref[0]`/`_payload_ref[0]` **before** touching `search_files`/`index`/`defaults` at all, and
return the cached trunk/payload directly if present — never calling anything on the freshly-built
`index`/`defaults` argument. So on a warm trunk+payload, these three routes' own
`_scene_inputs()` calls (2 config loads, 2 directory scans, 2 fresh memo-less resolver objects each)
are pure waste: built, passed down, and never consulted. This is already documented adjacent to
`_payload_ref` (app.py:141-152) as the mechanism that made `/scene` stay ~28s even on a warm repeat
before the payload cache existed — that fix stopped `build_scene_payload` from re-running, but did
nothing about `_scene_inputs()` itself still running unconditionally one line above the fixed call.

**`/rebuild` is NOT in this "provably unused" group — an earlier draft of this spec wrongly
included it, caught in review.** `_build_and_publish_geometry` (app.py:257-289) has **no**
already-cached short-circuit BY DESIGN ("Deliberately has no 'already cached? return early'
short-circuit ... Rebuild always re-derives from the CURRENT trunk view") and passes its
`index`/`defaults` straight into `_build_scene` (`preview_native.py:797`), which genuinely consumes
`index` for schema-aware mover classification and `defaults` for light-property class defaults —
real inputs to the CSG/lighting solve, not dead arguments. So a design that keeps a permanently
stale `index`/`defaults` around for `/rebuild` would not just be "still correct but slower" the way
it is for the other three routes — if a `.u` package's content genuinely changes on disk during a
long `serve` session (e.g. a level's substrate gets recompiled/updated without a restart), a
process-lifetime-cached `index`/`defaults` would feed `/rebuild` stale schema and silently produce a
**different, wrong** CSG/lighting result, not merely a slow-but-correct one. This rules out a single
"cache once, forever, no invalidation" scheme for all 5 routes — see the revised proposal below.

## Why the existing `_scene_inputs` docstring's rationale doesn't hold up — for the three read routes only

`_scene_inputs`'s own docstring (line 46-47) gives the reason for rebuilding every time: "so a
`--project`'s on-disk games config can change without a `serve` restart." Its own very next
paragraph (line 49-59) already concedes this doesn't actually work for `/scene`/`/atlas`/`/lightmap`
once the trunk/geometry/payload caches are warm — "A games-config edit therefore needs a Rebuild
(or a `serve` restart) to take effect, not just the next request." So for these three routes
specifically, the stated benefit is already unreachable on the hot, cache-warm path — which is the
argument the fix below relies on for THEM. It does **not** extend to `/load` or `/rebuild` (§3
above) — both remain untouched by the fix, still calling `_scene_inputs()` fresh every time, exactly
as today.

## Same root cause as the sibling CLI-side item

`dev/docs/board/inbox/materialize-rebuilds-classindex-twice-per/overview.md` is the identical
pattern one call deep in `level materialize` (`uedcli/apply.py`'s `run_materialize`/
`_assembly_level` building two independent `ClassIndex`es per invocation). That item's fix (thread
one already-built `index` through instead of rebuilding) is a narrower, same-process, single-call
version of this one. This item is the `serve` long-running-process case, where the redundancy
compounds across N requests instead of 2 calls.

## Proposed fix

**Scope the cache to the three read routes only (`/scene`, `/atlas`, `/lightmap`); leave `/load` and
`/rebuild` calling `_scene_inputs()` fresh, unconditionally, exactly as today.** This is a revision
from this spec's first draft, which proposed one process-lifetime, never-invalidated cache for all
5 routes — review correctly caught that this would let `/rebuild` silently consume stale schema
(§3 above). `/load` and `/rebuild` are the two routes whose whole job is to genuinely re-derive from
current state; they must keep paying for a fresh `_scene_inputs()` every time they run, same as
today. The redundant, provably-wasted calls are only the three read routes' own independent rebuilds
on top of a trunk that `/load` (or the automatic first bootstrap) already just built.

Concretely: add a cache slot (`_scene_inputs_ref`) whose lifetime is tied to `_trunk_ref`'s, not to
the process's — rebuilt only when the trunk itself is rebuilt, by the same two places that already
reassign `_trunk_ref[0]` (`/load`'s handler, and `_get_trunk`'s once-only bootstrap branch under
`_trunk_lock`), stashing the `(search_files, index, defaults)` triple they already had in hand
alongside it. `/scene`, `/atlas`, `/lightmap` stop calling `_scene_inputs()` themselves; they read
whatever is currently paired with `_trunk_ref[0]` — which is exactly what they already effectively
run against today (via `_get_trunk`'s/`_get_payload`'s own cached-trunk fast path), just without
first paying for a same-answer rebuild to get there. The one case this can't shortcut is the very
first ever request on a fully cold process (nothing to pair with yet) — that one request still
builds `_scene_inputs()` itself, same as today; not a regression, and not the repeat-Reload cost the
owner reported.

`switch_level` (app.py:413-459) already clears `_trunk_ref[0]` on a level switch; clear
`_scene_inputs_ref[0]` in the same place, for the same reason `_trunk_ref` itself is cleared there
(nothing paired with the old level's trunk is valid for the new one) — even though, in this case,
`search_files`/`index`/`defaults` don't actually depend on which level within the project is open,
so keeping them would likely be safe too; clearing is the simpler, more obviously-correct choice and
costs at most one extra `_scene_inputs()` call on the next request after a level switch.

**Open question for the plan stage, not resolved here:** whether `/rebuild`'s own always-fresh
`_scene_inputs()` result should also opportunistically refresh `_scene_inputs_ref[0]` (cheap, and
keeps the read routes' pairing as fresh as possible without extra cost, since `/rebuild` already
paid for the fresh build) — a nice-to-have, not required for correctness, since the read routes stay
correct either way (paired with whatever trunk is current).

**A real, but low-severity, concurrency note review surfaced (Important, §ClassIndex/ClassDefaults
are mutable memo objects, not immutable snapshots):** unlike `_LoadedTrunk`/`_BuiltGeometry`
(frozen dataclasses, assigned once, never mutated after), a shared `ClassIndex`/`ClassDefaults`
instance mutates its own `_schemas`/`_pkgs` memo dict as a side effect of being read
(`classindex.py:111-121`, `classdefaults.py:177`). Handing the SAME instance to `/scene`+`/atlas`+
`/lightmap` fired concurrently (`Promise.all`, `web/src/api.ts:250`) means their threadpool threads
can race on that dict's check-then-insert with no lock. This is a genuine gap from claiming the fix
"mirrors" the existing immutable-snapshot cache-slot pattern — it doesn't, and should not be
described that way. The race itself is benign, not a correctness bug: a class's decode is a pure,
idempotent function of the file on disk, dict single-key get/set is atomic under the GIL, so the
worst case is two threads occasionally redundantly decoding the same first-touched class once, never
a corrupted or wrong result. Worth a one-line comment at the shared instance's construction site
saying so explicitly, so a future reader doesn't need to re-derive it; not worth a lock.

**Not tied to `PUT /api/level`** beyond the `_scene_inputs_ref` clear above — a level switch changes
which level directory this process reads (`_current_level[0]`), not the project or its games config.

### What this fixes and what it doesn't

- Fixes: every `/scene`/`/atlas`/`/lightmap` call after the trunk it reads is already warm pays zero
  `_scene_inputs()` cost — no repeat config loads, no repeat directory scans, no repeat per-class
  schema decode for classes the current trunk's own `/load` already resolved. On the common Reload
  flow (`/load` then the three GETs, `App.tsx`'s `runBuildAction`), this cuts 4 `_scene_inputs()`
  calls down to 1 (the `/load` call itself, unchanged and necessary).
- Does not fix: `/load`'s and `/rebuild`'s own `_scene_inputs()` call, on every Load/Rebuild — those
  are real, necessary, unavoidable re-derivations by design, not redundant work; nor the first-ever
  cold request before any trunk exists. The ~30-60s freshly-restarted-process figure comes from
  `/load`'s own necessary per-class decode across the level's distinct classes — inherent to needing
  every class's schema at least once, not redundant. (`speed-up-the-offline-test-suite`'s parked
  in-process-memo/disk-cache-split question, cited by the sibling item, is the more relevant lever
  for THAT number, not this fix.)
- Does not touch `_assembly_level`'s double-build in `level materialize` — that is the sibling
  item's own, separate fix.

## Where to look

`uedcli/serve/app.py` (`_scene_inputs`, its 5 call sites, the existing `_trunk_ref`/`_geometry_ref`/
`_payload_ref` cache-slot pattern to mirror), `uedcli/classindex.py` (`_schemas` memo),
`uedcli/classdefaults.py` (`_pkgs` memo), `uedcli/config.py` (`composed_search_files`,
`load_user_config`), `uedcli/cli/resources.py` (`class_index`, `mover_index`), `uedcli/schema_cache.py`
(the on-disk layer this in-process memo sits in front of), `dev/docs/board/inbox/
materialize-rebuilds-classindex-twice-per/overview.md` (sibling item), `web/src/App.tsx`
(`runBuildAction`, the mount `useEffect`), `web/src/api.ts` (`fetchLevelState`).

## Testing

A regression test should assert the memoization directly rather than timing, and must distinguish
the two groups of routes: patch/count calls to `config.composed_search_files` (or
`resources.mover_index`) across a `POST /load` followed by two `GET /scene` (or `/atlas`/`/lightmap`)
requests against the same running `TestClient` app instance, and assert it is called exactly **once**
— from `/load` — not three times. A second test should confirm the negative is still true for the
routes this fix does NOT touch: two sequential `POST /rebuild` calls (or `/load` calls) must each
independently call `config.composed_search_files`/`resources.mover_index` again — asserting a call
count of 2, not 1 — so a future change can't accidentally extend the read-route memo to `/load`/
`/rebuild` and silently reintroduce the stale-schema risk §3 describes. Mirrors how
`dev/docs/board/to-spec/uedcli-serve-share-one-in-process-scene-cache/`'s own tests already assert
`build_scene_payload` call counts for the sibling `_payload_ref` cache.

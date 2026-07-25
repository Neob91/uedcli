# Plan — Actor folders (hierarchical organization)

Implements [`specs/2026-07-18-actor-folders-hierarchical.md`](../specs/2026-07-18-actor-folders-hierarchical.md)
(cold-review-gated; §8 resolutions binding). Ephemeral scratch — folded into `architecture.md` +
`unrealed/t3d.md` on build.

A **folder** = a per-actor, uedctl-side, hierarchical dotted path (`castle.tower.roof`) stored in a
`folder` SIDECAR file beside `order_value`. NEVER in the T3D body, NEVER emitted to the map,
independent of the T3D `Group=` prop.

## Build order (each step compiles + tests green before the next)

1. **`model.py`** — add `Actor.folder: str | None = None` (a typed field like `location`, NOT a
   `props` entry). Add a `// uedctl-folder: <path>` carrier reader to `_parse_actor`: a bare
   `//`-comment line matching `^\s*//\s*uedctl-folder:\s*(\S+)\s*$` sets `actor.folder`. Only the
   `actor show` interchange form carries it; stored trunk bodies never do (folder is the sidecar).
   Other `//` comments stay ignored. `emit.py`/`canonical_actor_t3d` are UNTOUCHED — they never
   emit the field, so folder is naturally out of the body, the map, and the hash.

2. **`folderlib.py`** (new, pure) —
   - `validate_folder_path(path)` — non-empty; `.`-split; every segment non-empty and
     `[A-Za-z0-9_+-]+`. Rejects `*`, `,`, `/`, `\`, whitespace, empty segment (ValueError naming
     the value).
   - `validate_pattern(pattern)` — same per-segment charset PLUS the `*` token: each segment is
     exactly `*`, exactly `**`, or a pure literal `[A-Za-z0-9_+-]+`. Rejects `?`/`[`/`]`, `***`,
     mixed `a*b`, empty segment.
   - `is_wildcard_free(pattern)` = `"*" not in pattern`.
   - `matches(pattern, folder)` — the §3 normative algorithm. `folder is None` → False.
     Case-insensitive (casefold both). Wildcard-free → `folder == pattern or
     folder.startswith(pattern + ".")` (subtree). Else a **segment-list globstar match**
     (`*` = exactly one segment, `**` = zero-or-more segments) — provably identical to the spec's
     separator-absorbing regex, verified case-by-case against the §3 table in tests.

3. **`trunk.py`** — `read_level_with_bodies` returns a **4th** element `folders: dict[str, str|None]`
   and sets `actor.folder` (read `folder` file, strip; absent/empty → None). `read_level` ripples
   (ignores it). `write_level` writes the `folder` sidecar **atomically** (`tmp + os.replace`, like
   `actor.t3d`) when `actor.folder` is set, else **removes** any existing `folder` file — for each
   actor it (re)writes in the delta set.

4. **`dispatch.TrunkLevelSource`** — `_loaded_folders` baseline gains the loaded-folders map;
   `load` unpacks the 4th element; `save`'s changed-set diff also compares
   `actor.folder != self._loaded_folders.get(name)` so a folder-only change (incl. `"x"`→None
   unset) fires the delta write; the post-save baseline is refreshed.

5. **`query.py`** — `list_actors` gains `folders`/`no_folder` params (AND across dimensions, OR
   within `--folder`); `actor_show_block(actor, with_folder)` emits the carrier line. `show_actor`
   grows `with_folder=`.

6. **`stashlib.py`** — `with_folder(actor, folder)` (sets the model field; `with_group` unchanged).

7. **`cli.py`** — `actor folder set --to PATH <names…|->` / `unset` / `get`; `actor add --folder`;
   `actor find --folder`/`--no-folder` (mutually exclusive); `actor show --t3d-only`;
   `stash/prefab apply --folder` (added beside `--group`, no default).

8. **`dispatch.py`** handlers — `_actor_folder` (validate path, resolve names all-or-nothing, get
   prints `(none)` for unfoldered, set/unset save); wire `find` folder matching + pattern
   validation; `actor add` carrier precedence (explicit `--folder` overrides carrier; validate the
   resulting folder); `actor show` carrier emit; `_apply_set` folder stamp. A shared
   `_reject_nonlevel_target_for_folders(args)` guard makes ALL folder surfaces exit 2 on
   `--target stash|prefab` ("folders apply only to a level target"), checked BEFORE the source is
   resolved.

## The non-obvious trap (spec §2)
The delta-write changed-set is a content-diff, not a `touched` hint. A folder-ONLY change leaves
body+rank byte-identical, so without adding folder to the diff the write is silently dropped —
symmetric for `"x"`→None (unset). Step 4 adds the folder comparison; step-3/4 both directions are
regression-tested.

## Tests (spec §7)
`test_folderlib.py` (grammar accept/reject, §3 match boundary cases) + `test_folders.py`
(trunk round-trip incl atomic write; delta-write both directions incl unset; hash exclusion;
CLI guards incl trunk-only target + missing `--to` + bad path; carrier round-trip
`actor show A | actor add -`; `--t3d-only`; explicit `--folder` overrides carrier; non-carrier
`//` ignored; apply `--folder`/`--group` independence; Group⊥folder independence).

## Docs on build
`architecture.md` (a "Folders" subsection: the sidecar, the model field, the delta-write diff, the
carrier, trunk-only), `unrealed/t3d.md` (already notes the carrier — confirm the "folder is
uedctl-side, not a T3D construct" line), board `to-plan.md` → `done.md`.

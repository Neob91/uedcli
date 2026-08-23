# uedcli — architecture & development

## Terminology (use consistently)
- **level** — the authored content and uedcli's domain object / verb namespace (`level
  apply`, `Level`, `canonical_level_hash`/`level_hash`, "level name"). Substrate-agnostic.
- **map file** — the binary on-disk artifact only: `.dx` (Deus Ex) or `.unr` (Unreal/UT).
  Matches the engine's own `MAP SAVE`/`MAP EXPORT` verbs (`.unr` = "Unreal map").
- **T3D tree** — the directory form of a level: one directory per actor,
  `actors/<name>/{actor.t3d, order_value}`, under `<maps-dir>/<level>/` (the project's maps dir —
  the `uedcli.toml` `maps` key, default `<root>/maps/`; in the LUM repo `uedcli/maps/`) — the git-tracked
  trunk `level materialize` builds from. `order_value` is a per-actor LexoRank sidecar (the CSG order
  is the `(order_value, name)` sort); there is **no shared `order` file and no `packages` manifest**
  (packages resolve on demand at build). The actor's name is its directory name; the level's name is
  the `<level>` directory name.

"level" is never used for the file; "map" is never used for the abstract content. See
[`direction/terminology.md`](direction/terminology.md) (2026-06-23).

> **Direction:** uedcli aims to be a generic UnrealEngine-1 tool with Deus Ex as one baked-in
> substrate. Today it targets Deus Ex and `.dx` map files only. New code/naming should avoid
> DeusEx-only framing and map-file handling should grow to accept `.unr`; forward-looking
> guidance, not a refactor mandate (see `direction/scope.md` + `board/README.md` "Portability goal").

> **Git-native migration complete.** The durable source of truth is the git-tracked T3D trunk
> (`<maps-dir>/<level>/`); the session store and its core modules were deleted (git
> history holds them). See [`direction/trunk-and-editor.md`](direction/trunk-and-editor.md) for the net target.
>
> **Project layout (`direction/projects-and-config.md`, 2026-07-17 20:58):** a project is a repo with a free-standing
> **`uedcli.toml` at its root** (à la `pyproject.toml`) — the dir containing it IS the project
> root. The file declares `game` (required) + optional `paths`/`maps`/`prefabs`/`catalog`, all
> root-relative (defaults `maps/`, `prefabs/`, `texture-catalog/`). Discovery is a walk-up to the
> nearest ancestor containing `uedcli.toml` (`config.walk_up_root`; nearest wins). **The walk STOPS
> at a marker it cannot read** — malformed, not a regular file, or unstatable (a permission-denied
> dir) — and raises a named `ConfigError`, because climbing past one binds the caller to an OUTER
> project and silently edits the wrong tree. Both readers of a colon-separated dir list
> (`resolve_dirs` at compose time, `load_user_config` at load time) run the shared
> `config.reject_windows_drive` BEFORE splitting, so a pasted `C:\DX\System` is named as a
> Windows path instead of splitting on the separator and being reported as
> `dir must be absolute: 'C'`. All
> machine-local project state (stash, delivered preview maps, locks, staging) lives in the
> **self-ignoring `<root>/.uedcli/`** (`config.state_dir`): first creation
> writes `.uedcli/.gitignore` containing `*`, so it can never be committed.

## Premise (git-native trunk)
The durable source of truth is the git-tracked T3D trunk — one directory per actor under
`<maps-dir>/<level>/`, edited on ordinary git feature branches. The `.dx`/`.unr` map
file is a build artifact, never the merge unit. UnrealEd is not in the read/edit loop —
it is a build/preview tool reached only via a per-command ephemeral spin-up (`level materialize`,
`level preview`, the `stash` CSG generators). Every `actor`/`brush`/`poly`/`vertex` read and
mutation is pure model-side compute against the trunk (no `docker exec`, no `MAP EXPORT`); the LLM
issues semantic by-name commands; T3D is internal plumbing. Git is the history — `git commit` is
the user's own, uedcli never wraps version control.

This pivoted from the earlier editor-centric model (a live UnrealEd held the authoritative level,
every read a `MAP EXPORT`) and the interim session store (slices ≤3, since deleted). See
[`direction/trunk-and-editor.md`](direction/trunk-and-editor.md) (the 2026-07-05 git-native entries). The per-actor `.t3d` +
`order_value` layout was chosen so disjoint edits merge natively under `git merge` — verified in
[`spikes/2026-07-01-git-merge-t3d-tree/`](spikes/2026-07-01-git-merge-t3d-tree/findings.md)
and [`spikes/2026-07-05-git-merge-t3d-layout/`](spikes/2026-07-05-git-merge-t3d-layout/findings.md).

## Four layers (module map)
- **Command API** — `cli.py` (argparse verb surface), `dispatch.py` (routes verbs, records
  one command per mutation). Relative CLI file paths (`--out`, `--map`, `--from-t3d`, …) resolve
  against the **cwd** (standard CLI semantics; the repo-root join, the legacy `/repo/` remap, and
  the whole `repo_paths.py` module — CLAUDE.md-marker walk-up, `UEDCLI_REPO_ROOT`/
  `UEDCLI_PREFAB_DIR`/`UEDCLI_TEXTURE_CATALOG` env overrides — were deleted, 2026-07-17 20:58).
  **`tool_assets.py`** anchors the tool-INSTALL assets package-relative: `tool_root()` (the
  `Tools/uedcli/` dir holding the package, via `__file__`), `uned_dir()` (compose dir + UED22),
  `umodel_dir()` (`Tools/umodel_win32` — a SIBLING of the tool dir, deliberately outside the
  anchor; the packaging item owns how these ship under pipx/Nuitka).
  **`userdocs.py`** applies the same package-relative anchoring to the tool's own USER-facing
  prose: it resolves a **docs root** and enumerates the served `.md` set behind the
  `docs list|show|search` verbs (see "Commands" below). It is a leaf module — pure filesystem
  enumeration, no level, no project, no editor — imported lazily by `dispatch._dispatch_docs`.
  The top-level `dispatch()` guard converts expected failures to a
  clean stderr message + exit 2 — never a traceback: `_SelectionExit`/`_ProjectError`/
  `LevelSelectionError`/`ConfigError`; **`GeometryError`** (a degenerate/invalid brush from a
  model-side verb — actor add, brush clip/vertex, mover key, the builders, stash/prefab apply;
  `level materialize` catches its own build-time geometry error locally); and editor-driver failures
  (`DriverError`/`TimeoutError` from materialize/preview/stash CSG — `EditorNotReadyError` subclasses `TimeoutError`, so a startup death lands there too). Per-verb
  guards cover the rest: unreadable/missing/corrupt T3D input (`_read_t3d_input` for
  `actor add`/`stash capture --from-t3d`; `_read_prefab_or_exit` for the prefab library — both name
  the offender), a not-found stash id / prefab name (clean "not found", not a silent no-op or
  traceback), a **corrupt on-disk stash/prefab box** (the `--tree` `StashLevelSource`/
  `PrefabLevelSource` `load` and the stash lifecycle reads all catch a bad `meta.json`/sidecar → clean
  "cannot read …"), a corrupt texture catalog, and `actor add` on zero-actor input ("nothing to add").
- **Level model** — `model.py` (parse `MAP EXPORT` T3D → actors keyed by unique `Name`;
  brushes carry a `PolyList`; **vertex/Location coords are exact `Decimal`** — see "Coords";
  an actor's `Location`/`Name` live ONLY in their typed fields, never mirrored into `props` —
  `emit_actor` re-emits `Location` from the field, see `rationale/emit.md`, 2026-06-28),
  `emit.py` (the single write path: `clean` near-integer **noise** to the grid while
  **preserving genuine fractions**, multi-group quoting, **`Brush=` ref emitted after the
  brush block**), `normalize.py` (strip computed/volatile fields so diffs are authored-only; the
  identity hash vs the TYPED effective-value compare view — see "The compare view vs the identity
  hash"), `typedprops.py` (pure value semantics: a property's declared type as a `Field`, and the
  decode of a T3D value text into a comparable value), `classdefaults.py` (per-class memo of the
  decoded schema + defaults that feeds it),
  `geometry.py` (reject degenerate brushes pre-CSG; validates on `clean`ed coords),
  `clip.py` (Sutherland-Hodgman brush clipping), `vertex.py` (weld per-poly vertices into
  corners; **move-only** vertex editing), `builders.py` (model-side parametric brush builders
  — cube/cylinder/cone/sheet/staircase/spiral, plus the 2D-profile sweeps extrude/revolve;
  `make_brush_actor` also makes a **Mover** via
  `mover_class=`), `profile.py` (the swept generators' shared 2D
  layer: `--point U,V` parsing, weld/collinear cleanup, the non-simple-ring rejection, winding
  normalization, and the ear-clip + Hertel–Mehlhorn convex decomposition of a cap — no brush, no
  world coordinates, no T3D; it also OWNS `WELD`, which `builders` imports, because the reverse
  direction is a load-time cycle), `movers.py` (the mover domain module: `is_mover(actor, index)` — the schema-aware
  descends-from-`Engine.Mover` predicate, keyframe read/write
  accessors `mover_keys`/`set_key_pos`/`set_key_rot`/`remove_key`/`num_keys`/`set_num_keys`
  (the bounded 2..8 NumKeys setter behind `mover key count`; its validator `check_num_keys` is
  *shared* with the `actor prop set NumKeys=` route, which applies the same omit-when-2 write for a
  byte-identical result), and
  `canonicalize_mover` — folds an ingested `KeyNum≠0` mover to
  `KeyNum=0`; see "Mover support" below), `query.py` (list/show, `brush poly list` +
  `brush vertex list` metadata, flag decode; `actor find` uses `list_actors`, whose
  name/class/group matching is **case-insensitive** (`FName` semantics) and whose `name_glob` is
  the CLI's ONE pattern mechanism. **`actor show` (`show_actor`) does NOT glob** — it is a pure
  name resolver over `resolve_actor_name`, so a token matching no actor is the house
  `Actor not found: <name>` at exit 2, never an empty string printed as a blank line at rc 0;
  showing a SET is `actor find <pattern> | actor show -` (owner ruling 2026-07-25);
  `--prop` matching moved OUT of `list_actors` to the dispatch find handler (EFFECTIVE-value
  matching over the class schema/defaults, spec 2026-07-18 §7 — see the actor-prop section).
  **Spatial filtering** lives in the same find handler, alongside `--prop`: `actor find
  --within-bbox X0,Y0,Z0,X1,Y1,Z1` keeps actors whose world AABB is fully inside the box, a Decimal
  predicate (`writes.aabb_within`, edge-inclusive **within `emit.CLEAN_EPS`**) over
  `writes.actor_bounds` — the same full-transform world bounds `actor bbox` reports, so
  scaled/rotated brushes and point actors (a zero-size box at Location) are all handled with no new
  geometry (spec 2026-07-24-find-spatial; decision 2026-07-24). The tolerance is what makes the two
  agree: `actor bbox` reports tolerance-snapped values while `actor_bounds` carries the raw GMath
  rotator noise, so an exact compare left a rotated actor outside its own reported box — see
  [`rationale/reported-coordinates.md`](rationale/reported-coordinates.md).
  `parse_bbox` (`cli.py`) normalizes the two-corner token to Decimal `(lo, hi)`. Only the
  `--within-bbox` slice landed; `--near`/`--overlapping`/`--overlapping-bbox` remain unbuilt. The
  class filter is likewise resolved in the find handler (`dispatch._find_class_filter`, decision
  2026-07-19): `actor find` takes **`--exact-class`** (exact class match — the old `--class`, renamed)
  and **`--subclass-of`** (descendant-aware — expands, via the offline `ClassIndex.descends_from`, to every
  class PRESENT in the level that descends from a base). The two OR into one class-name set handed to
  `list_actors` (which still does the case-insensitive bare/FQCN `_class_matches`); `resolve_actor_name(level, name) -> str` and
  `resolve_actor_names(level, names) -> list[str]` perform case-insensitive actor-name
  lookup — exact match first, then case-fold scan — and are used by every verb that
  takes an actor name at the CLI; a miss raises `KeyError` which dispatch catches and
  converts to a clear "Actor not found: <name>" / "Actors not found: <n1>, <n2>" error
  with exit 2, never a bare traceback), `preview.py` (color wireframe viewer),
  `eventgraph.py` (pure Tag↔Event trigger-wiring analysis — `build_graph`/`lint_graph` + text/DOT/
  JSON formatters, the `event graph` verb; no editor, see "Commands" below),
  `upackage.py` (the ONE low-level UE1 package reader — header/tables/compact-index/tagged-
  property lists — every package decoder builds on; `direction/packages.md`, 2026-07-18 10:02 §5),
  `uprops/` (offline class-property SCHEMA + class-DEFAULT extraction from the game's own
  `.u` — the source of truth for `actor prop` validation and effective-value reads; four layers,
  `base` < `ufield` < `uclass` < `values`, behind a re-export-only root, so every `uprops.X`
  caller is unaffected),
  `propedit/` (the pure `actor prop set|unset|get` verb logic: dot-path grammar, planner,
  effective values, typed-field registry; six layers, `base` < `tokens` < `paths` < `structtext` <
  `fields` < `edit`, behind a re-export-only root; see "Class-property schema" below. Its
  `structtext.split_struct_text` does NOT re-implement the struct-literal grammar — the quote- and
  depth-aware member split (`typedprops.split_struct_members`) and the name/value `=` finder
  (`typedprops.top_level_eq`) are shared with the compare path, so a quoted comma
  (`(Msg="a,b",Count=1)`) parses identically on both sides; see
  [`rationale/propedit.md`](rationale/propedit.md)),
  `surface.py` (the per-face verbs `brush poly set|pan|rotate|scale`: the stored-attribute edit plus
  the pure texture-frame transforms, and the shared `resolve_targets` that turns `BRUSH:SELECTOR`
  tokens into a deduped `(brush, poly_index)` list — see "Surface edits" below),
  `polyalign.py` (the `brush poly find` producer + `brush poly align` verb: pure texture-vector
  math that makes one texture flow continuously across a face set — coplanar `--wall`/`--floor`
  and cylinder `--ring` wrap; world-space continuity written back per-brush via each brush's own
  inverse transform; see "Surface texture alignment" below).
- **Editor driver** — `driver.py` over `wine_ctl.py`: console `exec`, `BRUSH IMPORT/EXPORT`,
  `MAP EXPORT/IMPORTADD`, selection, `set_clipboard`+`edit_paste` (the clipboard WRITE path that
  makes a pasted brush selectable), screenshots. Reading the level back is `MAP EXPORT` only —
  the `EDIT COPY`→xclip READ path is gone (`Driver.edit_copy` deleted 2026-07-26 as uncalled).
  `wine_ctl` fast-fails on a dead/crashed editor (see unrealed/commands).
  **`map_save` waits for and verifies its own output** (returning the saved size). Driving is
  fire-and-forget — `wine_ctl exec` types the line, presses Return, settles 0.3 s and returns, long
  before the editor has written anything — and `MAP SAVE` answers nothing over the console, so the
  file is the only signal. The check must separate three outcomes a size poll conflates —
  finished, stalled and container-dead — so it stacks four independent signals:
  1. **A pre-`MAP SAVE` stat the file must differ from.** `container_stat` is taken before the
     command is typed; a post-save reading with the same `(size, mtime)` proves the editor wrote
     nothing, even when a complete map from an earlier run sits at that path. Both PRODUCTION callers
     (`apply._save_and_swap_verified`, `native.csg_golden.capture_case`) save to a fresh uuid path,
     so `before` is `None` and this signal is dormant for them — it guards the FIXED-path callers,
     i.e. the spikes that save to a constant name and any re-save over a real map.
  2. **`stable_reads` equal readings spanning at least `settle` seconds** (defaults 3 and 3.0 s at
     `poll=1.0`). The retired rule — two equal reads one poll apart — accepted any write that merely
     went quiet for a second. Cost: every save is accepted ≥ `settle` after the file stops growing,
     so `level materialize` pays a few extra seconds.
  3. **A structural check of the written package** (`driver.package_header_problem`, fed by
     `container_file_head`'s 36-byte `od` read). The only signal that can tell finished from
     stalled: a part-written map holds a steady size exactly like a finished one, so stability can
     never distinguish them, while the bytes can. It requires the magic, non-zero table counts, every
     table offset inside the file, and enough bytes after each offset to hold that many entries at
     their minimum encoded size. The blind window, measured over the 264 packages the real
     composed path resolves (`spikes/2026-07-25-map-save-mechanism/measure_header_window.py`): over
     the 101 editor-written maps (the 120 `.dx` minus the 19 `Native*.dx` uedcli's own native build
     wrote — not `MAP SAVE` output, so they must not set the bar) the required end lands at
     98.4–99.7 % of the real size (median 99.5 %) versus 93.5–98.9 % (median 98.3 %) for an
     offsets-only rule — so a truncation in the last ~1.6 % of a map still passes; the room rule
     shrinks the window several-fold rather than closing it. Closing it needs a full table parse on
     the host (`upackage.load_package` after `docker cp`); not done here because the driver checks a
     container-side file and `apply`'s post-verify re-reads the installed map anyway. Same 9
     little-endian u32s `upackage.py` parses (the driver keeps its own copy of the magic to stay
     container-only; a test pins the two equal); it decodes no table, so it judges completeness, not
     content. The editor serializes into `Save.tmp`, patches the header last in the temp, then moves
     it onto the destination (📖 `core.dll` strings, 2026-07-25 — `unrealed/commands.md`
     "`MAP SAVE` writes `Save.tmp`" and `spikes/2026-07-25-map-save-mechanism/`); whether that move
     is a rename or a copy is undetermined, so a truncated destination may not be reachable at all,
     and none has ever been observed (the one report was retracted by
     `spikes/2026-07-15-native-materialize/sections/91-leaves-overproduction.md`). The check is kept
     because it costs one 36-byte read at the accept point and also rejects a stale non-package at
     that path. A stable-but-incomplete file is not accepted and not an instant error — polling
     continues to `timeout` (default 600 s), re-reading the header at most once per `recheck` (30 s)
     per size (bounded, since an undetermined move mechanism means the destination's header cannot be
     assumed immutable) — then `DriverError` names the path, the structural reason and the elapsed
     time.
  4. **Liveness from a probe sentinel, not an exit code.** Every container-side file read on this
     verification path goes through `Driver._container_probe`, which prefixes the in-container
     `sh -c` snippet with a `printf` of `driver.PROBE_TAG`; the tag can only appear on stdout if
     docker really started a shell in a live container, so its absence is the container failure and
     the exit code is ignored. Measured live 2026-07-25: a stopped container, a missing container
     and a permission error all make `docker exec` exit 1 — the same code `stat` uses for
     "no such file" — so the retired "only exit 1 means no file" rule had an unreachable failure branch and misread every real container
     death as "not written yet", polling a corpse for the full 600 s before blaming the editor. Each
     probe is bounded by `driver.PROBE_TIMEOUT` (60 s) and a `TimeoutExpired` becomes a `DriverError`,
     so a hung dockerd cannot park a caller forever. The probes answer `missing` / `statfail` /
     `odfail` distinctly: only genuine absence reads as "no file yet", every other failure raises at
     once instead of costing a full timeout.

  Without this a wedged editor writes nothing and the failure surfaces far downstream as an opaque
  `docker cp` exit 1 blaming the wrong subsystem. (Driver's other `docker exec` calls — `_wine_ctl`,
  `dexec_bash`, `set_clipboard`, `log_size`, `read_log_since`, `dismiss_blocking_dialog` — do not go
  through `_container_probe` and are still unbounded; `board/inbox/` carries that chore.)

  **Every docker subprocess OUTSIDE `driver.py` is bounded.** `editor.py`'s container lifecycle
  (`_is_running`, `_reap_container`, `_spin_up`'s `docker compose run`, each `_wait_ready` poll,
  `stop_editor`), `xfer.py`'s `cp_in`/`cp_out`/`remove`, and `store_export.export_dx_t3d`'s three
  execs all pass a `timeout=`; a query/teardown call that blows it is SWALLOWED where it runs on a
  teardown path (mirroring `preview_game.stop_game`) and otherwise raises a named `DriverError`,
  which the materialize/preview guards already surface as a clean exit 2. `_wait_ready`'s bound is
  the load-bearing one: an unbounded `docker exec` inside its deadline loop meant the deadline could
  never expire, so `ensure_editor`'s readiness retry never fired. `export_dx_t3d` also removes its
  `/work/ucc_export-<uuid>` dir in a `finally:`, so a failed export strands nothing. See
  [`rationale/containers.md`](rationale/containers.md).

  **Most `Driver` methods have no uedcli-command caller.** After the model-side pivot and the
  2026-07-16 deletion of the editor-screenshot preview flow, ~17 of them are called only by the
  committed spike harnesses under `spikes/` and by the default-deselected integration suite —
  populations a grep over `uedcli/` does not see, so a green `bin/test` would not catch their
  removal. They are retained (owner ruling 2026-07-26); only genuinely uncalled symbols were removed
  (`select_inside`, `edit_copy`, `map_sendto`, `select_by_csg`, `editor.novnc_url`, and the
  never-raised `EditorBusyError`). Before re-proposing a dead-code sweep here, read
  [`rationale/driver.md`](rationale/driver.md), which carries the measurement.
- **T3D tree I/O** — `t3dtree.py` is the ONE shared per-actor-tree reader/writer
  (`write_actor_tree`/`read_actor_tree` over `actors/<name>/{actor.t3d, order_value[, folder][, labels]}`, plus
  the LexoRank rank algebra, the coordination-free name allocator, the `actor.t3d` body strip/inject,
  `check_safe_segment`, and `write_sidecars`/`read_sidecars` for the beside-`actors/` extras). ALL
  THREE T3D trees go through it (`direction/trunk-and-editor.md`, 2026-07-18 23:01 UTC — "stash, prefab, and trunk MUST
  share ONE T3D tree format"): `trunk.py` re-exports it under the level-facing names
  (`read_level`/`write_level`), `stash_register.py` and `stashlib.py` wrap it for the stash/prefab
  boxes. (The old `tree_io.py` flat-tree reader + its `safe_name` URL-quoting are GONE — the dir name
  is the identity verbatim, guarded by `check_safe_segment`.) `uuid7.py` (ephemeral-editor id).
- **Materialize** — `apply.py`. The build verb is **`level materialize`** (`apply.run_materialize`,
  git-native slice 3): a PURE build of the git-tracked T3D trunk into a `.dx`/`.unr` map file via a
  **per-command ephemeral editor** — ensure-load the composed search path, FULL RE-IMPORT, `light_apply`,
  MAP SAVE, H3 post-verify (in that same ephemeral container), atomic swap; refuses to overwrite `--out`
  unless `--overwrite`. `run_materialize` REQUIRES a `schema_resolver` (the post-verify types
  both sides against the game's real class schema + defaults and has no zero fallback). No session, no reconcile, no backup, no git commit. `materialize.py`
  (the FULL RE-IMPORT seam), `packages.py` (manifest resolution + the full live `ensure_load`:
  absolute `Paths` ini-edit + explicit `OBJ LOAD` per package, shared by `apply._materialize`
  and `qualify.export_and_qualify`), `store_export.py`/`dxpkg.py`/`verify.py` (offline UCC `.dx` export + manifest +
  independent post-verify; `dxpkg.transitive_closure` is the manifest extractor used by all
  three call sites since 2026-06-20 — the TRANSITIVE package closure, not just a `.dx`'s direct
  import-table deps, recursing into code AND content packages alike — see the package-extraction
  design spec. **`dxpkg.parse_header` raises `upackage.SchemaError` on ANY malformed or truncated
  input** — the same class, from the same canonical home, that `upackage.load_package` raises, so
  a corrupt package names the offending file and exits 2 instead of escaping as a bare
  `struct.error`/`IndexError`. `SchemaError` subclasses `ValueError`, so the existing
  `substrate stub` handler in `dispatch.py` catches it unchanged).

## The core write pattern (model-side; the editor is touched only at `materialize`)
Every read and mutation is pure model-side compute against the git-tracked trunk, no editor in the
loop:
1. `src.load()` (`TrunkLevelSource.load` → `trunk.read_level`) reconstructs the level from the
   per-actor trunk dir (`actors/<name>/{actor.t3d, order_value}`). No `docker exec`, no
   `MAP EXPORT`, no liveness check.
2. Build/transform the `Actor`/`Brush` in the model (move, clip, set poly fields, …);
   `geometry.validate_brush` rejects coincident/degenerate/non-planar polys (degenerate
   geometry would crash CSG at the eventual materialize).
3. `emit.emit_map` renders canonical T3D (winding preserved; `Brush=` after the block);
   **modify = delete-then-readd** under the same `Name` in the model (clipping/vertex/poly
   edits all ride this path).
4. `src.save(verb=…, args=…, level=level, touched=…)` (`TrunkLevelSource.save` →
   `trunk.write_level`) writes the per-actor trunk from the already-transformed in-memory model as
   a **DELTA under a short per-level flock** (`<maps-dir>/.locks/level-<name>.lock`,
   resource-adjacent + self-ignoring like the catalog locks; `direction/trunk-and-editor.md`, 2026-07-18 08:08 +
   the same-day follow-up): only actors whose **body or rank differs from this process's load
   snapshot** are written (content-diff via `read_level_with_bodies` — not the `touched` hint),
   each per-actor write is **atomic** (rank first, then `actor.t3d` via tmp + `os.replace`, so a
   lock-free reader never sees a torn body and a killed writer can't wedge the level), a new
   actor's `order_value` is minted appended-after-all, and **only the actors THIS process
   deleted** (its loaded set minus its current set) are pruned. An on-disk actor dir the process
   never loaded — or loaded but didn't change — is left alone, so disjoint concurrent
   adds/edits/deletes from parallel sessions compose instead of a stale model stomping them.
   Equal freshly-minted `order_value`s from concurrent adds stay harmless (the name tiebreak,
   decisions 2026-07-05 15:11). There is no shared `order` file, no `packages` manifest, and no
   per-command blob log.

The editor only sees the level at **`level materialize`** (`apply.py` → `materialize.py`), which
FULL RE-IMPORTs the merged result:
- **point actors → `MAP IMPORTADD`** (exact location);
- **brushes → `EDIT PASTE`** (clipboard + paste), pre-shifted −32uu to cancel paste drift —
  the *only* verb that yields a selectable brush (see unrealed/quirks);
- LevelInfo materializes first (D-I); `MAP NEW` supplies the default LevelInfo, replaced by
  the imported singleton.
- **Points before brushes, always** (2026-06-21): `writes._re_add` splits any re-add batch
  into ONE `MAP IMPORTADD` for every point actor followed by ONE `EDIT PASTE` for every brush —
  so a brush listed BEFORE a point actor in the authored/merged order still lands AFTER every
  point actor in the live editor's resulting actor list. `materialize.levelinfo_first_order`
  (despite its name) predicts this full grouping — LevelInfo, then points, then brushes, each
  group keeping its relative order — not just "LevelInfo first"; `apply._materialized_order`
  and `materialize()`'s own `import_order` both call it, so the predicted and actual orders
  agree. This doesn't violate "actor order = CSG precedence" (`materialize.py`'s module
  docstring): CSG precedence is a brush-to-brush concern, and point actors don't participate
  in CSG, so grouping them ahead of brushes changes nothing CSG cares about — only the
  recorded `level.order`, which `canonical_level_hash` folds in, so a wrong prediction here
  spuriously fails H3 post-verify on a level whose authored order interleaves the two kinds
  (confirmed live debugging a base-content map's first apply).

## The `LevelSource` seam and `--tree` (level / stash / prefab)
Every content verb is source-agnostic about *where* the actor set lives: it does
`src = _resolve_level_source(args)`, then `level = src.load(); …transform…; src.save(verb=…,
args=…, level=level, touched=…)`. `_resolve_level_source` is the ONE place that picks the box, so
the same verbs edit any of three T3D "boxes" — the ambient `$UEDCLI_LEVEL` level (the default), a **stash**, or a
**prefab** — with zero per-verb logic. Three `LevelSource` classes implement that `load()`/`save()`
seam (all in `dispatch.py`):
- **`TrunkLevelSource(trunk_dir)`** — the git-native trunk (`trunk.read_level`/`write_level`);
  holds each surviving actor's `order_value` between load and save (see the write pattern above).
- **`StashLevelSource(reg, id)`** — a stash register entry (`stash_register.read_stash`/
  `write_stash`, atomic swap, `force=True`).
- **`PrefabLevelSource(root, name)`** — a durable prefab (`stashlib.read_prefab`/`write_prefab`).

Stash/prefab are now the **same per-actor T3D tree** as the trunk (`direction/trunk-and-editor.md`, 2026-07-18 23:01
UTC), so their on-disk `order` is derived from the per-actor `order_value` sort (not a flat `order`
file). The wrappers still speak a flat `order` **list** as their public currency — an internal
detail derived on write (`stashlib._ranks_for`: preserve a surviving actor's rank, append a new one)
and re-derived by the sort on read — so the `LevelSource.save(ranks=…)` CSG-override channel stays
trunk-only (the ordering verbs still reject a stash/prefab target). Their `_ranks` stays `{}` (no
content verb reads it; only `level status`/`doctor` do, and those are level-only). Both stash/prefab
sources guard the `order`→blob join with `if n in blobs` (a torn/partial tree loads cleanly, never a
bare `KeyError`), re-attach each member's stored `folder` on load (persisted per member — full trunk
parity), and `save` recomputes the **texture-only** `packages` (`stashlib.referenced_packages`) and
re-writes the per-member folders while preserving `meta` (the capture anchor). The prefab's old
single-JSON meta-clobber trap is GONE: `packages` is its own sibling file and `order` is the
`order_value` sort, so the sibling `meta.json` holds ONLY the capture extras (`anchor`/`ts`) and
cannot clobber structural state.

**The default level is the ambient `$UEDCLI_LEVEL`** (a bare level name), read by
`level_select.resolve_level(env_level=os.environ.get("UEDCLI_LEVEL"), maps_dir=…)` — per-process, so
there is no shared mutable pointer to race on (it replaced the old `.uedcli/current-level` pointer +
`level select` verb; `direction/trunk-and-editor.md`). The env value is `strip`ped, blank ⇒ unset,
`_check_safe_level`d, and existence-checked; unset/malformed/nonexistent → a clean exit-2
`LevelSelectionError` naming BOTH set-methods, never a silent empty level. When the env fallback is
used, `_resolve_level_source` sets `src.from_env = True`.

**Per-command override** is `--tree KIND/NAME` (KIND ∈ `level|stash|prefab`; renamed from `--target`
2026-07-20 — the three boxes are one T3D-tree format), added to the shared content verbs via the one
`cli._tree_flag(parser)` helper. `_resolve_level_source` splits on the FIRST `/` (so NAME may be
nested, e.g. `stash/hangar/arch`), runs `stashlib.validate_member_name(name)` **before constructing
any source** (mandatory — `read_stash`/`read_level` do NOT validate the top name, so `--tree
stash/../../x` would otherwise escape on both load and save), resolves the project, and per kind
applies the not-found guard then returns the matching source (`from_env` stays `False` — explicit).
The flag rides the content verbs that MUTATE or lack a per-kind equivalent
(`actor add/delete/move/prop/rotate/find`, `brush clip/replace/vertex list|move/poly
list|set|find|align`, `mover key count/move/rotate/remove/list`), the READ verbs (`actor show`,
`level status`, `level doctor`, `event graph`, and `stash capture`'s SOURCE), **and — level-kind only
— `level materialize`/`level preview`** (a build/preview of a *world*; `--tree stash|prefab` is
rejected via the shared `_resolve_level_only` helper since a captured actor-set has none, and
`stash`/`prefab preview` exist for those). For the box-inspecting reads, `_level_status`/
`_level_doctor` use the source's uniform `display_name`/`kind` (a stash/prefab has an empty `_ranks`,
so no duplicate-order finding, and `level status` prints a git hint only for a `TrunkLevelSource`).
`stash capture --tree` names the capture SOURCE (rejected in combination with `--from-t3d`). It stays
**deliberately absent** from the generators (`actor build`/`brush build`, which target nothing) and
`actor preview` (a per-kind `stash`/`prefab preview` already exists).

**Mutation visibility echo.** Because a per-shell env var still lets a *stale* `export` silently edit
the wrong level, a **mutating** verb that resolved from the ambient env (`src.from_env` and no
explicit `--tree`) echoes ONE line to **stderr** — `editing level 'X' (from $UEDCLI_LEVEL)`
(`materializing …`/`capturing from …` per verb). It lives at the mutation seam
(`TrunkLevelSource.save`, once per save via `_announce_env_level`), so it self-limits to writes with
no per-verb list; reads never reach `save`, and an explicit `--tree` leaves `from_env` `False`
(silent). *(spec in board item `level-is-the-ambient-uedcli-level-target-tree`; decisions 2026-07-12 03:06 +
2026-07-19 12:30 + 2026-07-20 21:30 UTC.)*

## Coords: exact Decimal, fractions preserved
Vertex and `Location` coords are stored as **`decimal.Decimal`** (parsed from the T3D
strings), and the CLI takes coordinates as one `X,Y,Z` token parsed by `cli.parse_coord`
(Decimal, integer or decimal, negatives via the `_CoordArgumentParser` leading-dash fix).
**`cli.parse_decimal` is the ONE scalar-number validator** every Decimal-valued argument goes
through — `brush clip --offset` directly, `parse_coord`/`parse_bbox` per component. The bare
`Decimal` constructor must never be an argparse `type=`: it raises `decimal.InvalidOperation` (an
`ArithmeticError` argparse does NOT convert, so a typo escaped as a traceback) and it *accepts*
`nan`/`snan`/`inf`. `parse_decimal` rejects both as a clean `ArgumentTypeError`; `parse_pan` stays
outside it because it is int-valued and `int()` already rejects those. See
[`rationale/cli.md`](rationale/cli.md).
Decimal — not float — so authored fractional coords carry no binary drift and match stored
vertices exactly. `emit.clean` is the single grid rule: a coord within **`CLEAN_EPS`
(0.001)** of an integer snaps to it (kills editor/float noise like `511.999969→512`), but a
genuine fraction (`32.5`, a semisolid's `70.71`) is **preserved at 6-dp**. `geometry`
validates on `clean`ed coords, so a planar *slanted* face is no longer pushed off-plane by
integer snapping — which is what fixed the cone-clip non-planar failure. Computed-geometry
modules (`clip`, `builders`, `preview`) compute in float and finalize back to Decimal via
`clean`; texture vectors (`Normal`/`Origin`/`TextureU/V`) stay float (the editor recomputes
the normal from winding). Fractional vertices are editor-native and CSG-safe (see
unrealed/quirks).

## Invariants
- **D1 — selection fidelity.** Act only on the editor's real read-back, never the model
  prediction; refuse on under-selection. Brushes select under containment (box ⊇ brush);
  point actors by pivot. (Historically brush selection was thought impossible — it was an
  IMPORTADD artifact; paste-added brushes select fine.)
- **D2 — modify = delete-then-readd with rollback.** Capture the target's actual block
  before delete; on any re-add failure, restore the original (+ swept neighbours) and
  re-raise; `level` advances only on success. Never a bare re-import (live-name collision
  duplicates).
- **D6 — uedcli owns the `Name` namespace.** `allocate_name` mints `Uedcli<Class><n>`
  checked against the level; `add_actor` refuses a live-name collision.
- **D5/D7 — parallelism = N per-command ephemeral editors, no shared session.** Each
  editor-driving verb mints its own throwaway container (`uuid7`), so concurrent invocations
  never share editor state.
- **D8 — `PrePivot` is load-bearing; never rewrite it implicitly.** An actor's pivot is part of
  the actor→world transform (`Location + R·(vertex − PrePivot)`) and `Mover`s rotate about it,
  so a transform must leave `PrePivot` byte-for-byte intact unless changing it is the verb's
  explicit intent. Re-centering/snapping/baking a pivot is its own opt-in verb, never a side
  effect of clean/normalize/emit. (See unrealed/quirks "Pivots".)

## Stash / prefab (captured actor sets)
A stash, a prefab, and a level trunk are one on-disk format — the per-actor T3D tree
`actors/<name>/{actor.t3d, order_value[, folder]}`, read/written through the single shared
`t3dtree` code path (`direction/trunk-and-editor.md`, 2026-07-18 23:01 UTC). Any per-box extras (`packages` list +
`meta.json` capture anchor/timestamp) sit beside `actors/` (via `t3dtree.write_sidecars`/
`read_sidecars`); the trunk has none. The stored `actor.t3d` is byte-identical to the trunk's (the
`t3dtree` consistency test pins this).

A **stash** is a private, per-project register entry at `<root>/.uedcli/stash/<id>/`.
`stash_register.FileStashRegister.{write,read,list,drop}_stash` own it (wrapping `stashlib`'s
shared `write_tree_box`/`read_tree_box`), built at the ONE `dispatch._stash_register_for` seam (the
self-ignoring state dir — `config.state_subdir(root, "stash", create=True)`); capture normalizes
the set to its bbox-min corner (recording the pre-shift anchor) so it places predictably. Stash is
machine-local throwaway, so a stale OLD flat-format entry (loose `actors/<name>.t3d` files) is
treated as **absent** (read-empty AND `exists()==False`) and simply regenerated — no migration path.

A **prefab** is the durable, tracked, shareable tier-2 form: the per-actor tree
`<library-root>/<name>/{actors/…, packages, meta.json}` under the resolved project's prefabs dir
(`config.project_prefabs_dir`, the `uedcli.toml` `prefabs` key, default `<root>/prefabs/`; in the
LUM repo `Prefabs/`), overridable per-invocation via `--prefab-dir` (with the flag no project is
needed; with neither a project nor the flag → clean exit 2). `stash promote` copies a register entry
there; `stashlib.{write,read,list}_prefab` are the pure file I/O. `prefab` reads
(`list`/`show`/`preview`/`drop`) touch only the tracked dir; only `prefab apply` resolves the
selected trunk level. **Migration is a HARD CUTOVER** (`direction/trunk-and-editor.md`, 2026-07-18 addendum, sub-choice
1): there is NO dual-read of the pre-per-actor-tree single-blob prefab (`<name>.t3d` + `<name>.json`)
— reading one raises `stashlib.OldFormatPrefab`, surfaced as a clean exit-2 message naming the
prefab (`old-format prefab 'X' — re-capture it`), never a traceback; the name still LISTS so the
error surfaces on use rather than a misleading "not found". Both stash and prefab persist a
**per-member `folder` sidecar** (full trunk parity, sub-choice 2), threaded through the capture →
store → read → apply channel; `stash/prefab apply --folder` OVERRIDES the stored folder at placement,
absent it a member lands in its stored folder.

**Apply is a model-side merge into the trunk, no editor.** `dispatch._apply_set` (shared by
`stash apply` and `prefab apply`) reads the captured set via the `LevelSource` seam, translates it
to the placement anchor (`--at` → bbox-min corner — kept deliberately, see
`direction/conventions.md` "PLACEMENT anchors the bbox-min corner; ROTATION pivots a member's own
Location"; else the captured `anchor` for a stash, or the world origin for a prefab),
auto-allocates fresh random-suffix names, sets `Group`, appends to `order`, and `src.save(...)`s the
trunk — validating all geometry up front (all-or-nothing), no editor, no paste, no `MAP SENDTO`, no
rebuild. The trunk has no package manifest (the load set derives on demand at `level materialize`),
so packages are not recorded; `stashlib` supplies the pure value transforms
(`translate`/`with_group`/`normalize_for_capture`/`referenced_packages`). The canonical level hash is
order-dependent (`normalize.canonical_level_hash` folds in `level.order`) so a reorder reads as a real
CSG state change.

## The compare view vs the identity hash (`normalize.py`)

Two different reductions of a `Level` live in `normalize.py`, and conflating them was a live bug
class (`direction/materialize.md`):

- **`canonical_level_hash(level)` — the IDENTITY hash.** Pure and **schema-free**: it hashes exactly
  `canonical_actor_t3d` per actor (Name-sorted) plus `level.order`, with nothing folded away. Its
  main consumer is `preview_game.materialized_dx`, which names the built map
  `materialized__<level>__<hash12>.dx` and **reuses that file whenever the hash matches** — so any
  equivalence folded in here is a pair of different levels collapsing onto one cache entry, i.e. a
  preview showing a map built from something else. Erring strict only ever costs a rebuild.
- **`compare_view(level, *, defaults) -> CompareView`** — what the H3 post-verify compares:
  `{canonical actor name -> typedprops.ActorValues}` + the canonicalized order. It rewrites the
  engine-managed LevelInfo actor Name to a fixed sentinel, then per actor builds the **typed
  effective-value view** (`_actor_values`) plus a float32-quantized, `Normal`-free geometry text
  (`_geometry_text`, on a throwaway copy of the brush). `verify` uses this ONE view for both the
  equality check and `_first_diff`'s diagnostic — there is no second, hand-mirrored copy of the
  reduction to drift out of step.

**The typed compare is the compare-side half of UnrealEd's member-precise default-diffing**
(`unrealed/t3d.md`): the editor writes only what differs from the CLASS DEFAULT, uedcli's producers
write everything, so comparing their TEXT is comparing two spellings of one value. Instead, each
actor resolves to its **effective typed values** — for every property, the stored value if the actor
states one, else the class default — decoded by the property's DECLARED TYPE:

- a float compares numerically and at float32 (`StayOpenTime=4.0` == a default rendered `4`);
- an int compares VERBATIM, never reduced mod anything (an FRotator component such as
  `Yaw=-131072` survives the round-trip exactly);
- an enum compares by ORDINAL, so the T3D name (`SHEER_ZX`) and a struct-member default decoded as
  a number are one value;
- a struct expands MEMBER-WISE: a member the text omits takes the corresponding DEFAULT member (the
  engine's own import rule), never zero — so `(Yaw=16384)` == `(Pitch=0,Yaw=16384,Roll=0)` and an
  `Engine.Camera`'s `Location=(X=100,Y=200)` is `(100,200,300)`;
- a property the actor omits entirely resolves to the class default, else to **the type's zero taken
  from the schema** — which is what makes an explicit `LightRadius=0` and an omitted line one value
  while an explicit `Title="0"` (a StrProperty, zero = `""`) stays distinct from an omitted one;
- the editor's `Tag=<bare class>` default-stamp is dropped, but only where the class does not itself
  default `Tag`.

Two precision rules ride along, applied to both sides: every float compares at **float32** (the
precision the editor stores them at), and a `Location` axis is first put through the trunk emit's
sub-grid snap (`emit.clean`, `CLEAN_EPS = 0.001`) — the editor's export carries float32 noise
(`Y=7215.999512`) where the trunk holds the snapped `Y=7216.000000`, and comparing without it fails
~1% of the actors of a real retail export.

A property with **no** declared type and **no** class default yields `typedprops.ABSENT`, which
equals nothing — the compare never fabricates a zero to match an omission against.

Types + defaults come from `classdefaults.ClassDefaults`, a per-invocation memo over ONE shared
package map (~0.1-0.3 s cold per class, ~0.01 s amortized), decoded offline from the game's own `.u`
via `uprops.resolve_class_properties` + `resolve_class_defaults` (plus enum value names and struct
member layouts, compiled into `typedprops.Field` trees). `apply.run_materialize` resolves every
distinct class BEFORE creating the editor container (`_level_defaults`), so an unresolvable class
costs ~0.1 s and `exit 2` naming the actor and its class rather than failing after a ~100 s build;
`defaults` is a REQUIRED argument of `verify_dx_matches` with **no zero fallback** (assuming "the
default is zero" is the bug this exists to remove).

**Absent vs zero at ingest.** UnrealEd omits a `Location` axis equal to the class default member, so
`Location=(X=100,Y=200)` does not mean Z=0. `model.parse_t3d` is schema-free (it is also the trunk,
stash, prefab and generator-snippet reader), so it keeps the 0-filled triple the geometry math needs
and records the verbatim text in `Actor.location_text` — a contained side-channel the compare seam
expands member-wise. It is self-invalidating: trusted only while it still parses back to the current
`location`, so any mutation makes the compare fall back to "all three axes stated", and no mutation
site has to remember to clear it.

**The typed expansion is compare-only — the write side never omits an actor property to mean zero.**
`canonical_actor_t3d` (the durable trunk emit, the `MAP IMPORT` payload and `actor show`) keeps every
authored property verbatim, so its bytes never depend on which packages are installed. An omitted
property re-imports as the class default, so omitting one where the default is non-zero silently
builds a wrong map that post-verify passes (both sides share the mistake) — see the three fixed
instances in `unrealed/t3d.md`.

**A polygon sub-field is the deliberate exception, omitted when zero.** `Flags` and `Pan` inside a
`Begin Polygon` block are `FPoly` fields with no UnrealScript class behind them, so they have no class
default — absent means a fixed zero, always. `emit_polygon` therefore writes neither when zero. For
`Pan` that is forced, because it is exactly what `MAP EXPORT` writes back (the editor never emits a
zero pan; it does sometimes emit `Flags=0`, harmless either way since both compare sides re-emit
through `emit_polygon`). The geometry half of the compare is a whole-text compare of
`_geometry_text`'s `emit_brush` rendering, so a redundant `Pan U=0 V=0` in the intended level is a
difference wherever it sits and aborts the build. It does not even report as a pan difference:
`verify._first_diff` pairs the two texts by line number, so the extra line shifts every following one
and the message names a vertex. That shipped: `brush poly align` on a freshly built brush (no prior
`Pan` on any face) made every subsequent `level materialize` exit 2 with nothing written, until
2026-07-26. See `unrealed/t3d.md` "A poly sub-field has NO class default" and
[`rationale/emit.md`](rationale/emit.md).

## Folders (uedcli-side actor organization)
A **folder** is a per-actor, uedcli-side, hierarchical dotted organization path (`castle.tower.roof`)
that lets a big build be addressed as a tree ("retexture every `**.roof`"). It is stored in the
trunk, **never emitted to the built map**, and is a **separate dimension** from the T3D `Group=`
prop (which is retained, parsed, and emitted exactly as before — the two never interact). Spec
board item `actor-folders-hierarchical-actor-organization`; `direction/organization.md`, 2026-07-18 12:14/12:32/12:45 UTC.

- **Model + sidecar.** `Actor.folder: str | None` is a **typed field** (like `location`), NOT a
  `props` entry; `None` = ungrouped. It persists as a per-actor **sidecar file** `folder` beside
  `order_value` in the trunk (`actors/<name>/folder`, one line). `emit`/`canonical_actor_t3d`
  **never serialize it**, so a folder is naturally out of the T3D body, the materialized `.dx`, and
  the canonical level hash (materialize is byte-identical regardless of foldering — folders are
  authoring metadata with zero build effect, same class as lighting/BSP). One path per actor (no
  comma multi-membership — cross-cutting tags stay on `Group`). Chosen a sidecar, not a `Group=`
  prop, so a deep dotted path can't overflow UnrealEd's FName length limit.
- **Trunk I/O (`trunk.py`).** `write_level` writes the `folder` sidecar **atomically** (tmp +
  `os.replace`, like `actor.t3d`) when set, and **removes** it when `None` — loads take no flock, so
  a bare `write_text` would let a lock-free reader see a truncated first line and misreport the actor
  as ungrouped. `read_level_with_bodies` returns a **4th** element (name→folder) and sets
  `actor.folder`. **The delta-write trap:** the changed-set diff in
  `TrunkLevelSource.save` is a content-diff of body + rank, and a folder-ONLY change leaves both
  byte-identical — so the diff **also compares the folder** against the `_loaded_folders` baseline,
  symmetrically firing on **any** delta INCLUDING `"x"`→`None` (unset); without it `actor folder
  set`/`unset` would silently no-op.
- **Grammar + matching (`folderlib.py`, pure).** A **stored path** has non-empty `.`-separated
  segments, each `[A-Za-z0-9_+-]+` (case preserved, matched case-insensitively). A **query pattern**
  (`actor find --folder`) adds the globstar tokens: `*` = exactly one segment, `**` = any depth (zero
  or more); `?`/`[`/`]`/`***`/mixed `a*b` are rejected (exit 2 — never leaks fnmatch semantics). The
  **normative match** (spec §3): a **wildcard-free** pattern selects the folder AND its whole subtree
  (`folder == X or folder.startswith(X + ".")`); any wildcarded pattern is a pure segment-list glob
  with **no** subtree extension (so `**.roof` matches roof NODES only — the `--folder` help documents
  this asymmetry). `folder is None` matches no pattern; select the ungrouped set with
  `--no-folder`.
- **The `// uedcli-folder:` carrier (`actor show` ↔ `actor add`).** The interchange form of a folder
  is a **bare `// uedcli-folder: <path>` T3D comment** inside the actor block. `actor show` emits it
  by DEFAULT (`query.actor_show_block`, via the shared `emit.inject_carriers` seam) — importable T3D that
  ALSO round-trips the folder, because the UnrealEd importer **silently strips bare `//` lines** (spike
  `spikes/2026-07-18-t3d-comment-tolerance/`, `unrealed/t3d.md`; engine-facts regression pins the strip).
  The **generators** (`brush build`/`actor build`) emit it too — `emit.emit_actor_t3d` runs the same
  `inject_carriers` when the actor carries a folder/labels — so `brush build --folder …` authors it at
  birth. `actor add` parses that bare line back into the sidecar (`model._FOLDER_CARRIER` in
  `_parse_actor`) and strips it from the stored body. `actor show --t3d-only` suppresses the comment for a
  byte-exact editor export. **A stored trunk body never contains the line** — the carrier is emitted ONLY
  by `emit_actor_t3d`/`actor_show_block`, NEVER by `emit_actor`/`canonical_actor_t3d` (which write the
  trunk body / editor-import map). `actor add` is a **pure carrier-consumer** — it has no `--folder` flag
  (2026-07-24 17:04); the incoming carrier wins.
- **CLI + guards.** `actor folder set --to <path> <names…|->` / `unset` / `get` (get prints `(none)`
  for ungrouped). `set`/`unset` are **PRODUCERS** — touched Names to stdout, the count to stderr — so
  they chain like the sibling `actor label` verbs (the two organizational dimensions behave
  identically); `get` is a query and prints the folder VALUES. Also: the
  **generators** `brush build`/`actor build --folder`; `actor find --folder <pattern>`
  / `--no-folder` (mutually exclusive; ANDs across dimensions, ORs within `--folder`); `stash/prefab
  apply --folder` (a copy-verb exception that keeps its flag — added **beside** `--group`; a member
  DEFAULTS to its stored folder and `--folder` OVERRIDES it; `with_folder` stamps the model field,
  independent of `with_group`). The folder-EDITING surfaces (`actor folder set/unset/get`, the generator
  `--folder`, `actor find --folder`)
  still reject `--tree stash|prefab` (`_reject_nonlevel_target_for_folders`, exit 2 "folders apply
  only to a level target"). NOTE: the boxes now DO carry per-member folder sidecars (capture persists
  them, `StashLevelSource`/`PrefabLevelSource` load/save preserve them), so this guard is a
  deliberate SCOPE line, not a storage limitation — exposing the editing verbs on stash/prefab
  targets is a deferred follow-up (inbox). `list_actors` gained `folders`/`no_folder` params.
  Deferred (inbox): `folder rename`, exact-single-node match, a `--from-group` migration sugar.

## Labels (uedcli-side actor classification)
A **label** is a flat token (`lighting`, `flammable`, `hero`) on an actor, the multi-valued
cross-cutting axis a single folder hierarchy can't express (a torch is at `castle.tower` AND is
`lighting` AND `interactive`). Labels are the SET analog of the single-path folder: same storage
mechanism, same trunk-only scope, same never-emitted-to-the-map rule, but a **sorted set** rather than
one path. They are **orthogonal** to the folder, the T3D `Group=` prop, and the T3D `Tag=` prop —
named `label` deliberately, since `tag` would collide with `Engine.Actor.Tag`. Spec
and plan both in board item `re-evaluate-whether-reject-nonlevel-target`; `direction/organization.md`,
2026-07-22 20:49 UTC. This first cut is **trunk + `duplicate` only** — no stash/prefab labels channel
(deferred), so the label-editing verbs reject `--tree stash|prefab`.

- **Model + sidecar.** `Actor.labels: frozenset[str]` is a **typed field** (like `folder`), NOT a
  `props` entry; the empty set = unlabelled. It persists as a per-actor **sidecar file** `labels`
  beside `folder`/`order_value` in the trunk (`actors/<name>/labels`), **one label per line, sorted**;
  `emit`/`canonical_actor_t3d` **never serialize it**, so labels are out of the T3D body, the
  materialized `.dx`, and the canonical level hash (authoring metadata with zero build effect).
- **Tree I/O (`t3dtree.py`).** `write_actor_tree` writes the `labels` sidecar **atomically** (tmp +
  `os.replace`, like `actor.t3d`/`folder`) when the set is non-empty — `"\n".join(sorted(...)) + "\n"`
  — and **removes** it (`unlink(missing_ok=True)`) when empty, so a cleared set truly deletes the
  file rather than leaving a stale one. `read_actor_tree` reads it into `actor.labels` (absent/empty →
  `frozenset()`); the returned tuple shape is unchanged (labels ride on the model). **The delta-write
  trap (same shape as folders):** `TrunkLevelSource.save`'s changed-set diff is a content-diff of
  body + rank, and a label-ONLY change leaves both byte-identical — so the diff **also compares
  `actor.labels`** against the `self._loaded_labels` baseline (built in `load()`, re-derived after each
  `save()`, beside `_loaded_folders`), firing on ANY delta including a `clear` back to empty; without
  it `actor label add`/`remove`/`clear` would silently no-op.
- **Validation + matching (`labellib.py`, pure).** A **stored token** is `[A-Za-z0-9_+-]+`, no `.`,
  **no leading `-`** (`validate_label` = `folderlib.validate_segment` — the shared single-segment
  charset check extracted from folder validation — plus the leading-`-` reject, so a label can't be
  confused with a flag). `match_label(pattern, label)` is a **flat `*`-glob**: `?`/`[`/`]` are rejected
  (never leaks fnmatch char-class semantics — `*` is the only wildcard) and matching is
  case-insensitive (`fnmatch.fnmatchcase` over both sides `casefold()`ed, Linux-safe). An actor matches
  a `--label` pattern if ANY of its labels matches.
- **The `// uedcli-labels:` carrier (`actor show` ↔ `actor add`).** The interchange form is a bare
  `// uedcli-labels: a,b,c` T3D comment (comma-joined, sorted) inside the actor block, mirroring the
  folder carrier — the UnrealEd importer silently strips bare `//` lines. `actor show` emits it by
  DEFAULT (`query.actor_show_block`, whose `with_folder` param was renamed `with_sidecars` since it now
  gates BOTH carriers) and the **generators** emit it via `emit.emit_actor_t3d`→`inject_carriers` (the
  shared seam, NEVER the trunk-body `emit_actor`/`canonical_actor_t3d`), so `brush build --label …`
  authors labels at birth; `model.parse_t3d` parses it (`labellib._LABELS_CARRIER`) back into
  `actor.labels` and strips it from the stored body. `actor show --t3d-only` (`with_sidecars=False`)
  suppresses both carriers for a byte-exact editor export. `actor add` has **no `--label`** flag
  (2026-07-24 17:04) — it persists the incoming carrier as-is.
- **CLI + guards.** `actor label add|remove|clear|get <names…|->` (`add` = set-union, `remove` =
  set-difference, `clear` = empty; **no `set`** — compose `clear` + `add`); `add`/`remove` take
  repeatable `--label L`, `get` prints `Name<TAB>l1,l2` (sorted; `(none)` if unlabelled) or `--json`
  `{name: […]}`. The mutating verbs are PRODUCERS (touched Names → stdout, summary → stderr) and
  **validate-all-then-apply** (every `--label` validated and every name resolved before any write, so
  a bad token / unknown name leaves ALL actors untouched, exit 2 naming the offender). `actor find
  --label GLOB` (repeatable = OR-within, ANDs across dimensions) / `--no-label` (mutually exclusive
  with `--label`, matches only the empty set); the **generators** `brush build`/`actor build --label L`
  (repeatable). EVERY label surface that WRITES a label (`actor label add/remove/clear/get`, the
  generator `--label`) plus a label carrier arriving into a stash/prefab target rejects `--tree
  stash|prefab` (`_reject_nonlevel_target_for_labels`, exit 2 — mirrors the folder guard; a deliberate
  SCOPE line, not a storage limit). `list_actors` gained `labels`/`no_label` params; `actor_show_block`'s
  `with_folder` → `with_sidecars` (all callers updated).
- **`actor add` / `actor duplicate` ingest channels.** `actor add` is a pure carrier-consumer (no
  `--label`, 2026-07-24 17:04) so it passes `labels_override=None` — the incoming carrier wins.
  `_ingest_actor_t3d` retains the `labels_override` param (still the override channel, now used only if a
  caller supplies it) and `labels_add` (used ONLY by `actor duplicate` — UNIONs onto the carrier labels). `actor duplicate` was overhauled: it now REQUIRES exactly one of `--by DX,DY,DZ` (relative
  per-actor delta) / `--at X,Y,Z` (anchor the set's bbox-min corner, per the placement convention in
`direction/conventions.md`) — a bare `duplicate` is exit 2,
  `--by 0,0,0` the explicit overlap escape — and always mints a fresh `dup-<rand>` batch label
  (`t3dtree._rand_suffix`, re-rolled until unused anywhere in the target level, echoed to stderr) so
  the batch is re-addressable via `find --label dup-<rand>`. Copies inherit their source's labels via
  the `actor_show_block(with_sidecars=True)` carrier; `labels_add = {dup-<rand>} | frozenset(--label)`
  makes `--label` ADDITIVE on top. `duplicate` is trunk-only (rejects `--tree stash|prefab`).

## Commands (namespaced)
- **Texture catalog** (`texture_catalog.py`, `texture.py`) — fully offline:
  - **`texture sync [--package P]`** is project-scoped: it discovers EVERY package on the composed
    config search path (`config.composed_search_files(project, user_config)` — project overlay shadows
    game base; ALL extensions incl `.u`, since a `.u` can hold textures too — `direction/containers.md`, 2026-07-14
    19:21), UCC-batchexports each package's textures to PNG under the gitignored, per-user,
    cross-project cache
    `~/.uedcli/cache/textures/<package>/` (`config.texture_images_root` — per-user cache home)
    (host-side Pillow decodes PCX → PNG + derives `image_hash` over RGB pixels + dominant named colors
    from a 12-name controlled palette), and builds/refreshes a **tracked** per-package manifest in the
    PROJECT's catalog dir `<catalog-dir>/<package>.json` (`config.project_catalog_dir` — the
    `uedcli.toml` `catalog` key, default `<root>/texture-catalog/`).
    Each entry: `ref` (`Package.Name`; 3-part `Package.Group.Name` only when two stems share a
    bare name), `image`, WxH, `image_hash`, `colors`/`colors_source`, `tags`, `description`,
    `stale`, `removed`, `classified` (derived). Change detection: raw `.u`/`.utx` file sha256
    (`package_hash`) for the package; `image_hash` per texture. Classification is never
    silently lost: changed pixels → mark `stale`; gone texture → mark `removed`; new texture →
    empty entry. Catalog writes are atomic (temp + `os.replace`) under a per-package `flock` in
    the **catalog-adjacent, self-ignoring `<catalog>/.locks/`** (decision 2026-07-18 07:53 — the
    lock's scope matches the manifests it guards, so writers from different projects/checkouts
    pointing at one shared catalog still serialize; N concurrent agents). The project is resolved
    LAZILY, only to DEFAULT the catalog dir — with an explicit `--catalog-dir` every texture verb,
    reads AND `classify set`, runs outside any project. `--package P` narrows to one package;
    `sync` drops the old `texture export` verb (superseded).
  - **`texture list/search/tags`** — offline manifest reads. `search` ranks over
    name+tags+description with `--tag`/`--colors`/`--package` filters (exact palette-name
    `--color` match, case-folded; multi-term AND; ties by ref); output is `Package.Name` refs
    for piping into `brush poly set --texture`. `tags` lists the vocabulary.
  - **`texture classify status/set`** — record LLM/human metadata. `set` replaces provided
    fields and clears `stale`; `--colors` sets `colors_source=set`, after which `sync` never
    re-derives colors for that entry. `set` rejects a `removed` texture.
  - The **12-name color palette** (`black white grey red orange yellow green blue purple pink
    brown tan`) is defined as one module constant. Derivation: quantize 64×64 NEAREST-resample
    histogram → keep names ≥12% share, cap 3. Pillow pinned to a version floor for stability.
  - Image path is derived by convention (never stored in the manifest — would dangle vs the
    gitignored image tree). Consumers check existence and error "run `texture sync`".
  - See [`direction/asset-catalog.md`](direction/asset-catalog.md) 2026-06-22 entries for the full design rationale and
    rejected alternatives.
- **`docs list|show|search`** (`userdocs.py`, `dispatch._dispatch_docs`) — uedcli serves its own
  **user-facing** documentation, so a consumer reads the pages baked into the binary it has rather
  than carrying a copy that drifts (the `git help <topic>` / `rustc --explain` pattern). The
  motivating consumer is a shipped Claude skill that routes a user to a page by *querying the
  tool*, shipping **zero** doc copies. Read-only and fully offline: no project, no ambient level,
  no games config, no editor — it must answer in a bare checkout and a bare install.
  - **Docs root**, resolved in a fixed order (`userdocs.docs_root`): `$UEDCLI_DOCS_DIR` → the
    source checkout's `docs/` beside the package dir → the packaged `uedcli/_docs/`. **Source
    before packaged, deliberately** — a stale `_docs/` from an experimental local build must never
    shadow the live tree a developer is editing. The anchor is
    `importlib.resources.files("uedcli")`, not a `parents[N]` count, so moving the module inside
    the package cannot break it. The `_docs` branch is dormant: nothing generates it yet (see the
    packaging item on `board/inbox/`). Any failure is a clean exit-2 `_SelectionExit` naming what
    was wrong — never a silently empty listing, which would read as "this build has no docs".
  - **Topic key** — how a page is addressed: its path under the docs root with `.md` dropped, with
    a `README.md` folded onto the directory it documents (`leveldesign/deusex/README.md` →
    `leveldesign/deusex`) and the root `README.md` onto the reserved key `index`. `list`/`search`
    print topic keys; `show` takes one (a trailing `.md` is optional, matching is
    case-insensitive). A **bare basename is deliberately not a resolver** — `human-scale` names two
    pages, so it is a miss whose hint lists both, never a coin flip.
  - **What keeps the developer tree out is the ROOT, not the prune.** `dev/docs/` is a **sibling**
    of `docs/`, not a subdirectory, so it is not under the docs root and never was reachable — the
    served set is defined by where enumeration starts. The enumeration additionally never descends
    a **top-level** `dev/` directory inside the root (matched as `parts[0]`, so a legitimate
    `guide/dev/…` deeper down still serves) and drops any symlink whose real target resolves
    outside the root or back into that `dev/`. **That prune is defence in depth and fires on
    nothing today** — it guards a future layout that nests the two trees, or an operator pointing
    `$UEDCLI_DOCS_DIR` at the repo root. It is not a licence to weaken the root resolution.
  - **`show` resolves by looking a key up in the enumerated served set** — there is no path join
    anywhere — which is what structurally kills `../` traversal, absolute paths, directory reads
    and non-`.md` dumps rather than blacklisting them. ONE enumeration feeds all three sub-verbs,
    so they cannot disagree about what is served.
    **Every comparison in the module is case-insensitive** — the `dev/` prune, the `README` fold,
    the `.md` extension, key lookup, the duplicate-key check and the sort order — so the served set
    does not change shape on a case-insensitive filesystem (the Nuitka ship target).
  - **An unreadable directory is an error, not an empty one.** The walk is hand-written
    (`userdocs._markdown_files`) rather than `Path.rglob`, because `pathlib`'s glob swallows the
    `OSError` from `scandir`: an unreadable docs root would list as zero topics at exit 0, and an
    unreadable *subdirectory* would silently drop its pages from `list`, `search` **and** `show` —
    a partial answer with no signal, which "No silent half-answers" forbids. Root-owned trees left
    by container runs make that a live failure mode here. Every unreadable directory (and an
    unreadable file, in `userdocs._read`) is a clean exit 2 naming the path.
  - **A duplicate topic key is a hard error** naming both files (case-insensitively compared, the
    same way lookup resolves). An ambiguous served set cannot be trusted, and because the failure
    happens during *enumeration* it trips every `docs` invocation **and** `bin/test` — so it is
    caught while authoring the docs and a shipped binary can never carry one.
  - Output follows the house pipe conventions: topic keys (or a page's markdown) on stdout, the
    count on stderr, `--json` for structure. `show` writes **bytes** (`sys.stdout.buffer`) because
    the docs carry UTF-8 typography a locale-driven re-encode would corrupt. `show -` reads keys
    from stdin and is **atomic** — one unresolvable key means nothing at all on stdout and exit 2,
    never a partial dump that reads as complete; on success each page is preceded by a
    `<!-- topic: <key> -->` marker naming it, so `docs search … | docs show -` composes.
  - Rationale + rejected alternatives: [`rationale/userdocs.md`](rationale/userdocs.md).
- **`class list`/`class show`** — offline actor-class discovery over the composed `.u` path (no
  editor, no ambient level); see "Class discovery + qualify-and-validate on ingest" below.
- **Generator verbs (stdout T3D producers)** — `dispatch.py` handles these without resolving a
  selected trunk *level*, so they run with no ambient level. **They DO now resolve the project** to
  validate the emitted class (`--mover-class`/`actor build`'s class) and any `--texture` ref against
  the composed `.u` path (`_validate_ingest_actors`) — so they are **project-dependent** (no longer
  stateless context-free producers; an unknown class/texture → exit 2, no project → exit 2). This is
  the generators-AND-boundaries choice; the check is redundant with `actor add`'s boundary for the
  common `build | add` pipe. Its unique effect is failing a `build > file` outside any project:
  - **`brush build <shape>`** wraps `builders.<shape>()` via `make_brush_actor` and writes each
    actor T3D to stdout (one actor; spiral: a central column + one wedge tread per step, `N+1`).
    The eight shapes are `cube`/`cylinder`/`cone`/`sheet`/`staircase`/`spiral` (fixed parametric —
    you choose sizes) and `extrude`/`revolve` (**2D-profile sweeps** — you draw the silhouette with
    a repeatable `--point U,V`, then sweep it straight along `--depth` or around an in-plane axis
    through `--angle` UU; see "Swept profile generators" below).
    Flags `--at`/`--csg`/`--solidity`/`--folder`/`--label`/
    `--base-name` bake into the emitted T3D (there is no `--group` flag — the engine `Group`
    property is set with `--prop Group=<name>`, removed as a dedicated flag 2026-07-24). `--base-name` is a **stem**, not the final
    Name: `actor add` always appends a `_<rand>` suffix (and the spiral, one actor per brush, a per-brush index),
    so the emitted Name is a prefix (default: the shape/mover-class name). Session-free.
    **`--mover-class <Package.Name>`** makes a **Mover** instead of an `Engine.Brush`: the actor's
    `cls` is the given FQCN and NO `CsgOper` is emitted (a mover is out of world CSG — spike
    2026-06-25), base pose only (keyframes via `mover key`). `--csg`/`--solidity` are REJECTED with
    `--mover-class` (a mover carries neither — exit 2); the base name defaults to the mover-class
    bare-name (`Engine.Mover` → `Mover0`). `--at`/`--texture`/`--base-name` apply as for
    any brush.
  - **`actor build <Package.ClassName>`** constructs an `Actor` with the given class, location,
    optional `--base-name` (stem for the emitted Name; default the bare class name — give distinct
    base names when batching several point actors so `actor add` keeps them all), and optional
    `--prop KEY=VALUE` pairs, and writes the T3D to stdout. Rejects a bare class name (no `.`).
    The class is **existence-validated** against the composed `.u` path before emit (project-
    dependent, see above; unknown class → exit 2).
  - **`brush intersect -` / `brush deintersect -`** are generators whose SHAPE comes from a piped
    T3D brush SET instead of parameters, merged **natively — no editor, no container**
    (`brushcsg.py` -> `uedcli_native.intersect_brushset`). Both reduce to UnrealEd's
    `builder-brush ∩ world`, with the scaffolding the editor needs a live builder brush and a carved
    room for synthesized INTERNALLY: a `bbox+64` builder cube centred on the set, plus — for
    `intersect` only — a wrap-SUBTRACT of the SAME box that forces the empty background
    (`deintersect` uses the engine's default solid world and prepends nothing). Stdin order IS the
    CSG order and is never re-sorted (a mixed add/subtract set is order-dependent). `intersect`
    requires >=1 `CSG_Add`, `deintersect` >=1 `CSG_Subtract`; both exit 2 naming the other verb
    otherwise, and exit 2 (never skip) on a non-brush or Mover in the stream — the Mover half is
    `brushcsg.check_all_csg_brushes(..., index=)` over the schema-aware `movers.is_mover`, so these
    two "no editor, no container" generators DO need the class resolver (project + games config).
    The result is re-centred on emit so it is trivially relocatable and a `--mover-class` door
    rotates about a chosen pivot rather than the world origin (`--origin`/`--pivot`/`--at`, see
    `usage.md`). They replaced the editor-driven `stash intersect`/`deintersect`, which are DELETED;
    that editor path survives only as the golden regenerator (`tests/editor_oracle.py`,
    `-m integration`) behind the committed `tests/fixtures/intersect/` goldens. See `direction/generators.md`,
    2026-06-24 14:30 UTC (the generator pattern) and 2026-07-24 16:32 / 2026-07-25 (the merge
    itself and the corrections).
- **`level`** (the primary editor-driving verbs):
  - `level materialize [--out <path>] [--overwrite] [--tree level/NAME]` — the **pure build** (git-native slice 3,
    `apply.run_materialize`): materialize the resolved level's git-tracked T3D **trunk** into a
    `.dx`/`.unr` map file. No session, no 3-way reconcile, no THEIRS read, no anti-clobber name
    guards, no backup, no git commit — git holds the authored trunk, the map file is a regenerable
    build artifact. Trunk-only; resolves the project + the level via `_resolve_level_only`
    (`--tree level/NAME` else `$UEDCLI_LEVEL`; a stash/prefab `--tree` is rejected — no world to build).
    Echoes `materializing level 'X' (from $UEDCLI_LEVEL)` when resolved from the env. Flow: read the
    trunk (`TrunkLevelSource`) → warn on any
    duplicate `order_value` (arbitrary CSG order; `trunk.duplicate_ranks`) → **resolve every
    distinct class's DEFAULTS** (`apply._level_defaults`, needs the game's `.u`; done here, before
    any container exists, so an unqualified/unresolvable class costs ~0.1 s and `exit 2` naming the
    actor instead of surfacing after the ~100 s build — skipped entirely under `--no-verify`, which
    is the only thing that needs them) → ensure-load the **whole
    composed search path** (`config.composed_search_files` → bare names → `packages.ensure_load`;
    the container-visible substrate subset — overlay-`paths` dirs are the deferred mount slice) →
    FULL RE-IMPORT in LevelInfo-first order → **`LIGHT APPLY`** (unconditional — `MAP REBUILD` wipes
    lighting every materialize; lightmaps aren't T3D-exportable, so never affects the H3 compare) →
    temp `MAP SAVE` → **H3 post-verify** (re-export the saved `.dx` offline **in the same ephemeral
    editor**, qualify both sides, resolve both to their effective TYPED property values against the
    class schema + defaults, and compare against the intended trunk — `verify.verify_dx_matches`
    over `normalize.compare_view`)
    → atomic swap (`_install_atomic`). The editor is a **per-command ephemeral container** (minted
    per invocation, torn down in a `finally`; no session, no shared lock — `direction/containers.md`, 2026-07-06
    05:12). **Refuses to overwrite an existing `--out`** (exit 2, naming the file) unless
    `--overwrite`; H3 catches a silent `MAP SAVE` failure.
  - `level preview SHOT... --out-dir DIR [--game|--native] [--size WxH] [--fov DEG]` —
    **freely-posed still shots, two backends behind one verb; `--game` is the DEFAULT, `--native`
    is opt-in** (decisions 2026-07-16 12:13 + 2026-07-17 18:46; spec
    board item `de-containerization-follow-on-spec-items`). `dispatch._level_preview` resolves the tier as
    `use_game = not args.native` (mutually-exclusive flags; neither given ⇒ game). Trunk-only. SHOT tokens are the shared pose
    grammar (`preview_shots.parse_shot`): `at:X,Y,Z;rot:PITCH,YAW` / `at:…;look:X,Y,Z|@Actor` /
    `orbit:@Actor;radius:R;azimuth:A[;elev:B]` (+ `;name:STEM`), unreal rotation units (16384 = 90°), validated up front
    all-or-nothing; `look:`/`orbit:` aim at a brush's world-AABB centre or a point actor's
    Location. **`--native` (opt-in) is the all-offline draft tier** (`preview_native.py`):
    the Rust CSG core carves the trunk in-process (`build_geometry`), each built surf joins back
    to its SOURCE brush poly via `i_actor`/`i_brush_poly` (guarded like
    `assemble._patch_surf_refs` — an out-of-range owner renders flat grey, never an IndexError),
    the per-surf world UV frame is computed Python-side from the AUTHORED
    `Origin`/`TextureU/V`/`Pan` (`base_w = Location + R·(Origin − PrePivot)`, `axes_w = R·axes` —
    the built surf's synthesized texture vectors are never read, and Pan doesn't survive the
    build), textures decode natively (`utexture.py`; a ref that does not decode → magenta/black
    checkerboard + one stderr warning per distinct ref NAMING the decoder's case; no texture →
    flat grey), movers render
    directly as world-transformed extra polys at their base pose, and `uedcli_native.
    render_frame` rasterizes (camera BASIS passed from Python's `euler_to_matrix_uu` — Rust never
    converts angles; perspective, ~4uu near clip, z-buffer, perspective-correct nearest mip0 UV,
    per-face key-light shading factor, dark-grey background). `PF_Invisible` faces are dropped;
    translucent/masked/portal faces render opaque (draft tier). Rotated brushes pass through
    (validated against `rotation.world_vertices`, not editor goldens); non-identity
    `MainScale`/`PostScale`/`SheerRate` → named exit-2. `--fov` defaults to 75° (the game's
    `Engine.PlayerPawn DesiredFOV`). No cache: every invocation renders the current trunk.
    The U/V/Pan mapping is pinned against live editor+game references —
    `spikes/2026-07-16-native-preview-anchor/`. **`--game` (the DEFAULT) is the faithful in-game
    tier** (`preview_game.py`, spec 2026-07-13; warm-container spec 2026-07-17, built 2026-07-17): it
    delivers the map into a **WARM per-user headless-game container** (`uedcli-game`, `FROM
    dx-lum-uned` + a warm-wineprefix bake + the compiled `UedPreview` link package + a staged boot
    map; built on demand by `uedcli/game/build-image.sh` with a source-hash fast path), whose
    `Console=` subclass self-spawns a TCP link that FREEZES + noclips + HUD/weapon-cleans the world
    at possession (`bPlayersOnly` + `Ghost()`, spec D9). **Warm lifecycle (decisions 2026-07-17):**
    one container per Unix user (`uedcli-game-preview-<uid>`), serialized by a per-user
    `flock(~/.uedcli/game-preview.lock)`; reuse is gated in **ONE `docker inspect`** on the
    fingerprint LABEL (image id + realpath-normalized mount pairs + `--size` + project-overlay
    `(path,size,mtime)`) — a mismatch or a stopped container reboots fresh (a pinned other-config
    container errors instead of being clobbered). The container **self-terminates after 10 min
    idle** via an INLINE bash watchdog (tini's direct child; its `exit` stops the container) keyed
    on a `/work/.last_use` marker the **batch script refreshes each run** (no host heartbeat — the
    one-exec drive below); both boot-failure paths `exit 1` (fail-closed). The container's package
    mounts AND the game ini's `[Core.System]
    Paths` are wired from the COMPOSED CONFIG PATHS (decision 2026-07-16 15:49 UTC —
    `resource_mounts`/`paths_ini_lines` over `config.composed_search_dirs`, project-shadows-base;
    `.dx` AND `.unr` globbed, D7). **Map delivery** writes the build into `<root>/.uedcli/preview/` under
    a dot-free, lowercased, kind-prefixed, length-capped hash name (`materialized__<level>__<hash12>`
    for the trunk, `copied__<contenthash12>` for `--map`; `--rebuild` mints a short-nonce variant),
    bind-mounted read-only at `/resources/preview` (OUTSIDE the `/resources/r*` farm namespace, so
    the esync-fragile boot enumeration never sees it) and POST-boot symlinked into the local Maps
    farm — the SP-R-confirmed reload mechanism (a unique filename forces a fresh load; see
    `spikes/2026-07-17-game-preview-reload-keying/`). **The WHOLE batch runs in ONE `docker exec`
    of the in-container `preview_batch.py`** (spec in board item `level-preview-game` —
    the one-exec drive that replaced ~8-10 per-op `docker exec`/`stats`/`cp` round-trips; a
    persistent-daemon alternative was designed then rejected by review as not worth the surface):
    it symlinks the delivered map in, runs the 3-phase travel handshake (possessed link →
    `TravelToLevel` → reconnect-poll the level name; **skipped when already on the stem**), then per
    shot sends `PrepareCamera <x y z pitchUU yawUU>` (renamed from `Screenshot` — it only POSES; host
    clamps pitch to ±89.9°; the verb owns the single `BaseEyeHeight` eye→pawn subtraction and replies
    SYNCHRONOUSLY), waits a short in-batch **settle** (~0.2s — the posed frame must render before the
    grab, and the settle CAN'T live in the link verb because `bPlayersOnly` also freezes that actor's
    `Tick`/`Timer`), X-grabs the window, and streams length-framed PNGs back over stdout. Host-side is
    only the reuse `inspect` + this `exec` + a bounded reboot-retry; `preview_batch.py`'s link/travel
    seams are offline-tested (`test_preview_batch.py`, fake link socket). `--map PATH.dx|.unr` previews
    a prebuilt/retail map with NO CSG and NO trunk; **actor-relative poses (`at:@Actor`/`look:@Actor`/
    `orbit:@Actor`) resolve against the RUNNING game** for `--map` (link verbs `ListActors`/
    `GetActorLocation`; `preview_shots.py` is baked into the image so the batch resolves `@refs` +
    poses — decision 2026-07-17 16:24), and **`--list-actors CLASS [--sample N]`** is a QUERY mode
    printing a map's actors (`Engine.PathNode` blankets walkable spots) to compose `@Name` refs into
    shots — no screenshots. `--keep-alive` PINS the warm container (`/work/.pinned`) and prints its noVNC URL. A trunk with no
    PlayerStart is a model-side exit-2 BEFORE any boot (D8). uplayctl is the reference design only —
    no import/shared image (D1). Live-verified 2026-07-17: cold ~60s → **warm reuse ~2.2s** (skip-travel)
    → **10-shot batch 8.37s, all distinct** → idle self-death; plus the SP-R reload gate. *(The
    editor-screenshot
    backend — `preview_render.py`, the
    `TARGET[:MODE][=NAME]` grammar, `MODE_INI`, `query.overview_brush` — was DELETED at this
    cutover, 2026-07-16: it could only auto-frame a brush from one canonical angle, camera
    rotation being unrenderable headless — spike 2026-07-12. `unrealed/rendering.md` still
    documents the editor-render mechanics for other drivers.)*
  - `level doctor [--json] [--severity …] [--category …] [--tree KIND/NAME]` — **static, offline**
    BSP/geometry lint (`doctor.py`; no editor).
    **SCOPE IS BOUNDED BY INTENT-INDEPENDENCE, and the boundary is permanent** *(owner ruling
    2026-07-26; `docs/usage.md` "What `level doctor` WILL and WILL NOT find" states it user-facing)*:
    `doctor` reports only defects that are wrong **regardless of what the author intended** — the
    math/geometry that breaks or burdens the BSP, zoning of the same kind, and objectively-wrong
    footguns (an `Event` matching no `Tag`; a light buried in solid geometry). It does **NOT** judge
    gameplay or style, and **passage/occlusion checking is explicitly rejected, not deferred**: doctor
    can measure the free gap between two brushes but cannot distinguish a deliberately sealed wall from
    an accidentally blocked doorway, because the two are identical geometry and differ only in intent.
    Anything needing that guess belongs to a human or an independent reviewing agent looking at renders
    — see `spikes/levelbuild-friction/owner-reports.md`. Do not add a check here that infers what a
    space is *for*. Reads the box via the `LevelSource` seam — the
    ambient `$UEDCLI_LEVEL` by default, or a `--tree level|stash|prefab` box (decisions 2026-07-19 / 2026-07-20;
    it names the box via the source's uniform `display_name`, and a box's empty `_ranks` yields no
    duplicate-order finding) — and reports the *single-brush-decidable* hole
    causes: degenerate faces the engine drops at `FPoly::Finalize` (<3 verts after coincident/
    colinear cleanup, zero-area, non-convex, non-planar), non-watertight solids (open/non-manifold/
    reversed edges — the offline analogue of the editor's `bspValidateBrush` "linked X of Y";
    `check_watertight` uses **per-supporting-line directed-interval parity** so a legitimate
    **T-junction** — a long edge opposed by a collinear chain of shorter ones, as the single-brush
    staircase has — reads as closed 1/1 on every sub-interval, while a real hole collinear with a
    healthy seam is still flagged on its uncovered sub-segment; lines are grouped by a canonical
    key quantized to the `builders.WELD` grid),
    solidity misuse (semisolid+portal), gross
    CSG-order mistakes (add inside a later subtract, no-op subtract), and duplicate trunk
    `order_value`s (`check_duplicate_order`, WARN — CSG precedence among those actors falls to the
    name tiebreak, not intent; composed at the dispatch seam from `src._ranks`, since `run_doctor`
    has only a `Level`). **It REQUIRES a class resolver** since 2026-07-25:
    `run_doctor(level, index)` takes a `classindex.ClassIndex` — the watertight check covers closed
    solids: world brushes AND movers — and mover-ness is now the schema-aware `movers.is_mover`
    (see "Mover support"). With no games config the verb exits 2 naming itself and the requirement
    (`dispatch._mover_index`), never a partial report. Thresholds are the engine's
    own (the two 2026-06-24 BSP spikes); `doctor` owns them — `geometry.py`'s conservative
    write-path tolerances are unchanged. Exit non-zero on any ERROR (over ALL findings, regardless
    of `--severity`/`--category` display filter — CI-usable). It does NOT enumerate build-emergent
    holes (slivers/T-junctions/phantom collision nodes); that is the planned **offline BSP-build
    engine** (board item `bsp-issue-ground-truth-detector-d0-d1` — a faithful Python port verified differentially
    against the editor, editor = test oracle only) which will upgrade `doctor` from *predict* to
    offline *ground truth*.
  - `level list [--json]` — enumerate the project's levels (`dispatch._level_list` →
    `level_select.list_levels`): every immediate subdir of `<maps-dir>` that holds an `actors/` tree
    (the structural marker of a T3D trunk; dotted dirs like `.locks` skipped), sorted case-insensitively.
    Follows the producer convention — one name per line to **stdout** (pipe-friendly), a count + the
    active `$UEDCLI_LEVEL` to **stderr**; `--json` emits a `[{name, active}, …]` array to stdout. Needs a
    project but NO ambient level (routed before the trunk-level resolution, like `project show`). The
    marker reads the RAW env (unvalidated) so a bad `$UEDCLI_LEVEL` shows `(not listed)`, never crashing `list`.
  - `level status [--tree KIND/NAME] [--json]` — read-only summary of the ambient `$UEDCLI_LEVEL`, or of a
    `--tree level|stash|prefab` box (`dispatch._level_status`, via the `LevelSource` seam). `--json` emits `{kind, name, actors:{total,brush,point},
    duplicate_order_values, git, texture_packages}` (or `{"selected": null}` when nothing is selected);
    the text form is a `<kind>: <name>` header (`level: castle` / `stash: bay` / `prefab: door`,
    from the source's uniform `kind`/`display_name`), actor counts (total / brush / point), a WARNING
    on any duplicate `order_value` (`trunk.duplicate_ranks(src._ranks)`; a box's `_ranks` is empty →
    no warning), a best-effort one-line git hint **only for a level trunk** (`isinstance(src,
    TrunkLevelSource)` — branch + uncommitted-change count scoped to the trunk dir), and a `texture
    packages:` line of the box's directly-referenced texture packages (`stashlib.referenced_packages`
    — distinct non-Engine `Texture` prefixes; `(none referenced)` when empty). Class packages aren't
    string-derivable, so the line is texture-only. With no `--tree` and no ambient `$UEDCLI_LEVEL` it prints a
    friendly hint (exit 0), not an error.
- **`project show`** — read-only project diagnostic (`dispatch._project_show`; git-native slice 4 §1,
  the surviving remnant of the old `project` verb family). Prints the resolved project ROOT, its
  game, the three managed dirs (maps/prefabs/catalog), and the **composed package search path**
  (`config.composed_search_files`) in order,
  each entry tagged `project`/`base` (project overlay shadows game base — the old `--explain-paths`).
  Needs no ambient level (routed before the trunk-level resolution). Three exit-2 error paths, each
  naming the offending value: no project resolvable (`_ProjectError`), no per-user games config
  (`~/.uedcli/config.toml` absent — a separate hard error, decision 2026-07-06 05:12), and a game
  missing from a present config (`config.ConfigError` from `select_substrate`).
- **`event graph [--dot | --json]`** — read-only Tag↔Event **trigger-wiring** analysis over the
  ambient `$UEDCLI_LEVEL` (`dispatch._event_graph` + `eventgraph.py`; pure, model-side, no editor). In UE1/
  Deus Ex an actor's `Event` prop is the event it FIRES and its `Tag` prop is its receiver identity;
  a directed edge **A → B** exists when `A.Event == B.Tag` (non-empty, case-insensitive FName
  match). `build_graph(level, index)` collects nodes (any actor with a non-empty `Event`/`Tag`, or
  any `movers.is_mover`, which the handler resolves through `dispatch._mover_index` — so
  `event graph` needs the game packages too) and edges; `lint_graph(graph, level)` reports
  `dangling_event` (fires into the
  void), `unreachable_tag` (a receiver nothing targets — non-movers), `unreachable_mover` (a Mover
  with an unused Tag and no self-moving `InitialState`), and `cycle` (Tarjan SCC — a directed
  trigger cycle). **Output follows the producer convention:** default = one edge per line to stdout
  (`Src (Class) --Event--> Dst (Class)`), the summary + lint to stderr; `--dot` = Graphviz DOT to
  stdout; `--json` = `{nodes, edges, lint}` with lint folded in. **Exit 0 on any successful scan**
  (lint is advisory — a query verb, decision 2026-07-18 20:54 UTC). Takes `--tree KIND/NAME` to
  analyse a named `level|stash|prefab` box instead of the ambient `$UEDCLI_LEVEL` (the handler is
  source-agnostic — it only `src.load()`s). **Load-bearing
  modelling choice:** only an explicitly-set, non-empty `Tag` is a
  matchable receiver — an unset Tag's class-name default is NOT an edge target (decision 2026-07-18
  20:54 UTC). Known scope limit: the edge model reads the single `Event` prop only — multi-event
  array props (Dispatcher `OutEvents(n)`, Counter) are not modelled (inbox).
- **Content verbs are model-side** (no editor): `actor …`, `brush …` (including `brush poly …`
  and `brush vertex …`, the surface/corner sub-editors), **`mover key …`**, `actor preview`
  (wireframe).
- **The actor-name composition pipe** (spec in board item `actor-name-composition-pipe`) closes
  `actor find`'s output into the name-taking verbs at both ends. **Producer:** `actor add` prints
  the allocated `<stem>_<rand>` Names to **stdout** (one/line, allocation order) AFTER `src.save()`
  returns — so a live `add - | prop set -` pipe's downstream `load()` can never race the trunk
  write — while the `added N actor(s)` summary goes to **stderr** (never pollutes the pipe).
  **`actor duplicate` is both a consumer AND a producer:** it reads its name set (`-` supported) and
  emits each copy's fresh Name to stdout — sugar for `actor show <names> | actor add -`. `actor add`
  and `actor duplicate` share ONE ingest helper, `dispatch._ingest_actor_t3d(args, src, level, text,
  *, verb)` (parse → builder-brush filter → folder precedence → `_validate_ingest_actors` → allocate
  `<stem>_<rand>` → add with CSG-order placement → `src.save(verb=…)` → print names); `add` feeds it
  the `--file`/stdin T3D, `duplicate` feeds it the source actors' `actor_show_block`s (folder carrier
  included, so folders round-trip).
  **Consumers:** `actor delete`, `actor rotate`, `actor order`, `actor prop set|unset|get`,
  `actor show`, `actor duplicate` accept the
  single token `-` in their name position → read a newline-separated name list from stdin (exactly
  `find`'s output) via the shared `dispatch._resolve_target_names(tokens)` seam. `-` is the SOLE
  names source (mixing it with CLI names → exit 2); empty stdin → a no-op exit 0 (a filter that
  matched nothing is not an error); names resolve all-or-nothing case-insensitively and dedupe on
  the CANONICAL name (`dict.fromkeys` after `resolve_actor_names`). **`actor move` is deliberately
  excluded** (multi-actor `--to` would collapse everything onto one point — `move -` just resolves
  `-` as an unknown actor name and exit-2s), and `actor add -` keeps its OTHER meaning (a T3D
  snippet, not a name list). Multi-actor `prop set/unset` is **two-phase** (build every actor's
  `_class_ctx` + `plan_edit` first, apply all + one save second) so a bad token — or a key unknown
  on one piped actor's class — leaves ALL actors untouched even across mixed classes; multi-actor
  `prop get` prints name-prefixed KV (`<name>\t<key>=<value>`) so a multi-key dump stays parseable,
  while a single CLI name keeps the bare (or `--kv`) output.
- **`actor rotate <names…> --by PITCH,YAW,ROLL [--pivot …]`** rotates a
  group about a shared pivot — by default `rotation.best_grid_pivot`, the **`Location` of the member
  nearest the selection's bbox centre** (brushes first; alphabetically first Name breaks ties). It is
  an AUTHORED point, so alignment is inherited rather than computed, and there is no fallback branch:
  every actor has an effective Location (unauthored → the CLASS default, resolved via
  `dispatch._default_location_for` → `_class_defaults`, never assumed zero — `Engine.Camera` defaults
  it to `(-500,-300,300)`; the schema is touched only for an actor that states no Location). See
  [`direction/conventions.md`](direction/conventions.md) "PLACEMENT anchors the bbox-min corner;
  ROTATION pivots a member's own Location". Then:
  orbit each Location by the matrix (`rotation.euler_to_matrix_uu` +
  `rotate_point`) and compose orientation into the actor `Rotation` field by per-component
  FRotator **field-addition** (`rotation.compose_uu`, editor parity) — the `PolyList` stays local
  (the engine applies `Rotation` at CSG build). Because rotation + `PrePivot` live in the actor (not
  the verts), the world transform is **`Location + R·(v − PrePivot)`** (`rotation.actor_matrix` +
  `actor_prepivot` + the shared per-vertex `local_offset`; flat `world_vertices` for bounds). Every
  model-side world-geometry **measurement** consumer honours it —
  `query.level_bounds`/`list_polys`/`list_vertices`, `preview` (render + `--frame`),
  `writes.actor_bounds` (→ `stashlib` capture), `best_grid_pivot`; unrotated
  PrePivot-free actors are byte-identical (the `actor_matrix` `None` + zero-prepivot fast path). The
  **write** side inverts it: `brush clip`/`vertex move` map a world `--at`/plane to local by
  `R⁻¹·(world − Location) + PrePivot` (`rotation.world_to_local_point`), so they edit a **rotated**
  brush correctly and preserve the `Rotation` field. Points + the `--by` delta use the **true matrix
  inverse** `R⁻¹` (`world_to_local_point`/`world_to_local_delta`) — the float32 GMath `R` isn't
  perfectly orthonormal, so `Rᵀ` would drift a point ~1e-3uu at ±32768 extent; a clip **normal**
  correctly stays `Rᵀ` (`world_to_local_normal` — a normal's exact pullback is the transpose).
  (Rotated-brush `vertex move --at` matches integer corners via `clean`; a fractional corner on a
  rotated brush is a known limit.) **Scale IS applied model-side** (see "Scale" below). The UE1 FRotator convention (yaw `Rz`; pitch/roll sin-flipped; order
  `Rz·Ry·Rx`; unit 65536) is spike-verified (`spikes/2026-06-19-frotator-convention.md`). The
  matrix trig is **GMath-table-driven** (`rotation.gmath_sin`/`gmath_cos` → `euler_to_matrix_uu`):
  the editor builds world geometry from a 16384-entry sine table indexed `(field>>2)&16383`
  (truncation), so uedcli uses the same table — not float `math.sin` — to match the editor's
  rendered geometry to ~1e-5uu, the float32-table floor (float trig drifts up to ~0.074uu; spike
  `spikes/2026-06-19-group-rotate-exact-parity.md`).
- **Scale (`MainScale`/`PostScale`) is USED, STORED, and BAKED** (spec
  board item `scale-support-mainscale-postscale-use-store-bake`; spikes `2026-06-25-scale-transform-mechanics.md` +
  `2026-06-25-mainscale-postscale-applytransform.md`; decisions 2026-06-25 / 2026-07-18 14:03). The
  spike-verified world transform is **`world = Location + PostScale·R·MainScale·(v − PrePivot)`** —
  `MainScale` is LOCAL (pre-rotation), `PostScale` is WORLD (post-rotation), each an `FScale` (a
  `Scale` FVector + `SheerRate` + `SheerAxis`).
  - **STORE:** `MainScale`/`PostScale` parse OUT of `props` into typed `model.Actor.main_scale`/
    `post_scale` fields (`transform.FScale`, like `Location`); `emit_actor` re-emits SOLELY from the
    typed field (byte-matching the editor's serialization — a `Scale` axis iff ≠1.0, `SheerRate` iff
    ≠0.0, `SheerAxis` always, `Scale=(...)` omitted at unit scale; `transform.emit_fscale`), so a
    stale `props` copy can't double-emit. `builders` set the identity fields. Both are in
    `propedit.TYPED_FIELDS` (a `ScaleField`), so `actor prop get/set MainScale[.Scale.X|.SheerRate|
    .SheerAxis]` route to the field.
  - **USE:** `rotation.actor_linear` composes the full linear part `L = PostScale·R·MainScale` (None
    when rotation + both scales are identity — the unscaled fast path). `world_vertices` and every
    world-geometry consumer (`query.list_polys`/`list_vertices`, `writes.actor_bounds`, `preview`,
    `doctor`, `best_grid_pivot`) build world verts through it. The write inverse uses the TRUE matrix
    inverse `L⁻¹` (`world_to_local_point`/`_delta`) and the transpose `Lᵀ` for a plane normal
    (`world_to_local_normal` — the world→local covector pullback; reduces to `Rᵀ` under pure
    rotation), so `brush clip`/`vertex move` edit a scaled brush DIRECTLY in its previewed world
    frame. The sheer coefficient is the disassembled piecewise snap (`transform.sheer_coeff`,
    engine-fact pinned). *(The combined scale+sheer matrix ORDER is `Sheer·Scale` — an offline
    choice; single-effect cases match the live spike, combined is the integration differential's job.
    The `--native` preview + native binary build still REJECT / pass-identity scale — a separate
    deferred workstream.)*
  - **BAKE — `brush apply-transform`:** folds `L` into the PolyList (`v'=L·v`, `PrePivot'=L·PrePivot`
    — D8's explicit carve-out, `Location` unchanged, fields → identity, `Rotation` dropped), reverses
    each poly's winding when `det(L)<0` (mirror/odd shear — else an inside-out CSG-crashing brush),
    and with `--lock-textures` (default) transforms `Origin`/`TextureU`/`TextureV` by `L` (TEXTURELOCK).
    Guards: a Mover is rejected (bake rewrites PrePivot = the swing axis); a non-identity PostScale is
    warned as destructive (no v1 re-author verb). `transform.bake`.
  - **`brush scale <names…|-> (--to|--by) SX,SY,SZ [--pivot|--pivot-actor]`** sets `MainScale`. `--to`
    is IN-PLACE (Location unchanged, excludes `--pivot`; on a PostScale≠1 brush the previewed world
    scale is `PostScale·MainScale`, an explicit exception); `--by` multiplies per-axis AND orbits each
    `Location` component-wise `Loc' = P + S∘(Loc−P)` about the pivot (default `best_grid_pivot`).
    Guards: zero/sub-epsilon factor → exit 2; a Mover warns (keyframe travel doesn't scale);
    non-uniform `--by --pivot` over a rotated brush warns (MainScale is pre-rotation — inexact).
    `mirror` = `brush scale --by -1,1,1` (no sugar verb). **`actor rotate` gains `--to P,Y,R`** (absolute
    Rotation field, in place, excludes `--pivot`).
- **`actor order <names…|-> (--first|--last|--before NAME|--after NAME)`** and **`actor add --order
  (first|last|before=NAME|after=NAME)`** control **CSG precedence** — the `(order_value, name)` sort —
  by minting new LexoRanks, purely model-side (spec in board item `csg-order-control-actor-order-actor-add-order`; decisions
  2026-07-18). `order` reassigns EXISTING actors (a `--first` world-subtract now carves before
  everything else, unblocking in-place resize); `add --order` places NEW actors off the append point
  (default `last` == today's append). A multi-actor set is a **block move**: sorted by its current
  `(order_value, name)` and given **consecutive** ranks in the target gap, so relative order is kept
  and the block lands contiguously (works for non-contiguous sets). `order_ops.compute_reorder_ranks`/
  `compute_add_ranks` compute the K-consecutive ranks via `trunk.ranks_between` over `rank_between`,
  finding the predecessor/successor that bound the gap **excluding the moved set** (so a rank being
  reassigned never bounds its own gap). **The seam:** `TrunkLevelSource.save(..., ranks=<override>)`
  — without this override channel a `Level` (which carries no per-actor `order_value`) could never
  change an existing rank; the `changed`-set diff then fires on the rank delta and the reorder
  persists (folding into `canonical_level_hash`, since order is a real CSG state change). **Guards
  (each named exit-2):** trunk-only (rejected on `--tree stash|prefab`, which have no `order_value`
  sidecar); unknown moved actor; `--before/--after NAME` must exist and not be in the moved set;
  and `rank_between`'s `ValueError` on genuinely-adjacent imported ranks (e.g. `a`/`a0`) or `--first`
  against a smallest-digit min is caught → "cannot reorder …", never a traceback.

## Class-property schema, DEFAULTS & the `actor prop` verbs (`upackage.py`, `uprops/`, `propedit/`)

**`actor prop set|unset|get <actor> TOKEN…`** (spec in board item `materialize-post-verify-fails-when-the-trunk`;
`direction/packages.md`, 2026-07-18 10:02 + 10:30 UTC — every design choice Andrzej's) reads, sets, and clears
an actor's properties model-side, schema-validated, atomic per invocation (validate-before-mutate:
a bad token leaves the trunk untouched). It replaced the flag form (`--set/--unset`, removed
outright) and the retired `actor get`. The old stored-only reader warts (case-sensitive key,
silent rc-0 on `Location`/unknown keys) are gone.

**The dot-path grammar** (CLI-only — the stored T3D keeps its native `Key(N)=` spelling): `KEY.N`
is a static-array element, `KEY.Member` a struct member, recursively (`VectArray.0.X`); the T3D
`KEY(N)` spelling is rejected with a hint. `KEY=VALUE` is whole-value REPLACE (a static array
takes the tuple form `KEY=(0=V,3=W)`, clearing unmentioned elements; a Vector/Rotator prop takes
comma sugar `KEY=4,5,-17` — interpreted ONLY for those types, so `Group=a,b` stays verbatim);
`KEY.PATH=VALUE` is a targeted edit (siblings preserved; a member edit on an unset prop bases on
the class default). Overlapping tokens in one invocation → exit 2. Hard-rejects (`Name`/`Brush`/
mover-key bookkeeping) apply to ALL THREE subcommands and never touch the schema. `Location`
routes through a reusable **typed-field registry** (`propedit.TYPED_FIELDS` — one entry per typed
model field): whole-value partial structs ZERO-FILL (`Location=(X=1)` → `(1,0,0)` — ruling R2,
superseding the old strict all-axes parser), member edits base on the current value, `unset
Location.X` zeroes the axis, `unset Location` resets to origin; typed-field-only invocations
never require the v68 install.

**`get` is the EFFECTIVE view; dump-all is the STORED view.** A keyed `get` prints one line per
key, argument order: the stored value if present (enum ordinals re-rendered as names), else the
**class default decoded offline from the game's own `.u`** (below), else the type's ZERO — never
silence. A whole array renders as a one-line full-dim tuple; a whole struct renders every member,
unmentioned members filled from the class default (the live-probed import semantics — see
`unrealed/t3d.md` "Partial struct/array property values" + `spikes/2026-07-18-partial-value-
import-semantics/`). `--kv` prints round-trippable `KEY=VALUE` lines. `get <actor>` with no keys
dumps the stored props (plus `Location`) verbatim in stored order, dot-canonical keys; a stored
prop the schema doesn't know is a hard error (ruling R4). All keys validate before any output.

**`actor find --prop` matches EFFECTIVE values** (same fall-through, type-canonicalized compare:
bool ≡ 0/1, numeric `4`≡`4.0`, enum name≡ordinal, Name case-insensitive, str/object exact,
structs member-wise) and takes the same dot-paths. Mixed-level rule (ruling R3): a key not
declared on a given actor's class = that actor doesn't match; a key declared on NO considered
class → exit 2; an unbuildable class schema → exit 2 (no-fallback); plain `find` without
`--prop` stays schema-free (the stored-exact matching was REMOVED from `query.list_actors`).
**`actor build --prop`** uses the same grammar + validation (tokens compose onto the class-default
base; a `Location` token routes to the typed field, overriding `--at`).

**Layering.** `propedit/` is the pure verb logic (grammar, planner, effective values, dump-all,
find matcher, typed fields) — unit-tested directly (`test_propedit.py`) and through the verbs
(`test_actor_prop.py`). `dispatch.py` wires the handlers plus FOUR mockable seams the tests patch:
`_class_schema` (casefold name → `Prop`), `_class_defaults` ((casefold name, index) → canonical
default text), `_struct_members` (a StructProperty's ordered member `Prop`s), `_enum_names`
(cross-package enum values). All resolve LAZILY through `propedit.ClassCtx`, so hard-rejects and
typed-field-only tokens run without the install; everything else hard-requires the schema (the
no-fallback contract, decisions 2026-06-26 14:10, extended to reads).

**The schema/defaults source is the game's OWN `.u` bytes, parsed offline — never the editor,
never a stub** — through the unified low-level core **`upackage.py`** (decision 2026-07-18 §5:
one reader for the shared `.u/.dx/.utx/.uax/.umx/.unr` container — header v61/68/69, FCompactIndex,
FString, name/import/export tables, the tagged-property-list parser, object-ref helpers with
outer-chain qualification). `uprops/` builds on it (its old private copies deleted;
`uprops.Package`/`SchemaError`/`load_package` are re-exports, so callers are unchanged);
`utexture`/`dxpkg` migrate as a board follow-up. On top, `uprops` recovers per-class `Prop` schema
(name/kind/array_dim/flags/category/enum values — RE'd byte-exact, `unrealed/class-schema.md`),
walks Super chains cross-package (`resolve_class_properties`), and NEW this change:

- **`class_default_tags`** — the class's defaults block, decoded from the UClass body TAIL by
  REPLAYING the script bytecode (`_walk_expr`/`_skip_script`, the `SerializeExpr` token walker —
  `ScriptSize` counts IN-MEMORY bytes while names/objects are compacts on disk, so the walker
  tracks both cursors) then parsing the UState/UClass tail fields. Verified by exact-EOF landing
  on **1914/1914 classes** across the whole DX install (2026-07-18; integration test
  `test_uprops_defaults.py`). Layout facts recorded in `unrealed/class-schema.md`.
- **`resolve_class_defaults`** — every ancestor's block overlaid root→leaf (each block is a
  sparse diff vs its super), values rendered to canonical CLI text: enums by NAME (imported enums
  resolved cross-package), object refs as `Class'Package[.Group].Name'` via the outer chain,
  structs member-wise via **`struct_members`** (the Children linked-list walk — declaration order,
  super-struct members first) with the in-struct binary encodings (fixed scalars, compacts,
  FString, 1-byte bool — all validated by exact-consume). Pinned oracles: `Engine.Light`
  `LightPeriod=32`/`LT_Steady`/`Texture'Engine.S_Light'`; `DeusEx.Greasel`'s mixed-kind
  `InitialAlliances(0)`. Negative fact: v68 ScriptText carries NO defaultproperties text, so the
  binary route was the only one (live-verified 2026-07-18).

The schema search path is unchanged (`packages.schema_search_dirs` — the whole composed config
path; never the UED22 substrate or the stub cache). Cost unchanged: no game `.u` on the
config `paths` ⇒ hard `SchemaError`, exit 2, no fallback. Value type-validation keeps the
deliberately-partial stance (enum membership + Int/Float/Bool/plain-Byte checked, incl. at struct-
member depth; rich kinds pass on type — name + bounds still enforced). Warn-but-set (computed
props, `MainScale`/`PostScale`) and set-silently buckets are unchanged (decision 2026-06-26 10:53).

### Package schema cache (`schema_cache.py`)
Every `uedcli` command is a fresh cold process, so all `.u` schema decoding otherwise restarts from
zero each invocation — and the dominant cost is `load_package`'s name/import/export **table parse**
(38–211 ms per big package), not the property decode. `schema_cache.py` persists each package's
decoded **discovery primitives** to `~/.uedcli/cache/schema/v<N>/<key>.bin` so a warm cold run skips
`load_package` entirely (never touches the raw bytes `buf`). *(spec
board item `package-schema-cache`; `direction/packages.md`, 2026-07-18 21:30 UTC.)*

- **v1 bundle (`PackageSchema`)** — the per-package primitives `class list`/`class show` need, each a
  pure function of ONE package's bytes: class list (`iter_classes`), casefold→export-index map
  (`class_index_map`), per-class direct-super **FQCN strings** (`super_fqcn_by_index`, imported supers
  resolved), abstract flags (`class_is_abstract`), and the own-property schema with LOCAL enum
  value-names (`own_class_properties`). **NO name/import/export tables, NO defaults blocks, NO struct
  layouts** — discovery renders no default *values*, so it needs none of those (that is a deferred
  v2). Cross-package compositions (ancestry, the class tree, the resolved property union) are NOT
  cached — they are cheap dict-merges recomputed in-process from the cached primitives.
- **Two blobs per package, so `class list` never pays for what only the property union needs.** The
  bundle splits on disk into a **DISCOVERY** blob (`<key>.disc`: class list, cmap, super refs,
  abstract flags — everything `ClassIndex` reads) and a **PROPS** blob (`<key>.prop`: the own-property
  schema). `load_package_schema(path, need_props=False)` (the default — `class list`) decodes and
  writes ONLY discovery; `need_props=True` (`resolve_class_properties`) additionally decodes/loads the
  props blob (reusing an already-loaded `Package` on a shared miss). This matters because own-property
  decode of EVERY class is ~8 s across the whole DX path and is UNUSED by `class list` — without the
  split a `class list` cold-miss eagerly decoded it and ran ~4× the pre-cache path (measured 16 s vs a
  ~7 s discovery-only miss; warm ~0.35 s either way).
- **Key = a `(SCHEMA_CACHE_VERSION, realpath, size, st_mtime_ns)` STAT TUPLE**, hashed to the ~40-char
  filename — NOT a content hash: for ship-once game packages an `os.stat` (~5 µs) is a safe change
  detector, while re-hashing the bytes every run costs about as much as the parse it saves (~1.4 s for
  the whole `class list` path). Accepted narrow caveat: a content change that preserves BOTH size and
  nanosecond-mtime (a deliberate spoof / timestamp-restoring copy over a same-size file) serves a
  stale entry — bypass with `UEDCLI_SCHEMA_CACHE=off` or `uedcli cache clear`. `realpath` (symlinks
  resolved) keys the entry, so symlinks to one file share it.
- **Storage mirrors `stub_cache`**: immutable per-key files, `_atomic_write` (tmp + `os.replace`;
  parallel writers race harmlessly), a corrupt/version-mismatched entry is a MISS (re-decode), never
  an error. Serialization is **marshal** (the §9 spike: JSON 16.69 ms vs marshal 5.71 ms decode on
  DeusEx.u; marshal has no pickle RCE, and a format drift degrades to a miss). `SCHEMA_CACHE_VERSION`
  (an int constant) is folded into BOTH the hashed key AND the `v<N>/` path, hand-bumped on any change
  to the bundle shape / a feeding decoder / the `Prop` layout / the serialization — guarded by a
  committed **frozen-golden-bundle** test (`test_schema_cache.py`) that trips red on any decoder or
  format change, forcing a golden refresh OR a version bump.
- **Boundary + consumers.** `schema_cache.load_package_schema(path, *, need_props=False) →
  PackageSchema` wraps `uprops.load_package` (miss → decode + atomic write; hit → deserialize, no
  `load_package`). v1 consumers on the cache: `ClassIndex._cmap`/`_all_fqcns`/`is_abstract`/
  `children_map` (the `class list` TREE path — discovery-only), and
  `uprops.resolve_class_properties`' schema union (`need_props=True`) — including `class show`'s prop
  walk, which as of 2026-07-20 no longer pre-seeds a live `Package` and takes the cache path (the
  ~2.4× warm win), and `ClassIndex.ancestry` (super refs via `_schema`). The pre-seed capability of
  `resolve_class_properties` remains supported (pinned by `test_resolve_class_properties_schema_path_equals_seeded`)
  but has no in-tree caller. **Nothing loads a full live `Package` for class work any more** — the
  memoized `ClassIndex._package` was deleted with `class show`'s degrade fallback (2026-07-25), so
  every class fact and every property now comes off the cache. The `resolve_class_properties` cache path
  preserves the no-fallback contract: a corrupt super ref re-raises `SchemaError` (via the `""`
  sentinel + `super_ref_for`), and with the cache OFF it uses the old live per-class decode, not a
  whole-package one. Escape hatch `UEDCLI_SCHEMA_CACHE=off` (unset/other = on); the offline test suite
  runs with it OFF by default.
- **Footprint GC + the `cache` verbs.** `uedcli cache clear` deletes the whole schema cache;
  **`uedcli cache gc [--max-bytes N] [--max-entries N]`** *shrinks* it — `schema_cache.sweep()`
  reclaims the orphaned `v<older>/` dirs a version bump left unreachable, then LRU-evicts (by atime)
  current-version blobs until under the byte/count cap. The flags override the env-or-constant
  defaults (`SCHEMA_CACHE_MAX_BYTES` = 256 MiB / `UEDCLI_SCHEMA_CACHE_MAX_BYTES`,
  `SCHEMA_CACHE_MAX_ENTRIES` = off / `UEDCLI_SCHEMA_CACHE_MAX_ENTRIES`) for that run; a negative
  value exits 2. The same `sweep()` also runs automatically (best-effort, at most once per process)
  after a blob write, so the cache self-bounds without the verb. Eviction carries NO correctness
  pressure — blobs are immutable and derivable, so an evicted one is just a future re-decode — and
  `sweep()` never raises, so the GC can never be what breaks a command.

## Class discovery + qualify-and-validate on ingest (`classindex.py`, the `class` verbs)
`classindex.ClassIndex` is ONE offline structure over the composed `.u` path that powers three
things: the `class list`/`class show` discovery verbs, bare→FQCN class QUALIFICATION on ingest, and
class-existence validation. It is header-only (reuses `uprops.load_package` — name/import/export
tables, no property decode) except for `class show`'s schema and abstract detection. Built once per
invocation; a single unparseable `.u` is skipped with a stderr note (never aborts). *(spec
board item `offline-class-discovery-qualify-and-validate`; `rationale/qualify.md`.)*

- **`class list [--flat] [--package P] [--subclass-of Package.Class] [--depth N|all] [--include-non-actor] [--include-abstract]`** — by
  DEFAULT an indented inheritance **TREE** (decision 2026-07-18) rooted at `Engine.Actor`: abstract
  branch-points marked `*`, a frontier node's hidden direct subclasses shown inline as `(N)`. Depth
  **auto-grows to fit a ~60-line budget** (`_TREE_LINE_BUDGET`, min 1 level — Actor's ~40 children);
  `--depth N` sets it explicitly and **`--depth all`** = the whole tree (unlimited, no `(N)` collapse);
  `--subclass-of X` reroots the tree at X; **`--include-non-actor`** reroots at `Core.Object` (adds the
  non-Actor classes — `Object`/`Texture`/`Sound`/…); `--package P` prunes to P's classes + the branches
  reaching them. Built from `ClassIndex.children_map()` (the inverse of the Super chain, cached);
  `_class_tree` renders it. **`--flat`** switches to the pipeable one-`Package.Class`-per-line list —
  the older behavior: DEFAULT the ~40 direct-Actor-children CATEGORIES (depth 1, placeable is the
  offline PROXY — non-abstract Actor descendant, UE1 has no `CLASS_Placeable`), `--subclass-of X` the
  placeable-leaf drill, `--depth`/`--package` as before, and **`--include-abstract`** drops the placeable
  filter in the drill/`--package` list (shows abstract/non-placeable too; a no-op elsewhere, with a
  stderr note). The overloaded `--all` was split into these three flags (decision 2026-07-18 21:59), and
  is intercepted with a targeted pointer. Enumeration + abstract cached (`_ancestry`, `_abstract`,
  `_children`, per-package `_cmaps`).
- **`class show <Package.Class> [--depth N|all] [--category NAME …]`** — super chain + abstract/placeable header, then
  the class's own EDITABLE properties grouped by editor CATEGORY (UnrealEd's property-browser view). A
  prop's category is decoded from the `.u` (`Prop.category`, RE'd 2026-07-18 — see `unrealed/class-
  schema.md`): explicit `var(Group)` → a cross-class group (`Movement`/`Display`/…), `var()` → the
  declaring class name (a per-class group), non-editable plain `var` → NO category, **hidden**. **By
  DEFAULT only the class's OWN props are listed** (decision 2026-07-18); inherited props of an own
  category collapse to a `(+N inherited, from M superclasses)` count, and entirely-inherited categories
  fold into one tail line `(+TOTAL inherited, in K more categories: …)`. Own-category sections are
  capped at a **~60-line budget** (`_SHOW_LINE_BUDGET`, then a `(+N more own categories hidden: Foo, Bar,
  … — use --depth all or --category NAME)` note that **lists the hidden category names** so `--category`
  is discoverable). Passing **`--depth`** (any value) switches to the EXPANDED view — inherited props too
  (own + inherited per category; own untagged, inherited tagged `← Package.Class` with the FULLY-QUALIFIED
  source class — decision 2026-07-18). **`--depth N`** limits superclass hops (own = 0, immediate parent =
  1); **`--depth all`** = every hop (the whole chain — the old `--all`); the omitted-levels trailer notes
  `(+N more superclass level(s) omitted — --depth all …)`. **`--category NAME`** (repeatable, exact, case-insensitive,
  OR-combined — decision 2026-07-18 10:03) narrows to the named editor categories AND forces the EXPANDED
  render at **unlimited** superclass depth (a single category is narrow, so the budget is unhelpful; a
  derived class's category is often entirely inherited, where a count shows nothing) — `--depth N` still
  clips it, and the omitted-levels trailer is recomputed over the wanted categories only. An unknown
  category exits 2 listing the class's categories (the first unmatched value of several is named); a
  class with no editable categories also exits 2 rather than filter an empty set. `--depth all
  --category X` == `--category X`.
- **An unreadable ANCESTOR package is a HARD ERROR (exit 2), never a degraded answer.** The property
  walk resolves the whole super chain; if any chain package is missing from the composed schema search
  path (or unparseable), `resolve_class_properties` raises `SchemaError` and `class show` exits 2 with
  `cannot read schema for <FQCN>: …`, naming the offending package — in EVERY render mode, with stdout
  left empty. There is no own-only fallback (it was deleted 2026-07-25 along with the `--category`
  special case that had to reject it): printing the class's own props with a "inherited props
  unavailable" stderr note is a **silent half-answer** — the note scrolls away and the caller reads a
  truncated property set as a complete one. *(`dev/docs/direction/conventions.md` "No silent half-answers"; `direction/conventions.md`,
  2026-07-24 21:58 UTC.)*
- **Abstract detection is offline** via `uprops.class_is_abstract` → the shipped ScriptText `.uc`
  source (all DX classes ship it), NOT `ClassFlags` (unreachable past the variable-length script body
  — see `unrealed/class-schema.md`). `None` (source-stripped) fails OPEN (listed, `abstract=unknown`).
- **Ingest qualification (`ClassIndex.qualify_and_validate`, called by `dispatch._validate_ingest_
  actors`)** mirrors `qualify.qualify_level_classes`'s zero/2+ logic against the OFFLINE index (it is
  NOT that live function — it takes an actor list, adds a qualified-existence branch, and raises
  `_SelectionExit`, not a bare `ValueError`). A bare name → its FQCN (unknown → exit 2); an offline
  AMBIGUITY (a bare name in 2+ on-disk packages, which the live editor — seeing only the LOADED subset
  — would bind cleanly) is NOT hard-rejected: prefer a single Engine/Core candidate, else leave it
  BARE for live qualification at materialize (offline is never STRICTER than the build). A qualified
  class → existence check via the per-package `ClassIndex._cmap` name→index map (`uprops.
  class_index_map`; NOT the full ancestry union, which would false-report a real class with a missing
  *ancestor* as unknown). Texture refs are validated for
  EXISTENCE (`utexture.TextureResolver.exists` — decodability-independent, so a real non-P8/imported-
  palette texture never false-rejects); texture bare→FQCN qualification stays LIVE at materialize.
- **Call sites (all ingest/emit seams, one helper):** `actor add`, `stash capture --from-t3d
  <FILE…|->`, `stash apply`/`prefab apply` (`_apply_set`), and the generators `actor build`/`brush
  build` (which are thereby **project-dependent** now — no longer stateless context-free producers;
  their check is redundant with the `actor add` boundary but Andrzej chose generators-AND-boundaries).
  `brush poly set --texture` validates its single ref. `stash promote` is NOT re-validated (redundant
  — the prefab is gated when applied). The helper runs AFTER `is_builder_brush` filtering (which keys
  on the exact bare `"Brush"`). No project / empty package path → clean exit 2, never a silent pass.
- **H3 stays live-vs-live.** Because ingest now stores an FQCN, `verify.py` reconciles the intended
  level with `qualify.requalify_classes_to_loaded` (which re-qualifies EVEN a dotted class by bare
  name against the live loaded set) instead of `qualify_level_classes` (which skips dotted classes) —
  so an offline pick that differs from the live editor's pick can't cause a false post-verify mismatch.

## Mover support (offline keyframe authoring — `movers.py`)
A **mover** is an animated brush actor (`Engine.Mover` or a subclass like `DeusEx.ElevatorMover`):
doors/lifts/gears. Authoring is **entirely model-side** — keyframe poses are AUTHORED T3D
properties, not editor-computed (the console `BRUSH ADDMOVER`/`ACTOR KEYFRAME` verbs are a dead
end for authoring; the editor is reached only at the normal `level apply` materialize). Grounded
in `spikes/2026-06-25-mover-keyframe-basepos-semantics.md`.

- **Canonical representation:** uedcli stores a mover at **`KeyNum=0`**, with the **base pose in
  the ordinary `Location`/`Rotation` fields** and keyframe offsets in `KeyPos(i)`/`KeyRot(i)` props
  for i = 1..N-1 (relative to the base; `KeyPos(0)`/`KeyRot(0)` are `(0,0,0)` by definition).
  uedcli **never emits `BasePos`/`BaseRot`** — the editor derives them from `Location`/`Rotation`
  at materialize, so they are stripped via `normalize.COMPUTED_PROPS` (a uedcli-authored mover and
  its re-export then canonicalize equal — the H3 invariant). It likewise **never emits
  `SavedPos`/`SavedRot`**, which `AMover::PostLoad()` overwrites with a fixed sentinel
  (`(-12345,-12345,-12345)` / `(Pitch=123,Yaw=456,Roll=789)`) on **every load** of a Mover object —
  so they are engine runtime state that no authored value can survive, and they are stripped by the
  same set (spike `spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/`; decision 2026-07-25
  03:07 UTC). `SavedTrigger` is NOT stripped and must not be — `Engine.TriggerLight` declares its
  own, and `COMPUTED_PROPS` is keyed by bare name across all classes. At most **8 keys**
  (`KeyPos[8]` arrays in `Engine.u`), minimum 2.
- **`actor move`/`actor rotate` need no mover special-casing:** they edit `Location`/`Rotation`
  (the base pose at `KeyNum=0`); the editor re-derives `BasePos`/`BaseRot`. Moving/rotating the
  base rigidly shifts/rotates the whole animation (offsets are fixed) — correct by construction.
- **`mover key` math is trivial:** base = `Location`/`Rotation` (always `KeyNum=0`), so a
  `--from-world` key is `KeyPos(i) = to − Location`, world pose of key i = `Location + KeyPos(i)`; a
  `--from-base` key writes the offset straight in (no subtraction). The offset is added in
  **world axes even when `BaseRot≠0`** (`KeyPos[i]` is NOT rotated by `BaseRot`); rotation composes
  the same way (`KeyRot[i]` field-added to `BaseRot`). Confirmed live + from the disassembled editor
  transform (`spikes/2026-06-25-mover-keyframe-basepos-semantics.md`) — so no base-rotation special-casing is needed.
  (Caveat: `rotation.subtract_uu`/`compose_uu` are per-component FRotator arithmetic, geometrically
  naive for a non-cardinal base — `--from-world`/`--from-base` are not a clean re-basing off a tilted
  base `Rotation`.)
- **Keyframe verb model (spec in board item `mover-key-keyframe-model-rework`,
  `direction/generators.md`, 2026-07-20):** `NumKeys` is the *authoritative runtime waypoint count* — the engine
  cannot infer it from which `KeyPos` lines exist (a key deliberately at the base pose stores no
  line yet is a real waypoint), and UnrealEd never auto-decrements it (live-verified,
  `spikes/2026-07-20-mover-numkeys-trailing-zero/`; pinned by
  `test_it_keeps_numkeys_when_a_key_is_zeroed`). So the verbs split cleanly:
  - **`mover key count <name> [<n>]`** owns `NumKeys`: get (print) or set (2..8, non-destructive —
    lowering leaves the inactive keys' offsets dormant). Routed through `movers.set_num_keys`
    (`check_num_keys` validating, `_set_numkeys` keeping the omit-when-2 canonical export form).
  - **`NumKeys` is off `propedit.HARD_REJECT`** — `actor prop set <name> NumKeys=<n>` is
    byte-identical in effect to `mover key count`: it shares the `check_num_keys` validator (same
    bounds error) and applies the same omit-when-2 write. It does not literally call `set_num_keys`
    (`propedit.plan_edit` builds a prop list, not the live actor), so the two omit-when-2 writes are
    independent copies — a cross-route stored-props test pins them byte-identical against drift.
    `KeyPos`/`KeyRot`/`KeyNum` stay rejected (author geometry with `mover key move`/`rotate`;
    `KeyNum` is canonicalized to 0 on ingest).
  - **`mover key move`/`rotate <i>` are edit-only** (`1 ≤ i < NumKeys`) — they never grow `NumKeys`
    (raising the count is `count`'s job). `i == 0` errors (base pose); `i ≥ NumKeys` errors pointing
    at `count`. `--to` requires a `--from-base`/`--from-world` frame (no silent world default); `--by`
    is a frame-agnostic delta. Frame/`--by` checks run before the index guard. **`mover key add` was
    removed** — its implicit "next free slot" couldn't tell a base-pose key (no line) from an empty
    one; explicit `count` + index-addressed edit replaces it.
- **Ingest canonicalization:** an externally-authored mover left at `KeyNum=k≠0` (its `Location`
  is then `base + KeyPos[k]`) is folded back to `KeyNum=0` on read — `canonicalize_mover` rewrites
  `Location`/`Rotation` to the base and drops `KeyNum`, leaving every other key's offset unchanged.
  Idempotent. It runs at ONE place: **capture** — `dispatch._capture_from_t3d` calls it per
  candidate actor as the stash/prefab ingest gate, since the unified T3D-tree read path no longer
  canonicalizes on read (the retired `tree_io` did). There is no per-Level and no raw-blob variant:
  `canonicalize_movers_in_level`/`canonicalize_mover_blob` were deleted 2026-07-25 as zero-caller
  API surface (`direction/conventions.md` "No back-compat cruft"), and `qualify.export_and_qualify` — once
  described here as a second funnel — never called either. Without the fold the next `EDIT PASTE`
  materialize would re-derive `BasePos` from the offset pose and drift.
- **`is_mover(actor, index)` — the single shared, SCHEMA-AWARE predicate** (`direction/conventions.md`,
  2026-07-25 10:18 UTC). It answers "does this actor's class descend from `Engine.Mover`?" by
  walking the class hierarchy in a `classindex.ClassIndex` (the offline index over the composed
  `.u` search path), *not* by testing the class name. A bare (unqualified) class resolves through
  the index's `bare_to_fqcn` map — every candidate with that bare name is asked, and they must
  AGREE: unanimous yes → mover, unanimous no → not a mover, a split verdict → `ClassRefError` (see
  below). An empty class is not a mover. **It answers or it RAISES**
  (`classindex.ClassRefError` → clean exit 2) — never `False` for "don't know". Four cases: the
  index cannot resolve `Engine.Mover` at all; the actor's own class is not on the path; its
  ancestor chain truncates before the `Core.Object` root (`ClassIndex.ancestry` truncates SILENTLY
  at a missing/unparseable ancestor package, so a short chain is unknown, not "no"); or a bare name
  resolves to candidates that disagree. Any `False` there would report a real mover as a static
  brush — invisibly, since nothing downstream re-checks.
  - **Why it changed:** the old test was `bare.endswith("Mover")`. It REJECTED real movers whose
    class name doesn't end in `Mover` — `CaroneElevatorSet.CEDoor` and `…CaroneElevator` (live:
    `mover key` answered "is not a Mover"), plus `DeusEx.BreakableGlass` and `DeusEx.BreakableWall`
    in the base game, the first of which leaked into world CSG. Measured against the real composed
    path (2026-07-25, 2034 classes): **17** classes descend from `Engine.Mover`, only **9** of them
    match `*Mover` case-sensitively, so the old guess rejected **8** — the four above plus
    `TNM.Barricade` and, purely because `endswith` is case-sensitive while UE1 `FName`s are not,
    `TNM.fanmover`/`platformmover`/`weakmover`. It would also have ACCEPTED an unrelated class merely
    ending in `Mover`; that half is THEORETICAL on this substrate (0 of those 9 name matches is a
    non-mover), so the regression pins it with a synthetic class. The real-hierarchy half is pinned
    against the game's own `.u` by `test_movers.test_real_class_hierarchy_decides_mover_ness`.
  - **Every caller of `is_mover` passes an index**, and the predicate itself has no name-guess
    fallback inside it: `doctor.run_doctor`/`check_watertight`/`_is_closed_solid_brush`,
    `eventgraph.build_graph`, `preview_native.build_scene`/`_brush_inputs`/`_mover_world_polys`,
    `native.materialize._in_world_csg`/`_build_level_model`/`run_materialize_native`,
    `brushcsg.check_all_csg_brushes`, `movers.canonicalize_mover`, and the dispatch verbs
    (`mover key`, `brush scale`, `brush apply-transform`).
  - **ONE name-suffix mover test survives OUTSIDE `is_mover`, deliberately** (do not "fix" it in
    passing): `preview.classify_brush` still picks the magenta *mover* colour with
    `bare.endswith("Mover")`. It is the CSG-palette + hidden-line classifier on the shared
    `actor preview` / `stash preview` / `prefab preview` path, so threading a `ClassIndex` into it
    would make those three verbs require a project + the games config too — a further verb family —
    while an open spec item — board item `why-do-seven-verbs-now-require-the-games-config` — is
    asking whether that requirement should be scoped BACK DOWN. Which verbs may ask the mover
    question is one decision, so `classify_brush` is folded into that item's scope rather than
    pre-empted here. **Live consequence until it is decided:** in those wireframe previews `CaroneElevatorSet.CEDoor`,
    `DeusEx.BreakableGlass`/`BreakableWall`, `TNM.Barricade` and the lowercase `TNM.fanmover`/
    `platformmover`/`weakmover` fall through to their `CsgOper`/`PolyFlags` instead of reading as
    movers, while `mover key` and `level doctor` call the same actors movers. Usually only the COLOUR
    diverges — `is_solid` (hidden-line removal) is `classify_brush(actor) not in ("subtract",
    "nonsolid")` and both `"mover"` and `"add"` are solid — but a misclassified mover carrying
    `CsgOper=CSG_Subtract` (tested before `PolyFlags`) or `PF_NotSolid` also loses its solidity.
  - **Consequence: those verbs now REQUIRE a class resolver**, hence a project + the per-user games
    config. The verbs that NEWLY require one: `mover key`, `level doctor`, `event graph`,
    `stash capture`, `brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`
    (`level materialize` and both `level preview` tiers already did). `dispatch._mover_index` is the
    ONE seam that builds it (over `_class_index`, itself the mockable seam); BOTH resolver-less
    routes — no games config, and a config that resolves no packages (`index.empty`) — exit 2 naming
    the verb and the requirement. `doctor` treats subclass movers as closed solids (deliberate: it
    widens the watertight check to e.g. `BreakableGlass`, which the glass recipe already flags as a
    false-positive source — `board/inbox/` chore).
- **The `mover key` family** (model-side, trunk-level, `src.save`): `add` appends a key at
  an absolute world pose (stores the relative offset); `move`/`rotate <i> (--to|--by)` edit a key
  (`--to` absolute, `--by` delta — `mover key rotate --to` is a NEW absolute-rotation affordance
  `actor rotate` lacks); `remove <i>` deletes and compacts indices; `list` prints each key's world
  pose + stored offset (read-only). Index 0 is rejected (it is the base — use `actor move`/`rotate`
  or delete the actor). Saving stores the resolved relative offset so the key is base-independent.
  See `direction/generators.md` (2026-06-25) for the full rationale + rejected alternatives.

## The editor is a per-command ephemeral resource (`editor.py`)
The editor is a build/preview tool, not the source of truth — and every editor-driving verb spins
up its **own throwaway container for that one invocation**, then tears it down. There is no session
and no standing per-project editor: `level materialize` and `level preview` each mint a fresh
`uuid7` id, `ensure_editor(id)` `docker compose run`s
a container named `uned-<uuid7>` (its own WINEPREFIX volume + an **ephemeral** noVNC host port via
`-p 0:6080`, read back with `docker port` — `--service-ports` would collide with the standing
`dx-lum-uned`'s fixed `127.0.0.1:6080`), drive it, and `stop_editor(id)` in a `finally` (removes the
container + volume). Because each container is unshared, concurrent invocations never touch each
other's editor state — parallel-safe by construction, no drive lock needed; `preview` boots one
editor per distinct render mode. The container is **derived per command, never a `--container`
flag.** *(`direction/containers.md`, 2026-07-06 05:12 — per-command editor identity.)* Every editor/build-
container spin-up takes an explicit **`state_dir`** — the resolved project's `<root>/.uedcli/`
(`config.state_dir(project.root, create=True)`, threaded from the dispatching verb; `direction/projects-and-config.md`,
2026-07-17 20:58) — hosting the crafted/override ini temps (`tmp/`) and the flocks (`locks/`);
`repo_paths.state_root()` (the CLAUDE.md-marker-derived `<repo>/.uedcli`) is retired.

## Native (editor-free) map IMPORT (`uedcli/mapimport.py`, the `level import` verb)

The inverse of materialize: a compiled `.dx`/`.unr` map file → the same per-actor T3D a trunk holds,
with no editor, no container and no game in the path — just the package bytes. It makes an existing
map (a retail mission, someone else's level, an older build of your own) queryable, diffable and
editable with the ordinary model-side verbs.

**What a compiled map holds:** a `.dx`/`.unr` is an ordinary UE1
package (`upackage.py` parses the container) — a name table, an import table, an export table, and
one serialized *body* per export. One export is the `Engine.Level` object, and it owns an `Actors`
array naming every actor export **in the order that IS the level's actor order**. Each actor body is
an optional `StateFrame` (the UnrealScript execution state) followed by a `None`-terminated list of
*tagged properties* — only those whose value differs from the class default. A brush actor also
points at a private `UModel` whose `Polys` object is a `UPolys` array of `FPoly` records: the
authored polygons.

**The pipeline.** `mapimport.import_map(pkg, index, schema) -> str` returns `Begin Map … End Map` text
for `model.parse_t3d` — through TEXT deliberately, so the decode reuses the tested text→model routing
(location/scale/brush-ref handling) rather than reimplementing it. In order:

- **`actor_refs`** reads the `Engine.Level` export's `Actors` array — `[i32 Num][i32 Max]` (raw
  int32s, *not* a compact count) then `Num` signed compact object refs, `0` meaning a null/deleted
  slot (dropped; retail maps carry 29–329). Export-table order does **not** equal this order on any
  retail map tested, so the array must be decoded. Evidence:
  `spikes/2026-07-24-level-import-order/findings.md`.
- **Two integrity gates** implement "no silent half-answers": every non-null entry must be a local
  export descending from `Engine.Actor`, and **every actor-classed export must appear in the array**.
  A decode that dropped an actor would otherwise yield a trunk that looks complete.
- **`render_actor`** emits the bare class name, skips the StateFrame, reads the tags, renders each,
  then (for a brush) the inline geometry block followed by the `Brush=` ref and the trailing `Name=`
  — mirroring `emit.emit_actor`'s ordering, including *why* the model ref trails the geometry.
- **`render_prop`** renders values through `uprops.render_default_tag` under `uprops.T3D_STYLE`
  (see below), plus two rules of its own: a struct **drops each member equal to the class default's
  member, recursively** (the editor's own rule — this produces `Rotation=(Yaw=8192)`, and for a nested
  struct `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)`), and a dynamic array becomes one
  indexed line per element (`Foo(0)=…`). The recursion is why the comparison walks a member TREE
  (`uprops.struct_tag_member_tree` / `zero_struct_tree` / `strip_member_tree` / `render_member_tree`):
  a pre-joined nested value could only be kept or dropped whole.
- **`brush_of`** walks `Brush=` ref → private `UModel` → `parse_model_body(...).field_0x54` →
  `UPolys` → `FPoly`s → `model.Polygon`s, then `emit.emit_brush` renders them — reused deliberately,
  so the geometry text is guaranteed to parse back.

**`uprops.ValueStyle`** carries the two ways a decoded value is rendered to text. `CLI_STYLE` is the
default everywhere and is what every pre-existing caller gets; `T3D_STYLE` differs in exactly two
ways, both required to match the editor: **floats at a fixed six decimals** (`Location=(X=6048.000000
…)`, where the CLI form trims to `6048`), and **a byte struct MEMBER rendered as its enum value name**
(`MainScale=(SheerAxis=SHEER_ZX)`, not `5`). `Prop.array_inner` is the other schema addition — an
`ArrayProperty`'s element property, needed because an array's own `type_ref`/`type_name` point at the
element property OBJECT, so the element KIND is recorded nowhere else. It is persisted by
`schema_cache` (which forced `SCHEMA_CACHE_VERSION` 1 → 2): a cache that handed back
`array_inner=None` would break array decode *only on machines whose cache was warm*.

**The verb** (`dispatch._level_import` + `_resolve_import_dest`) is `level import MAPFILE --tree
level|stash/NAME [--overwrite]`. `_resolve_import_dest` is a **create-mode** resolver — the opposite
of `_resolve_level_source`, which requires the box to exist — and it runs the overwrite guard
**before** the map is read. Order matters twice more in the handler:

- **The editor's scratch objects are dropped BEFORE class qualification.**
  `mapimport.drop_editor_scratch` removes the builder brush (via the shared
  `normalize.is_builder_brush` predicate) and the `Camera` viewport actors; both key on the SHORT
  class name, which `ClassIndex.qualify_and_validate` rewrites to `Engine.Brush`/`Engine.Camera`.
  Same constraint `_validate_ingest_actors`' docstring already states for `actor add`.
- **A level `--overwrite` must name the previous actors as deletions.** `trunk.write_level` is a
  DELTA write that leaves unlisted actor dirs alone (so concurrent per-actor edits compose), so
  without that the old level's actors would linger and silently merge into the imported one.

Rationale, rejected alternatives and the outstanding verification gap:
[`rationale/mapimport.md`](rationale/mapimport.md). Format traps:
[`unrealed/package-format.md`](unrealed/package-format.md) (`RF_HasStack` is a per-EXPORT flag;
`FPoly.ItemName` index 0 is a real name).

## Native (editor-free) materialize (`uedcli/native/`, `uedcli-native/`)
The offline build path that turns the git-tracked T3D trunk into a game-loadable `.dx`/`.unr`
**with no editor, no wine, no container** — the design is board item `native-level-materialize`
(RE evidence: `spikes/2026-07-15-native-materialize/sections/{10,20,30}`). Two artifacts:

- **Python glue `uedcli/native/`** owns orchestration + the proven byte-exact serializers:
  `codec.py` (FCompactIndex + primitives + FString), `pkg_write.py` (package container:
  header/names/imports/exports layout + GUID/generation mint + a `parse_package` re-reader),
  `umodel.py` (UModel body parse + write-from-arrays — the Python **dev oracle**),
  `actor_write.py` (StateFrame + FPropertyTag list + struct layouts + UPolys/FPoly),
  `level_write.py` (the ULevel body: Actors/FURL/ModelRef/ReachSpecs/trailing), `pkgref.py`
  (import/name resolver — class→defining-package, textures by ref), `assemble.py` (object graph
  → name/import synthesis → body serialization → layout; **synthesizes the mandatory `Actors[0]`
  LevelInfo + `Actors[1]` Default Brush + builder-cube UModel, and asserts a PlayerStart is
  present**), and `materialize.py` (`run_materialize_native` + the **always-on offline
  self-check**: re-parse to EOF, resolve surf/model refs, assert the Actors[0]=LevelInfo /
  Actors[1]=Brush / PlayerStart invariants — §6 gate 1).
  - **World-CSG brush selection (`_in_world_csg`).** Only STATIC brushes are carved into the world
    BSP; a **Mover** (`Engine.Mover` / a subclass like `DeusExMover`, `ElevatorMover`) carries a
    brush but is a DYNAMIC actor (door/elevator/lift) whose brush UnrealEd keeps as the Mover's OWN
    private Model — it is never CSGed into the world.  `_build_level_model`'s `csg_order` therefore
    filters movers OUT of the CSG input (via the shared substrate-generic `movers.is_mover`
    predicate), while `_trunk_to_actorspecs` still EMITS every mover as a level actor (actor
    emission is independent of CSG selection).  Feeding movers into world CSG fills their doorways
    solid and shatters empty-space connectivity into spurious zones/leaf-blobs — measured on the
    retail levels: excluding movers took HK/WanChai-Market leaf-blobs 21→2 and zones 24→5 (matching
    the editor golden's own 5), and UNATCO-HQ leaf-blobs 18→7 and zones 20→9 (editor 7); the castle
    (no movers) is byte-unchanged.  **Those counts were measured 2026-07-19 with the OLD name-suffix
    predicate** — i.e. with the `DeusEx.BreakableGlass` brushes still entering CSG — and have not
    been re-run since; re-measuring is a `board/inbox/` chore.  The suffix GAP itself (a Mover
    subclass not named `*Mover` leaking into CSG) is CLOSED: `is_mover` is schema-aware since
    2026-07-25, so `_in_world_csg`/`_build_level_model`/`run_materialize_native` take the
    `ClassIndex` (`index=`/`class_index=`) and resolve the hierarchy for real.
- **Rust crate `uedcli-native/`** (a PyO3/maturin extension `uedcli_native`) owns the CPU-bound
  compute (spec §8: pure CPython misses the ≤2 min build target). `src/` is a pure-Rust core
  plus a THIN `lib.rs` PyO3 shim exposing the staged FFI contract (`build_geometry`/
  `serialize_model`/`bake_lighting`/`build_paths`) with a `BuildError` exception and `allow_threads`
  around compute. `cargo test` runs the core with no Python. The **CSG core** (N-1) is:
  - `fpoly.rs` — `FPoly`: CalcNormal/Fix/RemoveColinears/**Finalize/Reverse/Transform**/SplitWithPlane
    (classify+cut) with the exact ±0.25/±0.01 thresholds; carries the surf-link metadata that flows
    into node emission. Transform does Location/Rotation/PrePivot and **rejects non-identity Scale**
    (never silently mis-builds).
  - `csg.rs` — `bspBrushCSG`'s two-direction filter, `FilterEdPoly`/`FilterLeaf`, and all four
    per-CsgOper keep/discard/reverse leaf funcs (§4.3). Formulated as an FPoly-list filter (a
    fragment kept unless a leaf discards it → un-clipped faces stay whole). A fresh world is SOLID
    (`root_outside=false`): a Subtract carves, an Add fills. **Classification is POINT-IN-SOLID, not
    BSP propagation** (`direction/materialize.md`): the old code
    rebuilt a classify BSP from the accumulated world SURFACE list each brush step and trusted its
    propagated `outside`; for complex non-axis-aligned geometry (an octagonal tower's diagonal
    planes) that intermediate surface set is not watertight, so the rebuilt tree misclassified empty
    regions as solid and over-discarded the next brush's faces (the "missing walls" — a box wall
    added after the tower built no solid). Now the classify BSP is kept ONLY to SPLIT faces at
    boundaries (fragments stay aligned); each terminal fragment's keep/discard is decided by
    `point_in_solid` — replay CSG against the accumulated convex brushes (`WorldBrush`
    list, threaded from `build`), sampling FULL solidity just in front of (+normal) and behind
    (−normal) the fragment centroid. `void-front/solid-back → Outside` (as-authored), `solid-front/
    void-back → Inside` (reversed), `solid-both → CospatialFacingIn`, `void-both →
    CospatialFacingOut` — feeding the unchanged leaf funcs (this reproduces the buried-face
    annihilation of §6.5 robustly). The nudge uses each face's TRUE winding normal, and the oracle's
    convex hulls recompute normals from winding, because a SHEARED brush (a diagonal wall) stores a
    stale PRE-shear axis normal that is not perpendicular to its slanted face.
  - `build.rs` — pooling (`bspAddVector`/`bspAddPoint`), `bspAddNode` (surf sharing, coplanar-chain
    walk, >16-vert split), `FindBestSplit`/`SplitPolyList`/`bspBuild`, single-zone leaves.
    `build_geometry_from_brushes` accumulates the world-space `WorldBrush` oracle, runs the
    leaf-filter per brush (actor order), then builds the tree. Three build-side corrections keep the
    tree faithful: (1) before the final partition it re-derives each surviving face's plane normal
    from its winding (the authored T3D normal is the wrong pre-shear axis normal for a diagonal wall,
    which would give an axis-aligned FINAL BSP plane instead of the slant and misroute the descent);
    (2) **`bound_leaked_solid_leaves`** (the *leaf-bounding repair*, spike section 80) — our
    CSG→merge→ONE-partition build is leaner than the editor's incremental `bspBrushCSG` and so LEAKS:
    some solid terminal cells are reached with the live CSG `outside` propagation reading EMPTY, which
    makes the game's swept-box collision (`if Outside: return` before the hull read) skip them and the
    pawn sink/fall through. The pass grafts a synthetic solid-bound node (parent plane FLIPPED, marker
    `NF_SOLID_BOUND` 0x40, sliver leaf suppressed by `zones`) at each leaked-solid cell so its
    propagation reads SOLID and `bsp_build_bounds` emits its hull — box-drops then match the editor
    exactly (castle pawn rests z=47, not the sunk z=35). NOT a real editor pass (there is none — the
    editor's tree is watertight by incremental construction, `re-raw-zones/bspbuild-splitpolylist-decode.md`);
    a synthetic collision repair. (3) after `bsp_build_bounds` it re-checks each terminal leaf's
    solidity against `point_in_solid` and clears a spurious empty-leaf reference where the propagation
    mis-marked a solid cell empty — solid corrections only, hulls untouched.
  - `model_write.rs` — the runtime UModel-body serializer, pinned byte-identical to the Python
    oracle (§6 gate 5); serializes `Bounds`(c0)/`LeafHulls`(cc) too.
  - `passes.rs` — the cleanup + bound passes: `bsp_merge_coplanars`, `bsp_refresh`, and
    **`bsp_build_bounds`** — the **collision-hull builder** (ported from the editor `bspBuildBounds`)
    that emits `Model.leaf_hulls` + per-node `i_collision_bound` so the **pawn stands on the floor**.
    Without hulls a native map is non-solid to any box sweep and the pawn falls through — the game's
    `FBoxLineCheckInfo::BoxLineCheck` produces a collision hit ONLY by clipping the swept box against
    `LeafHulls[iCollisionBound]` (`direction/materialize.md`; `re-raw-zones/linecheck-oracle.md`).
    `Bounds`/`i_render_bound` stay empty/`-1` (render bound, separate).
  - `zones.rs` — the native `TestVisibility` port (section 70): real leaves (Pass A), a
    leaf-adjacency PORTAL graph (infinite node-plane quad clipped to the cell, filtered down both
    subtrees), a union-find zone FLOOD (a `PF_Portal` surf separates zones), per-node
    `iZone`/`ZoneMask`, and `Connectivity`.  ZoneActor refs (ZoneInfo/SkyZoneInfo) are wired at
    assembly (`_patch_zone_refs`, mirrors `_patch_light_refs`) by PointRegion-resolving each
    ZoneInfo's Location into a zone.  `Visibility = ~0`.  Zone MEMBERSHIP is approximate vs the
    editor (the flood is centroid/poly-filter based, not the exact `sub_aa370` passes), but the
    pawn's zone is valid and disconnected regions (the SkyBox) separate correctly.  `light/paths.rs`
    remain N-4/N-5 stubs.
  - **KNOWN GAP — CSG geometry parity (pre-existing, in `csg.rs`/`build.rs`, NOT zones):** for the
    full 95-brush castle, ~8 brushes (battlement merlons, some walls/steps, an arrow-slit) build a
    different solid/void than UnrealEd (~11% grid-solidity divergence), so a native map does not yet
    render IDENTICALLY to an editor-built one — the player sees through missing walls. The CSG surf
    *set* differential (cases a–e) passes but SOLIDITY parity on complex abutting/edge geometry is
    the open work (same family as the b/f xfail residuals). Tracked for the full-parity effort.

**Native CSG build performance (scaling).** The build is severely superlinear in brush count
(baseline: 60 brushes 0.6s, 150 15s, 300 153s, full 762-brush UNATCO tens of minutes). **Profiling
(harness `spikes/2026-07-15-native-materialize/harness/csg_perf.py time`) located the dominant cost
NOT in `point_in_solid` but in `build::build_bsp` — the classify BSP that `csg::bsp_brush_csg`
rebuilds over the WHOLE accumulated world-poly list on EVERY brush step** (14.7s of a 15s N=150
build; `point_in_solid` was 0.1s). `FindBestSplit` is O(M²) per node, so each per-brush rebuild is
O(M²) and, summed over N brushes with M growing ~linearly, the build is ~O(N³). Two
**provably behavior-preserving** (byte-identical) optimizations ship, each verified with
`csg_perf.py hash` (the serialized-Model sha is UNCHANGED vs the pre-change build for castle +
UNATCO-150/300, stable across runs) — they cut the O(M²) *constant*, not the exponent:
  - **AABB fast-path in `FindBestSplit`/`SplitPolyList`** (`build.rs`, `aabb_side`): a poly whose
    precomputed box provably sits entirely front/back/coplanar to a candidate plane is classified
    from the box alone — the exact category `split_with_plane` would return — skipping the
    per-vertex cut for the common far-apart pair. `proj_min ≤ min_dist ≤ max_dist ≤ proj_max` holds
    exactly (box ⊇ poly), and an `AABB_GUARD` (0.25 uu) covers the FP gap between the box-projection
    and `split_with_plane`'s per-vertex dot (~0.01–0.015 at world scale ±32768, unit normals), so
    the fast path returns a category ONLY when it is provably the one `split_with_plane` would; any
    ambiguous pair falls through to the exact `split_with_plane`. Relies on the unit-normal invariant
    (`finalize` normalizes) — the SAME normal feeds both paths.
  - **Parallel `FindBestSplit`** (rayon): the O(M²) candidate scan is embarrassingly parallel;
    reduced by lexicographic `(score, index)` min so the winner is the SAME lowest-index candidate
    the sequential `if score < best` scan picks, independent of thread order (deterministic — the
    sha is stable across runs). Small lists (<128) stay sequential to avoid pool overhead.

  Net (measured; box shared with a concurrent game session, so absolute times vary — a same-window
  A/B is the reliable figure): N=150 15.5s→7.1s under heavy contention (~2.2×), ~3–3.7× when cores
  are free; N=300 153s→~30–50s; full 762 UNATCO tens-of-min→single-digit minutes. CPU tops out
  ~215% because the sequential `SplitPolyList` recursion caps utilisation and the per-brush O(M²)
  rebuild is unchanged (only its constant).

  **Rejected (NOT byte-preserving — kept out; each would be a bigger win but changes output):**
  - *AABB cull in `point_in_solid`* (skip a brush whose padded AABB excludes the query point):
    only ~2% (point_in_solid is not the hotspot) AND not exact — `point_in_convex`'s `EPS_CONVEX`
    tolerance is along each FACE NORMAL, but an axis-aligned AABB pad is along the AXES; for an
    acute/sheared wedge (which this code explicitly supports) a point up to `EPS_CONVEX/sinθ` beyond
    the box is still inside the eps-hull, so the axis-pad cull would wrongly skip it and flip a
    sample's solidity.
  - *Lean classify trees* (skip the transient tree's per-node vertex pool, an O(points) `bspAddPoint`
    dedup scan per vertex): ~15% but not *provably* byte-identical — skipping the vertex pool changes
    the shared `model.points` array, and `alloc_surf` dedups each surf `p_base` against that array;
    a later surf base could resolve to a slightly different pooled point (≤0.002 uu), shifting a
    classify-tree split plane and, near a ±0.25 threshold, changing the surviving fragment set. It
    was byte-identical on the whole acceptance corpus (castle + UNATCO-150/300) but the guarantee is
    empirical, not proven, so it is held out.
  - *Restricting the per-brush classify tree to brush-local faces* (drop world faces whose plane
    clears the brush AABB): would collapse the rebuild to O(local²) (~100×) but changed node/vert
    counts — the classify filter's coplanar double-routing (a coplanar face is filtered down BOTH
    subtrees, splitting it against *neighbouring* planes) and its whole-face-vs-fragment emission
    (`discarded==0`) depend on the FULL tree structure, not just the actually-cutting planes.

  Reaching the sub-minute target therefore needs a genuine algorithmic change (incremental /
  localised CSG that reproduces the EXACT fragments, or a provable form of the local-tree/lean
  ideas), tracked in `board/inbox/` — out of scope for a strictly behavior-preserving pass.

**Status (M0 + toolchain + N-1 CSG core):** the CSG core is ported and wired into
`build_geometry` (flat-buffer brush API). It is validated by an **editor-golden differential**
(§6 gate 3): the harness `native/csg_golden.py` captured a discriminating corpus on a live
ephemeral editor and froze it as `tests/fixtures/csg_golden/*.json`; `tests/test_csg_native_
differential.py` runs the SAME corpus through the Rust build offline and compares the surf set +
counts. **Tier-S surf-set parity is reached on cases a (single subtract), c (add-in-subtract),
d (abutting-subtracts — the known prior-port 11-vs-10 ANNIHILATION bug, proven fixed), e (semisolid
detail).** Two residuals remain (both N-2, tracked xfail + `board/inbox/`): **b (off-grid wedge)**
needs `bspMergeCoplanars` coplanar-face union (`build.rs merge_coplanars` is a documented no-op;
`FindBestSplit` uses a split-minimizing variant that substitutes for the missing merge/opt passes),
and **f (portal)** needs `TestVisibility` portalization/zones (native is single-zone; leaf-count
parity for multi-region carves is the same slice). §6 gate 5 (dual serializer) still passes.
**Collision hulls (`bsp_build_bounds`) now build, so a native-materialized map is PLAYABLE**: the
pawn stands (`phys=1`) and `uplayctl shot` renders the world first-person — live-verified on
`NativeCastle` 2026-07-16 (the full castle trunk, 95 brushes). Validate offline with the box-sweep
oracle `spikes/2026-07-15-native-materialize/harness/line_check.py` (a downward pawn sweep must HIT
at `floor+extent`). `bake_lighting`/`build_paths` are N-4/N-5. `apply.run_materialize` still drives the editor; flipping
it to the native path as its **sole** path awaits full CSG parity (b/f) + N-3 typed-prop
serialization + editor-mock test migration (flagged in `board/inbox/`). Build the extension:
`cd uedcli-native && maturin develop`; `cargo test` runs the core goldens.

## Adding a verb (model-side, no editor)
1. `cli.py`: add the parser under `actor`/`brush` (brush sub-groups: `poly`/`vertex`)/`mover`/
   `level`/`stash`/`prefab` (or a new content group) + args.
2. `dispatch.py`: content verbs resolve the selected trunk level via `_resolve_level_source(args)`
   → `TrunkLevelSource` (a bad/absent project or selection → stderr + exit 2). Query verbs
   `src.load()` (never the editor) and print; mutating verbs `src.load()`, transform the in-memory
   `Level` (validate geometry where relevant), then `src.save(verb=…, args=…, level=level,
   touched=…)` (`trunk.write_level` — preserves each surviving actor's `order_value`, mints an
   appended one for a new actor) — **no `driver`, no editor**.
3. Put read logic in `query.py`; mutation is the model transform inline (or a pure helper). The
   editor (`writes.py`/`Driver`) is reached only by `level materialize` and `level preview` — never
   by a content read/edit verb, and no longer by the CSG merge generators (they are native).
4. Add an offline unit test that seeds a trunk (`trunk.write_level`) and asserts the resulting
   trunk dir; mock the editor seams only on materialize-side tests. Fixtures in `tests/fixtures/`.

**Vertex editing** is **DONE** (`vertex.py`): `brush vertex list <name>` welds the per-poly
vertices into corners (a cube corner is 3 coincident copies) and prints each corner's world
coord + the polys sharing it; `brush vertex move <name> --at X,Y,Z … (--to|--by)` moves one
or more corners selected **by coordinate** (no vertex names — a corner *is* its coord),
rewriting **every** copy so the solid stays watertight, then `validate_brush` →
`src.save(...)` (writes the trunk from the in-memory model).
**Move-only by design** — add/delete would open/over-close the solid and is the easy way to
crash CSG. `--to` takes a single `--at`; `--by` takes one or many.

**Surface edits** (`surface.py`) follow the same model-side pattern: mutate poly fields (flags,
texture, `Pan`, `Origin`, `TextureU/V`) → `validate_brush` → `src.save(...)`. Address a surface by
`(brush, poly index)` (see `query.list_polys` + `preview`); the CLI takes flag **names**, not bit
values. The module splits into two families (see
[`rationale/surface.md`](rationale/surface.md)):

- **`brush poly set`** (`apply_surface_edit`) assigns stored per-face ATTRIBUTES — `--texture`,
  `--add-flag`, `--remove-flag`; at least one is required.
- **`brush poly pan|rotate|scale`** (`apply_pan`/`apply_rotate`/`apply_scale`) transform the texture
  FRAME. `pan (--to|--by) U,V` writes the integer `Pan` and nothing else (exactly one form
  required); `rotate --by UU` turns `TextureU`/`TextureV` in the face plane by unreal rotation units
  (16384 = 90°, `--by` only — there is no `--to`); `scale --by FU,FV` multiplies the texture's
  APPARENT size, which divides the stored magnitudes. `rotate`/`scale` write `Origin` and leave
  `Pan`; `pan` writes `Pan` and leaves `Origin` — that pairing is what lets a uniform pan survive a
  `brush poly align --ring` continuity offset, which lives in `Origin`. `scale --to` (absolute world
  units per tile) is **not built**: it needs the texture catalog.

All four resolve their target set through **`surface.resolve_targets`**, which expands `all`,
canonicalizes the brush name and DEDUPES to a sorted `(brush, poly_index)` pair list. Dedup is
load-bearing for every relative form (`pan --by`, `rotate --by`, `scale --by`), which would
otherwise apply twice to a face named twice. The four take `BRUSH:SELECTOR` (or `-`) only —
deliberately narrower than `brush poly align`, which also accepts a bare brush name.

**The per-face verbs print `BRUSH:idx` SELECTORS on stdout**, not touched brush names
(`dispatch._print_poly_selectors`), because a bare brush name means *all* of that brush's faces and
would silently widen the set for a downstream per-face verb. The model functions still **return
brush names** — that is `src.save(touched=…)`'s currency, where widening to a whole actor is
harmless — so the CLI calls `resolve_targets` itself for the printed pairs, over the same one
resolution path the mutator used. `brush poly align` still prints brush names; converting it is part
of the unbuilt align rework.

`rotate`'s frame math, all in the brush's LOCAL space (the vertex centroid commutes with the actor
transform, so a world round trip would buy only float dust): the unit normal comes from the
polygon's own winding via `texframe.newell` — **never `poly.normal`**, which the
engine ignores and recomputes — and is then **flipped on a SUBTRACTIVE brush**, so the turn follows
the VISIBLE surface normal and the same `--by` reads the same from where the author stands whether
the face is the outside of an added pillar or the inside of a subtracted room (owner ruling
2026-07-27; `surface._visible_normal`). A `CsgOper` that is neither `CSG_Add` nor `CSG_Subtract` has
no inside or outside for that to mean, so it exits 2 naming the value rather than guessing a sign; an
absent one reads as `CSG_Add`, as it does in every other reader. A whole number of quarter turns takes an exact `n̂ ×` path so it
leaves no dust in the trunk; anything else is Rodrigues. Both verbs re-anchor so the face centroid
keeps its `(U,V)`: `rotate` by `Origin' = C − R(C − Origin)`, `scale` by a 2×2 **Gram solve** (the
same shortcut does not transfer — scaling covectors scales position by the inverse transpose, so
the direct-basis version is silently wrong on a skewed frame under a non-uniform factor). `rotate`
rejects a face whose stored axes point out of the face plane — `max(3e-3, 1e-2·|axis|)`, absolute
OR relative, in a PRE-PASS naming every offender before anything is written; `scale` needs no such
guard because it preserves direction. Derivations, measurements and the rejected alternatives are
in [`rationale/surface.md`](rationale/surface.md).

**Surface texture alignment** (`polyalign.py`, build item 11 — `direction/conventions.md`, 2026-07-18 21:40 UTC)
makes one texture flow **continuously** across a set of faces instead of restarting at each brush
edge. It is uedcli's OWN alignment, **not** a port of the editor's: UnrealEd's own verb is
`POLY TEXALIGN` (there is no `TEXTURE ALIGN`), and its rules were measured on 2026-07-26 and agree
with `_tex_basis` on none of seven face directions, besides anchoring on a world axis where uedcli
anchors on the seed face's centroid — see [`unrealed/texalign.md`](unrealed/texalign.md)
"How uedcli differs". Two verbs:
- **`brush poly find <brush> [--item][--facing][--texture][--json]`** — a stateless PRODUCER
  printing matching faces as `BRUSH:idx` selectors (one/line, summary→stderr), so
  `brush poly find Tower --item Side | brush poly align --ring -` skips a cylinder's caps.
- **`brush poly align (--wall|--floor|--ring) [--fresh-frame][--fit-perimeter] (targets…|-)`** —
  reads its face set from `BRUSH:SELECTOR`/bare-name positionals or stdin `-` (bare names or the
  producer's `BRUSH:idx` lines; empty stdin → clean no-op). The **UV convention** it implements is
  `U = (Vertex − Origin)·TextureU + PanU` (texel scale in `|TextureU|`; verified against
  `render.rs`/`texframe.world_uv_frame`, pinned by `unrealed/t3d.md` + a `test_polyalign`
  engine-fact). Continuity is defined in **world space**: the seed/first face's world frame
  (`texframe.world_uv_frame`) is written into each face by **inverse-transforming it through
  that face's own brush rotation** (`rotation.actor_matrix` + `rotation.inverse`) — NOT by copying
  identical stored fields, which would only align faces of one brush. The continuity offset lives in
  the float `Origin`, so `Pan` stays the seed's integer. `--wall`/`--floor` demand a strictly
  coplanar set (with a vertical/horizontal orientation guard distinguishing the two flags); `--ring`
  advances U by each facet's chord `2r·sin(π/N)` around the side ring (V along the axis), leaving the
  closing seam by default (`--fit-perimeter` snaps the scale for an exact meet). Frame source is
  **adopt-seed** by default (continue the seed's dialled-in `TextureU/V`+`Pan`); `--fresh-frame`
  synthesizes a canonical 1-texel/unit frame from the face normal.

**Shape replace** (`brush replace <name> -`) is the same model-side pattern for a whole-shape swap:
read a generator T3D snippet from stdin (`-` is the sole shape source — the `build → add -`
convention; empty stdin → clean exit 0), parse it with `parse_t3d_actors` + drop the transient
builder brush, require **exactly one** brush actor (0 or >1 → clean exit 2), then set
`target.brush.polys = incoming.brush.polys` — keeping the target `Brush` object (its
`model_name` stays `Model_<name>`, matching the actor's `Brush=` ref) and **every** actor field
(Name, Location/PrePivot, CsgOper, Group, PolyFlags, Rotation). The same-Name `src.save` preserves
`order_value` (CSG rank) automatically. Supersedes the dropped `brush resize` (resize =
`brush scale` + `apply-transform`). *(decision 2026-07-18 20:09 UTC; board Geometry #9.)*

## Package stubbing (`stub.py`, `stub_closure.py`, `stub_cache.py`, `uscript_rewrite.py`)

The UT-lineage UED22 editor cannot load Deus Ex **code** packages directly — **not because of
the package version** (UED22's own UCC reads Deus Ex's version-68 packages fine, and the UED22
substrate itself even ships several version-68 packages — see
[`unrealed/package-format.md`](unrealed/package-format.md)), but because Deus Ex code inherits
from / calls into a DeusEx-flavored `Engine`/`Core` whose class graph and natives differ from
UT's, and because the Deus Ex mesh format differs (8-byte `FMeshVert` vs UT's 4-byte packed).
**Package stubbing** converts a level's Deus Ex `.u` code dependencies (`.u` files from the
Deus Ex install's `System/` tree) on demand into UED22-loadable "stub" packages — stripping
every function/state body so the v469 UCC can re-link the class against UT's DLLs — preserving
mesh and texture assets. (The stub output happens to be version 69 because that is what UCC
`make` emits; the version is a by-product, not the purpose.) Triggered lazily at the package-resolution stage (`stub_missing_packages`)
before any editor spin-up — printing a progress notice — so a first `level materialize`
auto-stubs dependencies without any explicit user step.

### The pipeline (one stub per source package)

1. **Decompile class source + textures** — UED22's own `UCC.exe batchexport <pkg>.u class uc`
   + `batchexport <pkg>.u texture pcx` (not the v68 Deus Ex SDK `UCC.exe`, which predates the
   `batchexport` commandlet; not the GUI-only `UnrealEd.exe` "Export All"). Requires the full
   transitive dependency closure to be loadable: code deps as v69 (substrate or already-stubbed
   cache), content deps (`.utx`) on `[Core.System] Paths`.
2. **Extract meshes** — `umodel` (`VertMesh .3d` + authoritative `MESHMAP SCALE` values).
   UED22 UCC has no mesh exporter (`No 3d exporter found for LodMesh`), so `umodel` is the only
   source. Delivered into the build container via a bind mount (lives outside the `uned/` Docker
   build context).
3. **Rewrite source** (`uscript_rewrite.py`) — **strip every function/state/replication body**,
   keeping only: class declaration, `#exec`s, enums, structs, variables, `defaultproperties`.
   Body erasure — not the `#exec` rewrite alone — is what lets the v69 UCC link the class
   against UT's DLLs (decompiled bodies call Deus Ex natives UT can't resolve). Also: rewrite
   `#exec` import directory paths + rename group-prefixed PCX filenames to match.
4. **Compile** — `UCC.exe make` under a **throwaway temp package name** (not the real `<P>`) to
   avoid colliding with any `<P>` resident in `Paths` or the already-committed substrate.
5. **Rename** the compiled `.u` to `<P>.u` (the real package name). Class names inside are the
   real names; only the package wrapper was temporary.

### Modules
- `stub.py` — `assemble_stub_source`, `build_stub`, `ensure_stub`, `ephemeral_build_container`
  (an offline `docker exec` in an ephemeral build container — NOT via `Driver`/editor-lock).
- `stub_closure.py` — resolves the direct-deps closure (one hop; not recursive into deps-of-deps
  unless the substrate demands it; a dep whose `defaultproperties`/mesh ref crosses a package
  boundary is flagged, not auto-chased).
- `stub_cache.py` — cache at the per-user, cross-project `~/.uedcli/cache/stubs/`
  (`config.stub_cache_root` — per-user cache home; gitignored — copyright-derived);
  keyed by v68 source sha256 + dep stub shas + substrate id + toolchain id (a rebuilt dep,
  re-stripped substrate, or toolchain bump invalidates dependents). `substrate stub` CLI exposes
  explicit on-demand stubbing.
- `uscript_rewrite.py` — body stripping + `#exec` rewrite.

### v68 inputs
The stubber's input source is the v68 `.u` on the **whole composed config search path**
(`config.composed_search_dirs(project, user_config)` — ONE uniform dir set, no code-vs-content split;
`direction/containers.md`, 2026-07-14 19:21), threaded as a single `search_dirs` through
`stub_missing_packages`/`ensure_stub`/`compute_cache_key` and `stub_closure.resolve`. A package's v68
`.u` resolves first-`.u`-wins across the composed dirs (`stub_closure._find_code`, project overlay
before game base = config shadowing). The build container mounts the whole composed set via the ONE
`container_assets.resource_mounts` scheme (`/resources/<n>`, the same the editor uses);
`batchexport`/`umodel` read the `.u` by its remapped `/resources/<n>` path (never via Paths). A v68
`.u` on `[Core.System] Paths` is harmless because `/stubs` (v69) is FIRST, so `make` (and the editor)
always bind the v69 stub over any same-named v68 `.u`. (The install pointers for schema/closure
integration tests live in `tests/conftest.py` — `install_system_root`/`install_content_dirs`,
`UEDCLI_TEST_INSTALL`-overridable — not in any production module.)

### Scope
Decompile failures for stripped engine symbols (e.g. `Engine.PlayerPawn.PostRenderFlash`) fail
loudly — a broken stub is never emitted. First-party `LUM_Core.u` (compiled from repo source)
and cinematics' stripped engine symbols are out of scope. See
[`direction/containers.md`](direction/containers.md) 2026-06-21 and 2026-06-22 for the full design rationale.

## Builders (`builders.py`)

**Positive-dimension guard — one table, one message, at the dispatch front door.** Before any
geometry is generated, `dispatch._check_positive_build_dims` rejects a non-positive builder LENGTH
(width, breadth, height, radius, depth, rise, inner-radius, step-width) with a clean exit 2 naming
the flag and the value: `brush build staircase: --depth must be greater than 0, got -32.0`.
Previously such a value exited 0 and emitted a self-overlapping, inside-out brush that only failed
later as an incomprehensible BSP error. Which flags each shape must guard is DECLARED, not coded
per-verb, in `dispatch._POSITIVE_BUILD_DIMS` — a `{shape: {flag: argparse-dest}}` table. **That
table is the plug-in point for a new `brush build <shape>`: add one row and nothing else.** The
regression `test_every_builder_shape_declares_its_positive_dimensions` walks the real parser and
requires every FLOAT flag of every shape to be either in the table or in that test's explicit
non-dimension allow-list — which is now EMPTY, since every builder angle became a bool or an
integer count of unreal rotation units — so a new shape cannot ship a dimension outside the guard. It checks every float flag, not just the `required=True` ones — a dimension that merely has a
default builds inside-out geometry just as happily. Counts (`--steps` >= 1, `--sides` >= 3,
`--segments` >= 1) and angles stay out of the table: their constraint is tighter than "> 0" and
belongs next to the geometry reason for it — in `builders.py` for the parametric shapes, and at the
dispatch boundary for the two checked in **unreal rotation units before conversion**
(`--angle-per-step` in `0 < uu < 32768`, `--angle` in `0 < uu <= 65536`), where the message can name
the flag and the value the user actually typed. `revolve` still declares a table row, an empty one:
its radii ARE the profile's `u` coordinates, guarded by the stricter "strictly off the axis" rule.

UnrealEd's native BrushBuilders are GUI-dialog-only (not console-drivable), so they're
replicated in Python: each builder returns a `Brush` (PolyList) — or a `list[Brush]` for the
spiral (a central column + one convex wedge tread per step) — which the `brush build <shape>` **generator** wraps via `make_brush_actor` (sets
`CsgOper`, solidity `PolyFlags`, `Group`, the `Brush=` ref) and writes to stdout as a T3D
actor block — no level resolved. Name allocation happens at `actor add`, the
only consumer that has both the trunk and the T3D at once (see "Generator verbs" in Commands
below). **Ingest of user-concatenated T3D parses via `model.parse_t3d_actors` — an ordered,
duplicate-Name-PRESERVING list — NOT `parse_t3d` (whose Name-keyed dict silently drops all-but-
last on a Name collision, correct only for an already-unique stored level).** This is load-bearing:
concatenating several generator outputs that share a base name (e.g. 14 `brush build --base-name
Merlon` merlons) into one `actor add`/`stash capture --from-t3d` would otherwise lose all but one
before uniquification ever ran. `actor add` then mints a distinct `<stem>_<rand>` per incoming
actor; `stash capture` filters by the requested names first, then uniquifies the chosen set
(first keeps its bare Name, later collisions get suffixed). `translate_brush(brush, dx, dy, dz)` shifts all vertices by a world-space delta (used by the
intersect/deintersect scaffolding to place the builder cube on the set's bbox centre; the editor
ORACLE additionally pre-subtracts 32 uu on the pasted wrap cube to cancel the `EDIT PASTE` drift —
the native path has no paste and so no offset, see `direction/materialize.md`). Geometry helpers mirror `clip.py`
(`_face` orders a ring CCW-from-out from a rough outward direction; winding, not the emitted
Normal, is what the importer uses).
Each face carries an **`Item` (`ItemName`)** label — UED's per-face semantic tag (Base/back/
Step/Rise/Side, OUTSIDE) used for surface select-by-item; `model.Polygon.item` round-trips
through `emit`/parse. The linear `staircase` emits **ONE non-convex `Brush`** — the UED
`LinearStairBuilder` stepped-wedge outer hull: a `Base` quad, a full-height `back` wall, and per
step a `Step` tread (+Z) + `Rise` riser (−X), with the two sides **tiled into per-step convex
`Side` strips** (one rectangle per step column) rather than a single non-convex silhouette poly
(a non-convex FPoly is a real CSG defect `check_convex` rejects — so the FACES stay convex while
the BRUSH is non-convex). Face count `2 + 4·steps`; it sits entirely at/above the floor with a
front-bottom **corner pivot**. Its per-step Side/tread/base boundaries are watertight
**T-junctions**, which `level doctor`'s T-junction-aware `check_watertight` (below) accepts —
that rework is why the staircase could return to one brush (`direction/generators.md`, 2026-07-21 12:06 UTC,
reversing the 2026-07-18 20:09 box-per-step). The builder now MATCHES UED's `LinearStairBuilder`
taxonomy, pinned as a builder-vs-UED equivalence test (`test_builder_matches_ued_linear_stair_taxonomy`
over the `Brush5` fixture). The **spiral** is a `list[Brush]` of `steps+1` convex brushes — a central
**column** (`cylinder`, radius `inner_radius`, spanning the full height with its base at z=0) plus one
**wedge (pie-slice) tread** per step: a convex 6-face prism (top + bottom trapezoid, inner + outer
chord, two radial sides) built via `_face`, then rotated `k·degrees_per_step` about Z with `_rotate_z`
(about the world origin / column axis). Consecutive treads climb one `rise` (top `k` at `(k+1)·rise`),
so the tops ascend strictly monotonically — a single helix, replacing the old rectangular-slab shape
whose 360°+ wrap read as a mirrored-V (`direction/generators.md`, 2026-07-22). Rotation is orientation-preserving and
keeps each face planar (trapezoids stay at constant z; the verticals stay 2-point extrusions), so every
wedge passes `validate_brush` and `_face`'s Newell flip still lands the winding outward after rotation.
`--at` anchors the base of the column axis. Convex primitives (cube/cylinder/cone) are origin-centered;
the spiral lives in one local frame with its column base at z=0.
**Native-CSG caveat (falsifies `csg.rs:61`):** this non-convex staircase brush — and equally an
`extrude`/`revolve` of a concave profile — is built correctly by UnrealEd (the default `level
materialize`) and the real engine (the default `level preview --game`), but the **coarse** native
core assumes convex brushes: `uedcli-native/src/csg.rs` `point_in_convex` tests "behind every face"
(the convex hull, not the true solid), so a stepped brush's concave notches classify as solid.
That core is what `level preview --native` uses (and what `_build_level_model`'s `core=` kwarg selects internally — there is no `--core` CLI flag). Native
*materialize* by DEFAULT is NOT affected — it runs `core="bspcsg"`, the incremental `bspBrushCSG`
port, which never calls `point_in_convex` (though `bspcsg.rs` flags a non-convex FIRST Add as an
unhandled case of its convex world-seed shortcut, so a concave brush should not lead a level's
adds). This joins the already-documented ~11% native solidity
divergence on walls/steps (KNOWN GAP below); the `csg.rs:61` comment "DX brush builders emit convex
brushes, so this is exact" is now **falsified for builder output**, with a `board/inbox/` follow-up to
decompose non-convex builder brushes into convex pieces (or guard+warn) on the native path.
The convex CSG shapes (cube/cylinder/cone) were validated live
(paste→rebuild→select) on parallel ephemeral editors — see `parallel-editors.md`; the single-brush
staircase is verified offline (doctor-clean under the T-junction-aware `check_watertight` + the
`actor preview` wireframe render), NOT live paste→rebuild→select (deferred — `direction/generators.md`,
2026-07-21 12:22 UTC).

**Swept profile generators — `brush build extrude` / `brush build revolve`.** These two are the
only builders whose SILHOUETTE the author supplies, rather than choosing sizes for a fixed shape.
Both take the same closed 2D **profile** — a repeatable `--point U,V`, argument order = ring order,
implicitly closed, either winding accepted — the same `--axis x|y|z`, and the same `--at`, and
differ only in the sweep (`--depth` uu vs `--angle` UU / `--segments`). Before them, any cross-section that
was not a box, an n-gon or a stair (an arch voussoir, an L-ledge, a moulded cornice, a curved
corridor) was unbuildable short of hand-authored T3D. Design decisions + rejected alternatives:
`direction/generators.md`, 2026-07-25 00:14 UTC (D1–D9), 01:05 UTC (D10), 01:40 UTC, 02:30 UTC (D11–D12).

- **The 2D layer is `profile.py`** (no brush, no world coordinates, no T3D), applied by dispatch in
  ONE fixed order before any geometry exists: `parse_point` per token → arity ≥3 → `clean_profile`
  (weld near-duplicates at `WELD`, drop collinear vertices, re-check the arity) → `check_simple` →
  `normalize_winding`. `ProfileError` subclasses `geometry.GeometryError`, which `dispatch()`
  already turns into a clean exit 2 — it has no bare `ValueError` arm, so a plain `ValueError`
  subclass would traceback at the user. For the same reason `parse_point` is called from dispatch
  and NOT as an argparse `type=`: argparse replaces a `ValueError`'s message with its own.
- **`check_simple` rejects more than a crossing.** Any vertex repeated ANYWHERE in the ring (a weld
  only catches neighbours, so `A B C A D E` survives it while being a figure-eight) and any two
  NON-ADJACENT edges that meet at all — crossing, touching at an endpoint, or overlapping
  collinearly. A non-simple ring has no consistent inside: the decomposition below would emit
  overlapping or inverted pieces silently, and the brush would be a self-intersecting solid.
- **The `(u,v,w)` sweep frame** is `builders._SWEEP_FRAMES`, the single place the mapping is
  written: `z`→(X,Y,+Z), `x`→(Y,Z,+X), `y`→(Z,X,+Y), cycled right-handed so `u × v = +axis` and one
  winding rule (CCW in `(u,v)`) serves all three orientations.
- **`--at` is where profile `(0,0)` lands** — local vertices are the authored coordinates verbatim,
  no re-centering, the sweep running `0..depth` (or `0..angle`) from there. This is the THIRD `--at`
  exception beside the staircase's front-bottom corner and the spiral's column base, and it changes
  what `--rotate` pivots about: an actor rotates about its LOCAL ORIGIN, so a profile drawn away
  from `(0,0)` swings through an arc instead of turning in place.
- **Concave and >16-vertex profiles are supported as ONE brush with TILED CAPS**
  (`profile.convex_pieces`): ear-clip, then merge back across shared diagonals for as long as each
  fused piece stays convex and ≤16 vertices (Hertel–Mehlhorn). A convex ≤16-vertex ring returns
  EXACTLY one piece, so the simple case still emits two cap faces. The tiling adds only diagonals —
  never a new boundary vertex — so no T-junctions appear and `check_watertight` stays clean; face
  count is `n + 2·pieces`. Same shape of thing as the `staircase`: a non-convex BRUSH of convex
  FACES.
- **The revolve axis is the profile's own `v` axis (`u = 0`), and there is NO `--pivot`**: radius is
  written in the profile coordinates, so `--at` is the bend centre. Every profile point must be
  strictly positive-`u`; the sweep then grows toward `+axis` like an extrude. `--angle 65536` closes
  the turn (both caps omitted, the last ring welded onto the first) and needs ≥3 segments; the
  `--segments` default is `max(1, floor(angle/4096 + 0.5))`, one facet per 22.5°.
- **Per-face outward hints ROTATE with their faces, except the near cap.** `_face` FLIPS any ring
  whose Newell normal disagrees with its hint, so a stale hint emits a backwards-wound face — an
  inverted solid, which UnrealEd cannot recover from (it derives the face from the winding and
  ignores the emitted `Normal`). Near cap: `−ŵ`, identical to extrude's, because the `θ=0` cap lies
  in the `(û,v̂)` plane with the solid growing toward `+ŵ`. Far cap: `+ŵ` rotated by the whole
  sweep. Side quad of edge `k` in segment `m`: the in-plane edge normal `(dv, −du)` rotated by that
  segment's MID-angle. Regression: `test_profile_generators.py` asserts zero `doctor` findings at
  90°, 180° and a full turn — written first and confirmed RED against unrotated hints.
- **Sweep magnitudes never touch `rotation.uu_field`/`uu_to_deg`**, which wrap mod 65536 because
  they parse an FRotator *field*. A magnitude is not modular: `uu_to_deg(65536) == 0.0` would
  silently collapse a closed full turn into a zero sweep. `--angle` is range-checked on the raw
  integer and converted as `uu * 360/65536`.
- **These two builders call `geometry.validate_brush` themselves**, unlike every other generator
  (`brush build` validates only class and texture existence; geometry validation happens downstream
  at `actor add`). Justified by their vertices coming from arbitrary user input — two points 0.4 uu
  apart collapse only after `emit.clean`'s grid snap — and by generator output that can bypass
  `actor add` entirely (`> file.t3d`, `| brush intersect`).
- **Two stderr ADVISORIES** (`dispatch._advise_swept_brush`, run after `--rotate` so
  rotation-induced off-grid geometry counts): an off-grid brush that is also SOLID and not a mover,
  and a brush over 64 faces. Both are gated on the swept shapes, because a `cylinder`'s ring
  vertices are inherently fractional (with a green test asserting its silence) and a 16-step
  staircase already exceeds 64 faces.
- **Goldens, and what they do NOT prove.** `fixtures/builder_extrude.t3d` /
  `builder_revolve.t3d` freeze face order, the `Cap`/`Side<k>` item names and every coordinate. They
  are SELF-blessed, unlike the six parametric shapes' editor-captured parity cases below, so they
  pin **drift, not correctness**; a real parity case needs the gated integration run and is a
  follow-up. Note also that `Side<k>` numbering is invariant under an EXACT reversal of the ring but
  not under a cyclic rotation of it, which renumbers every side.

**World-geometry parity suite** (`tests/builder_parity_cases.py` + `test_builder_parity.py`
[offline, default suite] + `test_builder_parity_capture.py` [`integration`-gated]): for each
builder case the live editor reconstructs the brush's world vertices via the DEINTERSECTION
readout (paste `CSG_Subtract` −32uu → REBUILD → enclosing `CSG_Add` → BRUSH FROM
DEINTERSECTION → BRUSH EXPORT), and that set is frozen as a golden fixture
(`fixtures/builder_parity.json`). The offline test asserts each builder still emits the golden
world-corner set + face count (CI regression guard, no editor); the gated capture test re-derives
it live and is the re-bless path (`python -m uedcli.tests.builder_parity_cases`, which refuses to
bless a case where the editor disagrees with the builder). What this proves is world-corner/
coordinate faithfulness per shape, **not** our builder algorithm vs UED's (the GUI-only
`BrushBuilders` can't be console-driven, so there is no algorithm oracle), and **not** winding
(the vertex set is winding-invariant — a flipped face is only caught live via a CSG reject). Two
families are **dropped from the LIVE capture suite** and blessed **OFFLINE** from the builder
(`OFFLINE_ONLY` in `builder_parity_cases.py`): the `stair_*` single non-convex brush (a combined
non-convex cavity makes the editor invent interior vertices at the notches) and the `spiral_*`
column + rotated wedge treads (the wedge coords are NOT axis-aligned integers, so the DEINTERSECTION
capture invents vertices on them the same way — `direction/generators.md`, 2026-07-22). For both, `regenerate`
refuses to bless on builder/editor disagreement, so the offline value golden is the builder's own
world-vertex set — a legitimate (winding-blind) change-detector. `sheet` is excluded (zero-volume
`NotSolid`, never carves CSG). See
`spikes/2026-06-19-builder-world-geometry-parity.md`.

## Preview internals

**`level preview --native`** (the opt-in offline draft backend; `--game` is the default —
see the `level preview` verb above) is split across four pieces:
`preview_shots.py` (the pure SHOT grammar + `pose_from_lookat`/`pose_from_orbit` trig +
`shot_filename` dedup — shared with the `--game` tier), `preview_native.py` (the
orchestration described under the `level preview` verb above), `utexture.py` (the native
UTexture/UPalette decoder + `TextureResolver` over `config.composed_search_files` — promoted
from the 2026-06-27 decontainerize spike, corpus-validated byte-identical to UCC's export;
`resolve(ref)` returns a TYPED result, either a `DecodedTexture` or a `TextureError` naming
one of twelve cases and the offending value, never `None`. Four are REF-layer (`unqualified-ref`,
`unknown-package`, `package-unreadable`, `unknown-texture`) and eight DECODE-layer
(`corrupt-body`, `missing-palette`, `no-mip-data`, `unverified-format`, `unrecognised-layout`,
`size-mismatch`, `ambiguous-alpha`, `ambiguous-layout`). The `DecodedTexture` carries mip 0 as
`width`/`height`/`rgb`/`mask`, the WHOLE pyramid of the selected array as the lazy `mips`
property (`(w, h, rgb, mask)` per level — decoded on first access, so mip-0-only callers do not
pay for it), which array it came from (`array`), the effective `format_code`, and the engine's
`b_masked`/`b_alpha_texture` flags. Those two follow the owner's read rule — **the export's tag
if present, else the resolved class default** via `uprops.resolve_class_defaults`, and `None`
when the search path carries no code package to resolve one from, never `False`),
and `uedcli-native/src/render.rs` (`render_frame` — the pure-Rust rasterizer, `cargo test`-able
with no Python). The camera FRotator convention is single-sourced: Python builds the basis via
the GMath `euler_to_matrix_uu` and Rust only projects. Offline test oracles: the pixel-probe
projection test, the rotated-brush/mover transform cross-checks vs `rotation.world_vertices`,
and the byte-exact golden (`tests/fixtures/native_preview_golden.png`, Linux/x86_64, blessed
against the live anchor — `spikes/2026-07-16-native-preview-anchor/`; re-bless with
`UEDCLI_BLESS_GOLDEN=1` only after re-verifying the anchor).

**`level preview --game`** (the faithful tier) is a THIN host (`preview_game.py`: D5 delivered-map
naming `materialized_dx`/`copied_map`; `acquire_warm_container` = one `docker inspect` reuse gate +
flock + fingerprint LABEL; `run_batch` = one `docker exec` feeding a JSON request to the container
script and parsing the length-framed PNG stream; `ensure_image` with a host-side source-hash marker
fast-path; a bounded reboot-retry) driving `uedcli/game/`: `preview_batch.py` (the in-container
one-exec batch — deliver symlink → 3-phase travel/skip → per-shot `PrepareCamera`+settle+X-grab →
framed PNGs), `Dockerfile`, `build-image.sh`, `game-entrypoint.sh` (farms composed content into local
dirs, patches the ini with relative `../Maps/*.dx`+`*.unr` Paths, runs the inline bash idle
watchdog), and `uscript/` — the `UedPreview` link/console/base-driver package
+ the `UedPreviewDX` DeusEx substrate driver, compiled in a mounted builder against the game's own
`DeusEx.u`). The v469 UCC toolchain is user-supplied/gitignored at `uedcli/game/inputs/edit/` (see
its README). Container/host seams are mocked offline (`test_preview_game.py`) and the batch script's
link/travel seams too (`test_preview_batch.py`, fake link socket + fake X-grab); the live paths are
the SP-R reload-keying spike + the 2026-07-17 one-exec acceptance (warm ~2.2s, 10-shot 8.37s).

**`actor`/`stash`/`prefab preview`** (`preview.py`) is stdlib-only (no PIL/numpy). Projects polys to 2D (ortho top/front/side or
true-30° iso), back-face culls per view (`_is_front` vs the view's depth direction) to
shade obscured faces the lighter of a **CSG-op colour pair** (`classify_brush` → `_CSG_PALETTE`,
keyed on `CsgOper`/solidity-`PolyFlags`/mover: add-solid blue, subtract gold, semisolid pink,
nonsolid green, mover magenta), rasterizes a light-grey-background RGB buffer (PPM/P6 — an INTERNAL,
in-memory format only; the disk write is always PNG, below), and annotates per an **`AnnotationSpec`**
(poly indices painted on-face; actor names as de-collided leader boxes).

**`--faces {wire,flat,textured}`** picks whether faces are also FILLED. It is an explicit `faces=`
parameter on `render_brush_pgm`/`render_brushes_pgm`/`render_quad_pgm` and on
`_render_breakdown_grid`'s `_pane` — it cannot be inferred from the seam, since
`PreviewData.faces is None` would mean both `wire` and a filled mode.

- **`wire`** is the historical render, unchanged and byte-identical (pinned by the golden pair
  `tests/fixtures/preview_wire_golden_{iso,quad}.png`, captured BEFORE the rasterizer existed so it
  pins the behaviour rather than the rewrite; re-bless with `UEDCLI_BLESS_GOLDEN=1`).
- **`flat`** fills each surviving face solid — from the brush's `(front, back)` CSG/tint pair, picked by
  `_is_front`, **unshaded** (multiplying the hue would break the "this blue means additive" cue the
  legend is read against) — through an `array("f")` depth buffer (`_alloc_buffers`; a `list[float]` is
  ~0.5 GB at `--size 4096` against ~67 MB, and `--size` is uncapped). Fills draw at step 2 of the pane,
  ahead of the point layer, so no sprite or `--show` overlay is painted over.
- **`textured`** fills each surviving face by sampling its OWN decoded texture through its authored UV
  frame instead of a flat hue (`_fill_face_textured`), reusing `flat`'s cull, depth buffer and
  occlusion test unchanged. UV is affine in screen space, solved once per face off the same plane
  probes as depth (`_face_uv_affine`/`_plane_screen_probes`); the mip level is per face from that
  face's own screen-space UV gradients (`_mip_level`), never a view-global gain; the fetch is
  nearest-neighbour with wrap; and a masked face's index-0 texels write neither colour nor depth
  (`(poly.flags | actor PolyFlags) & PF_Masked` OR the decoder's `bMasked`). Colour is `texel·shade`
  truncated as `render.rs`'s key light (`_face_shade` = `0.55 + 0.45·|N·L|/|N|`), so it agrees with
  `--native` up to f32-vs-f64. **`textured` emits NO wireframe** (a highlighted face takes only an
  outline); a poly with no `Texture` fills `DEFAULT_GREY·shade`. Its resolution and refusals live in
  dispatch (`cli/rendering.py` `preview_textures`): a scaled or sheared brush, `--brush-colors` given
  with `textured`, a non-finite UV frame, and any unreadable/bare/undecodable ref each exit 2 naming
  the offender (a bare ref says to qualify it `Package.Name`); no resolver names which of three causes
  applies; a scene referencing NO texture needs — and resolves — none. **Accepted cost, as `flat`:
  `textured` needs the project's game content; `wire` needs neither.**
- **A filled mode assigns THREE roles from that ONE two-member pair** (owner ruling; the first
  assignment gave two of them the same value as the fill and both were invisible — the renders that
  measured it are in `board/inbox/faces-flat-keeps-a-wireframe-that-is-provably`). Per face, `own` = the
  member its facing fills with, `partner` = the other; both carry the same hue, so the CSG cue survives.
  **Fill** = `own`; **ordinary edge** = `partner` (an edge in `own` is by definition the colour of the
  fill under it); **`--highlight`** inverts the face — fill `partner`, outline `own`. `wire` fills
  nothing, so none of it applies there and its highlight keeps the plain `vivid` hue.
- **The cull, in `_scene_geometry`.** Under a filled mode a face is dropped ENTIRELY — fill, depth,
  edge, `--highlight` outline, on-face decal and `occluders` entry — when it is `PF_Invisible` (poly
  flags OR'd with the ACTOR's own `PolyFlags`, as the engine reads them) or when it is a **subtract**
  brush's camera-facing poly. Nothing else is back-face culled (a `nonsolid` sheet is one face and must
  read from both sides). Excluding culled faces from `occluders` deliberately RAISES the opacity of
  decals they used to dim — the sole observable of that rule, and pinned as such.
- **Mover-ness is `movers.is_mover`, not a name guess, and it crosses the seam as data.**
  `classify_brush` grew an `is_mover=` parameter: `None` keeps the `endswith("Mover")` name guess for
  `wire` (which loads no class index), a bool is the authoritative answer `dispatch._preview_movers` reads
  off the class hierarchy, and a filled render MUST pass it — its docstring has the case that makes the
  guess unsafe. One key drives the fill colour, `is_solid` and the cull, so a render never mixes two
  mover answers. **Accepted cost: `flat` needs a project + the game content; `wire` needs neither.**
- **EVERY VISIBLE face draws its edges — visible, NOT front-facing.** The rule reached this shape through
  two owner rulings in sequence, and reading only the first will get it wrong. (a) Spec §4.6's
  *front-facing* condition was dropped: a `nonsolid` sheet wound away from the camera has no front face to
  borrow an outline from, so that condition left it filled and unoutlined. (b) The resulting
  *unconditional* rule was narrowed to visible faces, because it let a brush sealed inside a solid show its
  entire wireframe through it (measured 421 px → **0**). A solid brush is opaque. The two agree: what (a)
  protects is a face with no cover, which is frontmost where it sits and so still draws (pinned, **657 px**
  on two abutting away-facing sheets). The test is `_face_is_occluded`, per FACE, on the finished depth buffer —
  **never a facing test**, which is what (a) deleted. (b) also erased the ≤1 px silhouette fattening (a)
  had cost on faceted geometry: a 16-segment cylinder loses the 5 px it gained, since an edge that
  overhung a silhouette was by definition on a hidden face.
- **The rasterizer is EVEN-ODD SCANLINE** (`_fill_face`), sampling the PIXEL CENTRE: 0.1–0.6 % of real
  faces are concave (`spikes/concave-faces/`) and a triangle fan fills outside those. Depth is affine
  in screen space under an orthographic camera, solved once per face off the face's OWN plane —
  anchored at `verts[0]` with the **Newell** normal (`_face_depth_affine`), which is observable on the
  non-planar faces `--from-t3d` can carry. A singular solve = an edge-on face, skipped. The depth test
  is strictly `<`, so a **coplanar tie goes to scene order** (no epsilon bias: a flush add/subtract
  pair is common pre-CSG and a bias would only relocate the arbitrariness).
- **A MIRRORED brush is CORRECTED, not refused** (owner ruling: "mirrored brushes SHOULD WORK
  CORRECTLY"). A negative-determinant linear part is a reflection, so every transformed face's Newell
  normal comes out as the NEGATIVE of its true outward normal and `_is_front` answers the opposite of the
  truth. `_is_front_corrected` flips it back — `mirrored = M is not None and det3(M) < 0`, guarding
  `actor_linear`'s **`None`** identity sentinel — and since the cull, the three colour roles, the edge rule
  and `occluders` are all expressed in terms of that one boolean, correcting it fixes all four at once. An
  EVEN number of negative axes is a 180° rotation (determinant +1) and is deliberately untouched; a sheer
  leaves the determinant at the scale product. **`wire` is deliberately NOT corrected** — it culls
  nothing, so the inversion costs it only the front/back shade, and the ruling was about the filled modes
  (`board/inbox/wire-renders-a-mirrored-brush-with-its-front`). *(Unrelated to
  `preview_native._reject_scaled`, which still rejects ALL scale in the `--native` tier — the two tiers do
  NOT agree on scaled brushes.)*
- **Refusals, all naming the offender**: unresolvable mover-ness (grouped by cause), and no project (the
  re-raise names `--faces` and why a preview wants one — the bare house "not in a uedcli project" names
  neither, and `--from-t3d` makes being outside one ordinary). **NOT
  refused:** a set with no BRUSH actors, whose mover answer is the empty set, so it needs no class index
  ("needs" is literal, as decision 2.6 ruled for textures) — a point-only selection renders and an empty
  one stays a clean no-op. An out-of-memory buffer (`MemoryError` **or** `OverflowError`, which is what a
  huge `--size` actually raises) can only surface mid-render: `preview.PreviewAbort` carries it out and
  `dispatch` maps it to exit 2, so a `--faces` render is NOT fully validated before it starts.

**`texframe.py` — the shared home for the face math, plus ONE deliberate second copy.** `newell` (a
face's outward normal from its own vertex winding) is read by `preview.py`, `query.py`, `surface.py`
and `polyalign.py`; `world_uv_frame` (where the authored texture sits on a face — the engine
convention, with its evidence, is `unrealed/t3d.md` "The UV convention"; `tex_basis_default` supplies
a missing/zero axis) by `preview_native.py` and `polyalign.py`; `poly_flags_int` (an actor's own
`PolyFlags` prop as an int) by `preview_native.py`. It is a **leaf** — stdlib, `rotation` and
`builders` only, pinned by two import tests — so `preview.py` keeps working with no Rust extension and
no game install, which taking `newell` from `preview_native.py` would have cost it.
**`builders._newell` stays a byte-identical second copy on purpose:** `texframe` imports `builders`
for `_tex_basis`, so re-pointing it at `texframe.newell` makes the two modules import each other —
survivable only because that import is function-local, and an `ImportError` on `import
uedcli.builders`, breaking every `brush build` verb, the moment anyone hoists it to module scope.

**Annotation vs label.** An **annotation** is the selection concept — which extra marks
a render draws, chosen by `--annotate`. A **label** is the drawing concept — one concrete text box
laid out on the canvas (`_LabelItem`/`_place_labels`).
Neither is the actor **`label` dimension** (`labellib.py`, the per-actor cross-cutting `--label`
classification) — a third, unrelated sense, and the reason the selection type is no longer named
`LabelSpec`.

**Which annotations** is an `AnnotationSpec` (`parse_annotation_spec`): per kind, the set of element
categories that get one — poly faces by `(is_front, is_highlighted)`, actor names by `(is_brush,
is_highlighted)`. The `--annotate` grammar is a comma-set of `KIND[:FILTER…]` selectors, unioned: a
bare kind = ALL of it, filters narrow (intersect within a selector), commas union (see `usage.md`).
Parsed in dispatch so a bad value is a clean named error. `render_*` ask `spec.draws_poly`/
`spec.draws_name` per element.

**Hybrid tint + legend** is the label scheme on the CSG-coloured path (`color_by_csg=True`, the real
`actor`/`stash`/`prefab preview`). The wireframe keeps its CSG hue (blue=add, gold=subtract, …), but
two brushes with the SAME CSG op then share one wire colour, so each actor's LABELS instead carry a
distinct categorical **per-actor TINT** (`assign_tints` → `_TINT_PALETTE`, cycled by scene order over
brushes AND point actors alike, kept clear of add-blue/subtract-gold and of red). A brush's on-face
poly-index decal (the painted digits + their 6/9 baseline underline) and a point actor's marker draw
in the actor's tint. Actor NAMES move OFF the geometry into a **top-left
LEGEND** (`_draw_legend` over `_LegendRow`): one row per LABELLED brush/drawn-point mapping tint → NAME
(brush = filled square swatch, point = filled diamond, matching its on-geometry marker). The legend is
sized to the widest row and capped to the rows that fit the frame with a `+N MORE` tail
(`_fit_legend_rows`); its footprint is seeded into `occupied` + the `DensityGrid`, and it is drawn LAST.

**The legend never overlaps the geometry.** `render_brushes_pgm` computes the legend rows BEFORE
framing and `_legend_reserve` turns the panel's height into a top-band `inset_top`; `_framing`
scales the geometry down and pushes it below that band (`inset_top=0` is byte-identical to the
un-reserved framing, so the legacy/no-legend paths are untouched). Two independent flags drive it:
`reserve_legend` insets the band, `draw_legend` paints the panel — a pane can reserve WITHOUT drawing.
That split is what lets the legend render **once** across multiple panes while keeping their framing
identical: `render_quad_pgm`'s TOP pane sets both True and the other three set both False (each uses
its full area); `dispatch._render_breakdown_grid` sets BOTH True only on the overview pane and BOTH
False on the per-brush panes — each pane self-frames a different region (the overview whole-scene, each
brush its own AABB), so there is no cross-pane registration and the zoomed per-brush panes get the full
frame height. The **legacy black/grey path** (`color_by_csg` off) keeps black accents, on-geometry
names, and no legend.

**`--brush-colors {csg,legend}`** (`brush_colors` arg → `_scene_geometry`) selects the WIREFRAME's
colour source on the hybrid path: `csg` (default) uses the CSG-op pair as above; `legend` uses the
actor's own tint as the front colour (`_fade`d for back, and as the highlight `vivid`) — dropping the
CSG cue but colouring each brush distinctly to match its legend swatch.

**`--focus <brush>`** (`_resolve_focus` in dispatch → the `focus` arg; a point-actor name is a clean
named error) spotlights one brush: every OTHER brush's wireframe is drawn faint — COMPOSITED at
`_DIM_ALPHA` (=0.15) over whatever's behind it (`_line(alpha=…)`), NOT faded-to-bg + painted opaque, so
a dimmed edge lets a crossed bright edge or number show THROUGH it instead of covering it. Face indices
show ONLY for the focused brush (in its tint). `--highlight` OVERRIDES focus — a
highlighted poly re-lights to its brush's vivid hue with a bolder line ON TOP of the dimming and KEEPS
its index even in a focused-out brush; a highlighted point keeps its selection brackets. All names
still appear in the legend regardless of focus.

**`--focus` is a BRIGHTNESS filter, and that is all it is** (owner ruling, 2026-07-29): it never changes
what is visible or what occludes what. Visibility is settled entirely by the cull — **a subtract's faces
are visible INWARD, an additive's OUTWARD** — and everything past the cull is ordinary physical depth,
nearest surface per pixel, with no brush privileged. So a box inside a room is not hidden by the room's
far wall whether the room is focused or not; a brush standing between the camera and the focused brush
DOES cover it; and a brush sealed inside a solid add is invisible, focused or not.

**Under a filled mode that costs ONE rasterizing pass, one depth buffer and a per-pixel mask.**
`_scene_geometry` puts every surviving face into a single `fills` list in **scene order** with a `dimmed`
flag — 1 when its brush is neither the focus nor `--highlight`ed, a BRIGHTNESS flag only — and
`render_brushes_pgm` rasterizes that one list, `_fill_face` recording `dimmed` into a `dim` byte per pixel
as each face wins the depth test. `_fade_dimmed` then fades every marked pixel toward `BG` at
`_DIM_FILL_ALPHA` (=0.35), **once per pixel, not once per face**. **The single scene-order loop is
load-bearing, not tidiness:** the depth test is strictly `<`, so a coplanar tie goes to whichever face is
drawn FIRST, and an earlier design that resolved the de-emphasised faces in a pass of their own therefore
let `--focus` choose which of two flush surfaces was visible — focusing a room lost its own floor to a
flush slab, and `--layout breakdown` focuses every brush pane in turn, so it was the common case.
`_DIM_FILL_ALPHA` is SEPARATE from `_DIM_ALPHA` (still the edge value, `wire` included) and is the owner's
value, picked from a ladder of renders (`spikes/2026-07-27-preview-focus-dim/`) and pinned by a test; why
it is a second constant, and why one blend: `rationale/preview.md`. With no `--focus` nothing is dimmed, so
no mask is allocated and no fade runs. `occluders` spans every brush, so decal grading is unaffected by
focus — consistent, since occlusion is too.

**Under a filled mode `--highlight` RE-COLOURS WHAT IS VISIBLE and is never an x-ray** (owner ruling,
2026-07-29, superseding the earlier "`--highlight` overrides `--focus`" ruling for the filled modes). It
still overrides `--focus`'s DIMMING — a highlighted face is full strength wherever its brush is, so it
never fades into the context — but it does not override depth. A highlighted face that depth hides
contributes **nothing at all**: no fill (it loses the depth test like any other), no outline, and no index
that the highlight alone asked for. Highlighting a sealed-in face changes the render byte-for-byte not at
all, which is what the test asserts.

`render_brushes_pgm` asks `_face_is_occluded` — after every fill is down, so `zbuf` is final — whether each
`vis_faces` entry is covered by pixels of which NONE is its own frontmost surface, comparing depths EXACTLY
(the float64 expression quantised to the `array("f")` the buffer stores). **Neither covering no pixel NOR being
edge-on is occlusion:** such a face keeps its outline, since nothing is in front of it. Those are two
separate halves — `_face_is_occluded`'s `covered` result and the caller's `plane is not None` guard — and
each is pinned on its own, because on a sliver brush the coverage-losing and edge-on faces project to the
same 2-D lines, so either half alone still draws the outline. The fully visible brush vanished from a
filled render only when one condition got both wrong. It is a **per-FACE** verdict, the same granularity as the subtract
cull, and deliberately not hidden-line removal. **`wire` is untouched and byte-identical**: `vis_faces` is
populated only under a filled mode, so nothing is ever in the hidden set there.
An index the `--annotate` spec would have drawn anyway is KEPT (`hi_only_labels` is exactly the set the
highlight alone owes) — on-face numbering is facing-blind by design and grades hidden faces down rather
than dropping them, and a highlight must never start deleting numbers.

**Full-strength and NUMBERED share only their focus half, and the implication runs ONE WAY.** Both test
"focused brush or highlighted face", but the index ALSO passes `--annotate`'s `AnnotationSpec`. So **a
numbered face is always full strength** — a number never lands on a dimmed fill — while the converse is
false: under `--annotate none` a focused brush's faces are all full strength and none is numbered. Do not
collapse the two into one flag. Both directions are pinned.
**Poly face indices are painted on the face — the sole poly-label renderer** (there is no leader-box
poly mode; the leader/arrow/box machinery below serves only actor names). Each face's index is a
texture painted flat in the face's own 3-D plane (`_plan_onface_texture` → `_DecalPlan`, drawn by
`_draw_painted_decal`), projected with the same `_project` as the wireframe, so it foreshortens with
the surface and reads as decaled on. `_face_decal_basis` builds the in-plane text frame: on
walls/slopes text-up (Vw) = world +Z projected into the plane (numbers hang by gravity, strokes stand
up the wall, view-independent); on horizontal floor/ceiling/cap faces (normal ≈ ±Z, no in-plane
gravity-up) the basis is fixed to the world axes (Vw = +Y, Uw = +X), so caps are consistently
Y-aligned rather than an arbitrary roll; Uw's sign is fixed from the screen projection so the glyph is
never mirrored (e.g. a ceiling's −Z normal). The glyph is sized in a fixed `_DECAL_SLOT_DIGITS`-wide
(=2) slot — `_text_bitmap` widens a short number to the 2-digit aspect and centres the digits in it
(extra columns blank, underline under the digits) — so a lone `5` scales like `12`. Placement and size
come from `_max_inscribed_box`: the largest glyph-aspect (the padded slot's) UV-axis-aligned box that
fits fully inside the face polygon (not its bounding box), and where it sits — on a rectangle the
centred box limited by the tighter dimension; on a triangle/arch/L an off-centre roomy spot. Convex
faces (the norm) solve exactly by eroding the polygon by the box (shift each edge inward by the box's
support, intersect) under a binary search on the per-texel `cell`; concave faces fall back to a bounded
grid × binary search (`_box_fits_2d`). Convexity is not a hard invariant — arbitrary UnrealEd vertex
editing can make a face concave, and 0.1–0.6% of faces in real exported maps are (measured
`spikes/concave-faces/`, live 2026-07-23), so placement detects convexity per face
(`_poly_is_convex_2d`). The decal is drawn at `_ONFACE_FILL` (=0.75) of that maximum; a face is omitted
when its number would be unreadable on screen — the smaller projected size of a glyph texel below
`_ONFACE_MIN_TEXEL_PX` (=2 px). This is a view-dependent verdict (chosen over the old world-uu one): a
face too small, too edge-on, or too zoomed-out gets no number, and the same face is numbered once it's
big enough on screen (zoomed in, or in its own `--layout breakdown` pane). There is no fallback for an
omitted face. Numbering is facing-blind (a face is painted if the spec would draw it in either facing,
so the default `poly:vis` still numbers back faces; `poly:hi`/`none` stay exact — the `--annotate`
`poly` selectors still gate whether numbers draw). The whole glyph — digits and the `_text_bitmap` 6/9
baseline underline — is one bitmap painted in one `_draw_painted_decal` pass at a single per-brush tint
+ `alpha` (so the underline can never read as a different brush's colour), with a translucent halo
(`_blend_px`). Decals draw after the name labels and seed `occupied` so name leaders avoid them.
`--focus`/`--highlight` still apply (focus paints numbers only on the focused brush; a highlighted poly
keeps its number).

**Overlapping numbers: a minimal nudge plus a white keyline.** The single spot above is
`_plan_onface_texture` = candidate 0 of `_onface_candidates`; the render resolves all faces' numbers
jointly (`_resolve_decals`) so they don't pile up, but repositioning is tiny and a white outline
carries the rest. `_onface_candidates` builds candidate 0 (full-size roomiest spot) first, then only
near-full nudges — `_RESHUFFLE_SCALES` (down to ≤10% smaller), each with its `_feasible_centers` so
the number can slide slightly. No deep size ladder, no rotation. Every candidate keeps candidate 0's
`_ONFACE_FILL` edge margin (`_feasible_centers` gets the padded box `cell/fill`, the max box the decal
is 0.75 of), so a nudged number never sits flush. `_resolve_decals` is greedy and deterministic:
biggest-primary face first; a candidate 0 with zero overlap (vs point-actor markers + committed decals
in `occupied`) is kept verbatim, so clean scenes match the single-placement planner byte-for-byte. On
overlap it restricts to candidates within the reshuffle budget — area ≥ `(1−_DECAL_MAX_SHRINK)²·area0`
(≤10% linear shrink) AND centre within `_DECAL_MAX_MOVE_FRAC` (=10%) of candidate 0's screen diagonal —
and takes the least overlap, then largest, then earliest. The keyline, not repositioning, keeps
overlaps legible. Overlap (`_rect_overlap_area`/`_overlap_fraction`) is summed per obstacle (stacked
patches count N×). The `_erode_convex`/`_feasible_centers` erosion is one Minkowski-erosion
implementation shared with `_max_inscribed_box`.

**The keyline** (`_draw_overlap_keyline`, called once after the decal draw loop): wherever two numbers'
`on` (glyph) pixel-sets overlap on screen, it draws a constant 1-screen-pixel white ring
(`_KEYLINE_RGB`) just outside each involved glyph's strokes — the 4-neighbour dilation of the `on` set
minus the set, restricted to near an overlap. Drawing outside the strokes (not on their boundary) keeps
it exactly 1px at any zoom and never a fill: it does not thicken as a number grows. `_draw_painted_decal`
returns its `on` set so the loop can collect them for this pass. *(decisions 2026-07-23 anti-overlap +
2026-07-23 minimal-reshuffle-and-keyline; spec in board item `actor-preview-on-face-number-overlap-minimal`)*

Each decal's opacity is graded by how deeply its face is buried. Every front face is collected into
`occluders` as `(poly2d, depth, brush_name, is_solid)`; `_occluder_count` counts how many lie in front
of a given face (nearer depth, covering its centroid) under the self-or-solid rule: a front face G
occludes face F iff G's brush is a solid CSG op (add/semisolid/mover) or G belongs to the same brush as
F. So a subtract/hollow room's near walls dim its own far walls (self-occlusion, depth grading inside a
room) without the room dimming a separate brush sitting inside it (a cube in a room stays bold); solids
still occlude across brushes. `_decal_opacity(n_front) = max(0.12, 0.56·0.6ⁿ)` turns that count into the
alpha — a visible face 0.56, one layer behind 0.336, floored at 0.12.

**`--layout breakdown` — a per-actor grid.** On-face numbers get only a
tiny within-face nudge (`_resolve_decals`: ≤10% shrink / ≤10%-diagonal move, never onto another face)
plus the white overlap keyline, so a crowded single view can still paint overlapping numbers (e.g. two
faces of one brush projecting onto the same screen region). Rather than fully disentangle them in one
frame, breakdown gives each brush its own zoomed shot — cross-brush overlap disappears and the
keyline only marks the occasional same-brush overlap. `dispatch._render_breakdown_grid` builds a
near-square grid of square PPM panes (`ceil(sqrt(N))` columns) stitched with **Pillow** (the sole
third-party dep, already used for the PNG write — `preview.py` has no rectangular-canvas primitive, all
its buffers are square-`size`, so the stitch lives in dispatch). The panes are PPM bytes, but the
stitched grid is **returned as a Pillow `Image`**, not re-encoded to PPM: the write boundary takes
either form (bytes from `preview.py`, an `Image` from here) so a breakdown never pays a
PPM→PNG round trip it has already paid once:
- **pane 0 (SCENE)** — the whole scene in CSG colour, a plain spatial map: NO labels at all (no legend,
  no names, no on-face numbers — `parse_annotation_spec("none")`). Actors are identified from their own
  captioned per-actor panes.
- **one pane per ACTOR, in actor-set order** (brushes and point actors intermixed). A **brush** pane is
  the scene `--focus`ed on that brush and framed to its own AABB (`_world_aabb([brush], render_data)`;
  the selector `--frame <name>` *targets*, framed tight since `--frame-tightness` does not apply), with
  all its faces numbered (focus paints numbers only on the focused brush). A **point** pane has
  `focus=None` and is framed by `_point_pane_region` — the point's `_world_aabb` EXPANDED to at least
  `Location ± _BREAKDOWN_POINT_MARGIN` (=32 UU) per axis; a marker-only point has a zero-size
  `_world_aabb` that `_framing` would otherwise collapse to a 1-unit window jamming the marker into a
  corner, so the margin guarantees a real, centred box. Every pane is captioned with the actor name.

Every pane frames its geometry with a minimal, CONSISTENT `_BREAKDOWN_PAD` (=16) px border
(`render_brushes_pgm(frame_pad=)` → `_framing(pad=)`) — no legend band, no per-actor world margin. The
overview is deliberately label-free, so no actor is named there — the captioned per-actor panes carry
the names. It prints the brush + point-actor counts to stderr (warning past `_BREAKDOWN_WARN_PANES`
=16 — a large selection, now including one pane per point actor, makes an unusably big grid).
`--layout breakdown` is one view (uses `--view`); it composes with `--annotate` (per-brush number set),
`--brush-colors`, `--highlight` (forwarded to every pane), `--show`, `--size`, and sets its own
focus/zoom per pane so a CLI `--focus`/`--frame` is ignored.

**Where NAME labels go** is geometry-aware. Poly indices are painted on-face (above); actor NAMES on
the **legacy** (non-hybrid) path are the only labels placed by `_place_labels` (on the hybrid `actor
preview` path names live in the legend, so the pass is empty). `_place_labels` (over frozen
`_LabelItem`→`_PlacedLabel`) minimises a cost per candidate ring position:
`k1·avg_density + k2·label_overlap + k3·leader_len` over a coarse **`DensityGrid`** of the drawn
wireframe **plus point-marker footprints, the legend rect, and the on-face decal boxes** (so labels flee
dense knots, actor icons, the legend, AND the painted numbers); `k2` high ⇒ no stacking, `k3` high ⇒ a
moderate drift cap. Every name is drawn OFF its anchor (no (0,0) ring slot) with a **leader ending in an
`_arrowhead`** at the exact target — cold readers read plain short stubs as mere proximity but reliably
trace arrow-tipped leaders. A brush's name anchors at the least-dense **vertex** (corner) of its own
wireframe — `_least_dense_anchor` — reading as "this whole shape", never the hollow interior of a concave
brush.

The renderer signature carries the preview state: `highlight` is a **set of `(actor_name,
poly_idx)`** (a highlighted poly draws in its brush's vivid front hue + a bolder line — NOT red,
which is retired); `color_by_csg` toggles the palette (off ⇒ the legacy black/grey, still the
`render_*_pgm` default for unit tests); `render_data` is a frozen **`PreviewData`** — everything
dispatch resolved for this render. `.points` maps a point actor's Name → a frozen
**`PointRender`** (decoded masked sprite `(w,h,rgb,mask)` + world footprint, or a marker, plus faint
collision/light/sound overlays). `.faces` is `None` under `wire` (which resolves nothing) and a
**`FaceData`** under a filled mode, carrying `movers: frozenset[str]` and `textures: TextureData | None`.
**Those two fields are separate on purpose:** `flat` needs the mover set and no textures at all, and a
single texture-named payload would invite passing `None` for `flat` — which drops the mover set and
makes the cull render a `CsgOper=CSG_Subtract` door inside-out. **`preview.py` stays resolver-free** — dispatch computes the
`PointRender`s in `_preview_render_data`/`_preview_point_data`/`_resolve_point_render`, resolving each field instance-else-
class-default via the `_class_defaults` seam and decoding sprites through a `_texture_resolver`
(`utexture.TextureResolver.resolve`, whose `DecodedTexture` carries the mask — palette index 0 =
transparent; a `TextureError` degrades to a marker with the case name in the stderr note). Brush-only previews resolve no
schema (a pure-brush `--faces wire` preview works with no game install); a point actor whose schema is unresolvable
degrades to an unscaled labelled marker + a stderr note, never a `SchemaError` traceback.
`render_quad_pgm` tiles four panes. `_render_actors_to_out` also resolves the `--frame` target
(`_parse_frame` splits an explicit six-field `X0,Y0,Z0,X1,Y1,Z1` AABB from a selector; the selector goes
to `_resolve_zoom`: a bare NAME → that actor's whole AABB, `BRUSH:idx` → one poly) and the
`--highlight POLY|NAME` tokens (`_resolve_highlights` splits colon
tokens into `(actor, poly)` pairs via `surface.parse_poly_selector`/`resolve_polys`, bare names into
whole-brush poly sets or point-actor bracket-highlight names) and
interpolates the frame between the whole-set extent and a SELECTOR target by `--frame-tightness` (an
explicit AABB is framed exactly). The `--show` comma-set (`_parse_show_set`, members
`collision`/`light-range`/`sound-range`) is validated up front and drives the point-actor overlays. The
whole path is **host-side, no container/editor**: `preview.py` returns PPM/P6 bytes in memory and the
write boundary (`_render_actors_to_out`) encodes them to **PNG** with Pillow (already the sole,
REQUIRED third-party dep) before writing. **PNG is the only on-disk preview form** — PPM is unviewable
by browsers, most viewers and an LLM, which is the audience previews exist for, so no CLI route to raw
PPM exists (decision 2026-07-24 21:57). `--out`'s extension is REPLACED by `.png` (`--out shot.jpg` →
`shot.png`); with `--out` omitted a `uedcli-preview-*.png` temp path is minted. Either way the absolute
path actually written is printed to stdout. The `actor`/`stash`/`prefab
preview` verbs were the only container users that drove neither the editor nor UCC; they no longer
need a running container at all.

## Testing
Offline unit tests (committed fixtures, no container):
```bash
cd Tools/uedcli && bin/test          # the auto-managed dev venv (bin/_venv.sh, .venv/)
```
Integration work runs against the live container; findings live in `dev/docs/spikes/`
(the editor state is the variable), and the `integration` marker is deselected by default.

## Substrate
`Tools/uedcli/uned/UED22` = committed pre-baked editor (OpenGL/32-bit, `SoftDrv` viewports, browsers
closed, `EditPackages` stripped with `DeusEx*`/LUM commented out — uncomment against a real
Deus Ex install). It is **baked directly into the image at its final runtime location** at build (`Dockerfile`
`COPY UED22/ /opt/UED22/` + `COPY entrypoint.sh wine_ctl.py /opt/uned/` — the *scripts* stay at
`/opt/uned/`), NOT read off a `/repo` mount at runtime — there is no `/repo` mount anymore
(container-fs isolation, D4). The committed `UED22/` is already the final editor (stripped
`EditPackages`, `SoftDrv` viewports, OpenGL inis), so there is **no boot-time assembly**: the
editor runs straight from the baked `/opt/UED22` and its writes (`Editor.log`, `Running.ini`,
`make` output) land on the per-container COW overlay, which never touches the image or the repo
(no `/repo` mount to pollute). The entrypoint only truncates the logs at boot — since the
asset-wiring cutover (2026-07-14) it no longer wires any `Paths=` (the host composes each
container's `[Core.System] Paths` + bind-mounts the crafted ini pre-launch). The Python side
already treats `/opt/UED22` as canonical (`packages._BAKED_UED22`,
`packages._EDITOR_INI`, `driver.py`/`store_export.py`/`texture.py`). See
[the decision](direction/containers.md).
The image must include `xclip` (clipboard read/write) and `imagemagick` (editor-screenshot
capture + crop for `level preview`/rendering — `wine_ctl.py`'s `import`/`convert`; NOT brush
`preview`, which is host-side Pillow).

**Code vs. content split.** Editor CODE (`.u`) is **substrate-authoritative**: UED22's
stripped, version-69 `.u` files are the only code the editor's runtime ever loads — the real
game's own Deus Ex `.u` can't be loaded into the running UT-lineage editor (its DLLs expect
UT's `Engine`/`Core` class graph + mesh format, which Deus Ex's diverge from) and is never
wired in. This is **not** a version incompatibility — UED22's `UCC.exe` reads the v68 packages
fine (it is the decompiler in the stub pipeline above); see
[`unrealed/package-format.md`](unrealed/package-format.md) (Deus Ex-install spike). Editor CONTENT (`Textures/*.utx`, `Sounds/*.uax`, `Music/*.umx`) is a SEPARATE
concern: a real Deus Ex install's content packages, copyrighted and never committed, are
needed to materialize real (non-synthetic) maps.

**Where the install content lives:** `Tools/uedcli/uned/DeusExAssets/` — a sibling of `UED22`
under the same `uned/` dir, gitignored, holding the install's content tree verbatim
(`Textures/`, `Sounds/`, `Music/`, plus inert `Maps/System/Help/Save` kept for completeness).
**Not** `_scratch/` — that dir is documented as throwaway-only, and this is a durable substrate
dependency. **To populate it from a Deus Ex install, see the runbook
[deusex-assets-setup.md](deusex-assets-setup.md)** (one command:
`dev/scripts/install-deusex-assets.sh <source>`, which also stages a full working game copy under the
gitignored `dev/games/<game>/` and populates this tree from it). The `System/*.u` (v68 code) are no longer merely
"inert kept for completeness" — they are the inputs to package stubbing. See `direction/containers.md`
(2026-06-21/22) for the stubbing + asset-layout rationale and the (rejected) alternatives.

The raw **installer** the content is extracted FROM lives at `Tools/uedcli/uned/deusex-installer/`
(the ACE archive `deusex.ace` + `.c00`–`.c52` volumes + `Install.exe`), also a sibling of `UED22`
and also gitignored. It was moved here out of `_scratch/` precisely because the once-extracted
`game/` content tree under `_scratch/` was already lost to a scratch wipe — `_scratch/` is
throwaway, so anything durable must live outside it. **Neither the installer nor the extracted
content is ever committed**: both are Deus Ex commercial game assets we have no right to
redistribute. They are user-supplied; the build and offline test suite must (and do) work without
them — only the live `integration`-marked verification of real maps needs them present.

**How it's wired in (config-driven, per-command — asset-wiring cutover 2026-07-14):** the content
is NEVER baked into the image (no `Dockerfile` `COPY` — it's user-supplied and the build must
succeed without it), and — since Part C — it is NO LONGER mounted statically by `docker-compose.yml`
either. The old static asset mounts (`DeusExAssets/ → /deusex:ro`, `Textures/`,`Maps/`,`System/` →
`/content/*:ro`, the Sounds/Music stub mounts) and the entrypoint's `$DEUSEX_ASSETS_DIR` `Paths`
`sed` block are **gone**. Instead every editor-driving command composes its OWN asset mounts:

- The **WHOLE composed config dir set** (per-user `[games.*]` base ⊕ per-project overlay — ONE
  uniform set, no code-vs-content split; `direction/containers.md`, 2026-07-14 19:21) becomes **read-only bind
  mounts at `/resources/<n>`** (`container_assets.resource_mounts` → `docker_mount_args`), computed
  ONCE per command and threaded.
- A **crafted `unrealtournament.ini`** whose `[Core.System] Paths` is regenerated wholesale over
  `[/stubs, /opt/UED22, /resources/<n>…]` (one line per dir × present extension — bare `*` stalls
  boot, `direction/containers.md`, 2026-07-14 12:00) by `container_assets.paths_ini_lines` is **bind-mounted over
  the baked ini PRE-LAUNCH, read-write** (`editor.engine_ini_mount`; wine + `UCC make`'s `cat >`
  rewrite it). `/stubs` (v69 stub cache) and `/opt/UED22` come FIRST, so a v69 stub SHADOWS any
  same-named v68 `.u` a composed code dir puts on Paths — the editor never loads a v68 package it has
  stubbed. This replaces the entrypoint's boot-time `sed`.

This is uniform across the GUI editor (`editor.ensure_editor`, for materialize/qualify/preview), the
no-GUI **build container** (`stub.ephemeral_build_container`, for stub-build + `texture sync`), and
the preview game — ALL mount the SAME whole composed set through `resource_mounts`. `build_stub`'s
`batchexport`/`umodel` read the v68 `.u` decompile SOURCE by its remapped `/resources/<n>` path
(never via Paths). The only static mounts left in `docker-compose.yml` are the baked-adjacent v69
stub cache (`${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}:/stubs:ro` — both
`editor.ensure_editor` and `stub.ephemeral_build_container` pass `UEDCLI_STUB_CACHE` = the resolved
`config.stub_cache_root()` in the compose env, so the mount honors `$UEDCLI_HOME`; the `${HOME}`
tail is only the hand-run-compose fallback) and the wine prefix. `packages.editor_search_dirs`
(host-side, `[/stubs cache, UED22, *composed dirs]`) resolves manifests, and
`packages._remap_to_container` maps each
host-resolved package file onto its container-visible root — baked `/opt/UED22`, a `/resources/<n>`
mount (via `container_assets.remap`, driven by the SAME threaded mount list — never recomputed), or
`/stubs` — at the single boundary in `packages.ensure_load`. The host-side closure/missing-package
checks and the container-facing loads thus agree on where to look. The only mutable host↔container
exchange is the container-local `/work` dir (see "Container filesystem isolation" below).

*(Deferred follow-up: the stub-build + `texture sync` mounts are sourced from the host
`packages.substrate_code_dirs` / `install_system_root` lists, NOT yet from a project's composed
config `paths` — folding that path onto the config layer, and re-basing `texture sync` discovery +
catalog dir onto the composed project path, are tracked in `board/inbox/`.)*

## Container filesystem isolation
**No live container can write into the repo tree.** There is no broad read-write `/repo` bind
mount (it was removed — container-fs-isolation design). The container's filesystem is three
disjoint domains:
- **Substrate — BAKED into the image** (`/opt/UED22` + the `/opt/uned/` scripts; see
  "Substrate"). Read-only as far as the repo is concerned; the editor runs straight from the
  baked `/opt/UED22` and any writes land on the per-container COW overlay.
- **Assets — READ-ONLY, config-driven per-command mounts** at `/resources/<n>` (the WHOLE composed
  config dir set — one uniform scheme, `direction/containers.md`, 2026-07-14 19:21) plus the `/stubs` v69 cache.
  The build container reads a v68 `.u` decompile source from its `/resources/<n>` path by explicit
  path; the editor reads content the same way and cannot write it. (Replaced the old static `/deusex`
  + `/content/*` compose mounts and the earlier `/install-system` code mount.)
- **Mutable exchange — the container-local `/work` dir**, created by the entrypoint's
  `mkdir -p /work` on the writable container overlay (deliberately NOT a tmpfs: `docker cp`
  writes a file UNDER a tmpfs mountpoint where it's shadowed and invisible to a live `exec`,
  which silently broke `cp_in` — verified 2026-06-21). `/work` dies with the container, so
  nothing it holds can outlive or leak into the repo.

`xfer.py` is the **sole owner** of `/work` path generation and the host↔container `docker cp`
boundary: `work_path(ext)`/`work_dir(stem)` mint uuid-suffixed paths (uuid because `/work` is
shared by reused/standing containers — a fixed path would race), `cp_in(container, host_path,
*, ext)` copies a host file IN and returns its RAW POSIX `/work` path (callers wrap with
`driver.to_z_path` where wine/UCC needs `Z:\`), `cp_out` copies a result file OUT, and
`remove` is best-effort cleanup (never raises — the editor is crash-prone). Every seam that
crosses the boundary goes through it: the target `.dx` is `cp_in`'d before any `MAP LOAD`/UCC
read (and the host snapshot under `<root>/.uedcli/tmp/` is itself made inside
`export_and_qualify`, from its threaded `state_dir`, so every caller gets it for free); results
(verified `.dx`, texture PNGs) are `cp_out`'d to host paths under `<root>/.uedcli/` or the
per-user cache; all editor scratch lives in `/work`.

**Writing the apply result back is atomic and repo-clean** (`apply._save_and_swap_verified` →
`_install_atomic`): the editor `MAP SAVE`s to `/work`, the H3 verify re-exports it **in the
editor container** (B1 — that container's `/work` is private to it, so the saved temp must be
read back there, not in the substrate container), then `cp_out` to a host staging file under
`<root>/.uedcli/tmp/` (the project state dir, threaded as `state_dir` from dispatch) and an
atomic `os.replace` onto the target. `os.replace` is atomic for an
in-repo target (same filesystem); for an out-of-repo target on a different filesystem (a
supported input) it raises `EXDEV`, and the fallback copies into a temp IN the target's own
directory and renames from there — same-fs by construction. Both temps are cleaned up on every
exit path, so no container-written temp and no stray dotfile ever lands in the repo tree.

# Asset wiring cutover — config dirs drive the container mounts + `Paths`

**Status:** draft, **revised after the 2-reviewer spec gate (2026-07-14)** — the first draft
under-scoped the blast radius and got the host/container split wrong; this revision resolves every
finding (each marked `[Rn]`). Decisions: `decisions.md` `2026-07-14 02:20 UTC — Asset wiring…`.

## 1. Goal

Make the **composed config `paths`** (per-user `[games.*]` base ⊕ per-project overlay), now **bare
directories**, drive the editor container: bind-mount each composed dir read-only at `/resources/<n>`
and craft the `[Core.System] Paths` from it. Retire the hardcoded content list in
`packages.substrate_search_dirs`, the static `docker-compose.yml` asset mounts, and the
`/deusex` `Paths` block in `entrypoint.sh`. Full cutover: the editor-driving paths (materialize,
qualify, preview, stub-build, texture-sync) use the config-driven mounts.

Out of scope (stated, not silently dropped): the preview game image (own spec); the `/resources/*/*.*`
wildcard *optimisation* — **being verified by a live spike now** (`spikes/2026-07-14-paths-wildcard/`),
§3 finalises once it reports; `schema_search_dirs` (the v68 CODE path — see §8, deliberately deferred).

## 2. The host/container invariant (the spine — `[R-crit]`)

**The Python process runs on the HOST. Every package *scan* (`os.listdir`, hashing) is host-side.
Only the editor, inside the container, sees `/resources/<n>`.** So there are two representations and
ONE translation boundary:

- **Host dirs** — what all the resolution/scan code consumes.
- **Container dirs** (`/resources/<n>`, `/opt/UED22`, `/stubs`) — what goes in the editor's `Paths`.
- **`resource_mounts` is computed ONCE per command and THREADED** to (a) the docker `-v` args, (b) the
  crafted `Paths`, and (c) the host→container remap. Nothing recomputes the index independently
  `[R-F3/#F3]`.

`substrate_search_dirs` **stays host-side** `[R-#1/F2]`. It is renamed `search_dirs` and now
*derives* the content tail from config instead of hardcoding it, but still returns **host** paths, in
the precedence order the code already depends on `[R-#5/F5]`:

```
search_dirs(project) -> [ uned/UED22 (substrate code, host),
                          ~/.uedctl/cache/stubs (v69 stub cache, host),
                          *project-overlay dirs (host),      # project shadows base
                          *base-game dirs (host) ]           # from the selected [games.*]
```
Substrate ≻ stub ≻ (project ≻ base) content — same invariant the old hardcoded list encoded, now
config-sourced for the content tail. `_ALWAYS_LOADED` (Engine/Core/Editor) is unchanged.

**ONE Paths-generation mechanism for EVERYTHING, incl. UED22 itself (Andrzej, 2026-07-14)
`[R-UED22]`.** The editor finds its OWN substrate packages via the same `[Core.System] Paths`, so
there is NO special-cased "baked substrate Paths" to preserve. Every host search dir above maps to its
**container** dir (`remap`) — `uned/UED22 → /opt/UED22` (baked in image), stub cache → `/stubs`
(baked-adjacent mount), each config content dir → `/resources/<n>` (bind mount) — and the SAME
`paths_ini_lines` generator emits the complete `Paths` set over that ordered container-dir list,
uniformly. UED22 is baked into the image (not host-mounted, not user-configurable — it's the editor),
but its `Paths=/opt/UED22/*.u` line comes from the generator like every other dir, not a hand-kept
baked entry.

## 3. Config: `paths` = bare directories

`config.py`:
- **`resolve_dirs(paths_str, base, *, require_absolute)`** replaces `expand_paths`: split on `:`,
  resolve each against `base` (games=absolute-required; project=relative-to-root). A leftover glob
  (`*` anywhere) → `ConfigError("paths are directories now — drop the /*.ext")` `[R-#F8]`. A
  **non-existent** dir is **skipped (not a hard error)** so offline model verbs still run for a user
  without the base game installed `[R-#9/F9]`; materialize's existing `missing_packages` fail-fast
  still catches an actually-needed missing package. Returns absolute host dirs, order preserved,
  **flat / non-recursive** (documented) `[R-#F8]`.
- **`composed_search_dirs(project, user_cfg)`** — project overlay dirs then base-game dirs, **deduped
  by directory keep-first**.
- **`composed_search_files(project, user_cfg)` is REBUILT** `[R-#F1/F1 — blocker]`: it is the load-set
  source (`dispatch._composed_load_set` → `search_path_package_names`). It must **scan each composed
  dir for the five exts** (`.u .dx .utx .uax .umx`, **case-insensitive** `[R-#F8c]`, flat), returning
  `(package_stem, host_file)` tuples **stem-deduped first-wins** so substrate/project shadow base
  `[R-#7/F7-dedup]`. Dir-dedup (mounts) and stem-dedup (load-set names) are SEPARATE and both required.
- **Migration** `[R-#10]`: rewrite `~/.uedctl/config.toml`, the LUM project `uedctl/config.toml`, and
  `_scratch` test configs from `.../X/*.ext` → `.../X`; update `config.py`'s docstring.

`Paths` **line form — per-dir-per-ext** (`Paths=/resources/<n>/*.<ext>` per mount × ext, emitting an
ext line only when that dir holds ≥1 file of it). The middle-dir wildcard (`/resources/*/*.<ext>`)
Andrzej preferred could NOT be verified standalone (`spikes/2026-07-14-paths-wildcard`: `OBJ LOAD
PACKAGE` doesn't reliably probe `[Core.System] Paths` — even the known-good per-dir form read
"unresolved" through it), so the cutover ships the **proven** per-dir-per-ext form (the entrypoint
already uses it, and every materialize this session resolved textures through it). The wildcard's
only correct test is **end-to-end** (a real materialize with wildcard-only Paths and no explicit
`OBJ LOAD FILE`); it is deferred to the integration step (§9) as an optional line-count optimisation,
with per-dir-per-ext as the guaranteed floor.

## 4. New seam: `container_assets.py` (host-fs reads only — NOT referentially pure `[R-#F10]`)

- `resource_mounts(content_dirs) -> list[Mount]`, `Mount = (host_dir, f"/resources/r{i:03d}")` over the
  composed order — deterministic, collision-free, readable `[R-#F3-agreed]`.
- `paths_ini_lines(container_dirs) -> list[str]` — the §3 form over the FULL ordered container-dir
  list `[/opt/UED22, /stubs, /resources/r000, …]` (UED22 + stubs + content, one generator for all —
  `[R-UED22]`); the per-ext variant does host `os.listdir` (via the paired host dir) to skip empty
  exts, hence "host-fs reads", not pure.
- `docker_mount_args(mounts) -> list[str]` — `["-v", f"{host}:{cont}:ro", …]`.
- `remap(host_path, mounts) -> container_path` — a host file under `mounts[i].host_dir` → its
  `/resources/r{i}/<basename>`; a file under `uned/UED22` → `/opt/UED22/…`; under the stub cache →
  `/stubs/…`. Replaces `packages._remap_to_container`; **takes the mount list** (no recompute)
  `[R-#F3]`. `/deusex` and `/content` roots are gone `[R-#4]`.

## 5. `editor.py` / `ensure_editor` — mount resources, set Paths PRE-LAUNCH

`ensure_editor(editor_id, *, mounts=None, ini_overrides=None, ready_timeout=…)`:
- adds `docker_mount_args(mounts)` to the `docker compose run` argv;
- writes the crafted `unrealtournament.ini` **byte-exact (`read_bytes`/`write_bytes`, CRLF preserved
  — a `read_text` universal-newline round-trip turns CRLF→LF and wine GPFs at boot; spike-verified)**
  and **bind-mounts it over `/opt/UED22/unrealtournament.ini` BEFORE wine launches** `[R-#3/F7 —
  blocker]` (a post-launch `sed` is erased when the GUI editor rewrites its ini from boot-time config
  — quirks.md "Containers / package resolution"). **This REQUIRES §7's removal of the entrypoint's
  `sed -i` on the same file** — spike-verified that `sed -i`'s rename-over fails on a single-file bind
  mount and kills boot, so the two are mutually exclusive. The crafted
  ini = the baked ini with its `[Core.System] Paths` lines **fully REPLACED by the single generated
  set** (UED22 + stubs + content, from `paths_ini_lines` — `[R-UED22]`, which resolves `[R-#2]`: the
  editor's own `Paths=/opt/UED22/*.u` is REGENERATED, not preserved, so a wholesale replace is safe and
  there is no strip-vs-keep split). Every other baked key (`SavePath`, `Suppress=…`, viewport
  sections) is left untouched. Mounted **read-write** (wine rewrites inis on exit; `:ro` → EACCES →
  GPF), to a deterministic `state_root()/tmp` path, **cleaned up in `stop_editor`** `[R-#F7]`.
- `mounts=None` (no project / CSG-only generator) → just `/opt/UED22` + `/stubs`, no `/resources`
  `[R-#F9/F11]`.

## 6. Threading — the 4 call sites + `ensure_load` (`[R-#F4/#4 — blocker; NOT already wired]`)

No call site passes a project today; this is NEW plumbing:
- `dispatch._level_materialize` → resolves project → `content_dirs = composed_search_dirs(project)` →
  `run_materialize(…, content_dirs=content_dirs)`. `run_materialize` computes `mounts` once, passes to
  `ensure_editor(mounts=mounts)` and to `ensure_load(…, mounts=mounts)`.
- `qualify.export_and_qualify` (`qualify.py:~331` `ensure_editor` + its `transitive_closure` +
  `ensure_load`) — same threading `[R-#F5-qualify]`.
- `preview` (`preview_render`/future `preview_game` `ensure_editor`) — same.
- `dispatch.py:~221` generic editor op — `mounts=None` path (§5).
- `packages.ensure_load(driver, manifest, *, search_dirs, mounts)` — remap via the threaded mounts.
- **Build container** `stub.ephemeral_build_container` + `texture sync`'s
  `enumerate_substrate_packages` `[R-#4/#F5 — blocker]`: these lost `/deusex`+`/content` when compose
  mounts go; they must take the same `docker_mount_args(mounts)`. `stub.py`'s `/deusex/System` v68
  source becomes a config-derived host dir (or explicitly deferred with §8).

## 7. `docker-compose.yml` + `entrypoint.sh`

- Remove the static asset mounts (`/deusex`, `/content/*`, Sounds/Music stubs); keep image/build,
  `wine-prefix`, env, `ports`, `/work`, and the `~/.uedctl/cache/stubs:/stubs` mount (baked-adjacent).
- `entrypoint.sh`: delete the `$DEUSEX_ASSETS_DIR` `Paths` block (host composes Paths now); keep the
  rest.

## 8. `schema_search_dirs` — deferred, explicitly `[R-#8/F5-schema]`

The v68 CODE path for offline `actor prop` schema (`packages.schema_search_dirs`, hardcoded
`uned/DeusExAssets/System`) is a DISTINCT concern (v68 code, not v69 content) and is **out of scope**
here. It keeps working (reads on-disk host dirs, independent of compose mounts) but now diverges from
the config-driven content path. Action: update its docstring TODO to reference this cutover and add a
`board/inbox.md` item to re-base it onto the config `paths` layer. Not silently ignored.

## 9. Test plan

- **New unit — `container_assets.py`:** `resource_mounts` id stability/uniqueness/order; `paths_ini_lines`
  (both forms per spike; empty-ext skip; case-insensitive); `docker_mount_args`; `remap` (content dir →
  `/resources/rNNN`, UED22 → `/opt/UED22`, stub → `/stubs`, threaded mount list, no recompute).
- **New unit — `config.py`:** `resolve_dirs` (abs-required games; relative project; **missing dir →
  skipped, not raised**; leftover-glob → the migration ConfigError); `composed_search_dirs` order +
  dir-dedup; **`composed_search_files` scans-by-ext + stem-dedup first-wins** (the F1 blocker gets its
  own tests).
- **Migrate existing tests** `[R-#10/F10]`: `test_config.py` (glob → dir semantics),
  `test_packages.py` (`test_remap_deusex`/`test_remap_content` assert the now-removed `/deusex`,
  `/content` → rewrite to `/resources`), `test_dxpkg.py`/`test_texture_integration.py`
  (`substrate_search_dirs` → `content_search_dirs`).
- **Integration + the REAL gate** `[R-#6/F6]`: the merge gate is **re-running the known-good 161-actor
  castle materialize + H3 post-verify** through the config-driven mounts (the artifact already proving
  the path works), NOT just a small level. Offline suite green is necessary but insufficient (it can't
  see a live-mount regression), so the castle run is a required pre-merge step, stated here.

## 10. Docs to update on landing `[R-#F10]`

`architecture.md` (D4 container-fs roots `/deusex`+`/content` → `/resources/<n>`); `unrealed/quirks.md`
("Containers / package resolution" — the deleted `/deusex` Paths mechanism); the layout spec
`2026-06-20-uedctl-deusex-assets-layout-design.md` (its `DeusExAssets`/`/deusex` model is superseded —
mark it so).

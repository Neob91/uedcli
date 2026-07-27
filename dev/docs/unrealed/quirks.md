# UnrealEd 2.2 — quirks & non-obvious behaviors

The weird, hard-won, *surprising* facts about UnrealEd-2.2-under-wine — the things that
silently bite you. Command syntax is in [`commands.md`](commands.md); rendering/screenshot
behavior is in [`rendering.md`](rendering.md). Evidence: `../../dev/docs/spikes/`.

## Stability
- **The editor crashes/wedges often, even idle**, into a "process alive, window gone" zombie
  (sometimes with a `Critical Error` GPF dialog). Always poll liveness; recover with
  `docker compose up -d --force-recreate`. `wine_ctl` fast-fails on this rather than hanging.
- **A "Cleaning up..." GC-progress dialog (window titled literally `xmessage`) appears around
  the garbage-collect pass that fires on nearly every `MAP NEW`/`IMPORTADD`/`REBUILD`, and never
  auto-closes under headless SoftDrv** — confirmed live 2026-06-20: sat unattended 60+ seconds
  with zero progress. It blocks every later console command from reaching the Command box until
  dismissed. Dismiss with `xdotool windowactivate --sync <id>` then a **window-less** `key
  Return` (NOT `xdotool key --window <id>` — `X Error: BadWindow`; wine ignores synthetic
  `--window` events). `Driver.dismiss_blocking_dialog()` does this; `qualify.dump_obj_dependencies`
  calls it defensively before every retry. To actually SEE the dialog's content: a per-window
  `import -window <id>`/`xwd -id <id>` capture of it both came back showing the *editor's*
  toolbar instead (unexplained) — cropping a **full-root** screenshot at the dialog's
  `wmctrl -l -G` absolute geometry worked. **Scope of the block (✅ 2026-07-18): the dialog
  blocks the Command-BOX input path only — it does NOT stall the engine's own exec loop.** An
  `EXEC <file>` command script keeps executing its remaining lines while the dialog is up (a
  mid-script `MAP NEW` popped it; the following script commands still ran, verified by their
  file side effects) — so batching a sequence into one `EXEC` script rides straight through the
  dialog that would stall the same sequence typed command-by-command. Dismiss before the NEXT
  typed submission as usual. (spike `../spikes/2026-07-18-exec-file-console-batch/`; see
  `commands.md` "`EXEC <file>`".)
- 🔬 **A reused editor driven for a SECOND materialize after an H3 post-verify intermittently
  loses the next `MAP SAVE` (silent no-file).** Driving one warm editor through many
  `level materialize` builds back-to-back (no teardown between), a build whose H3 post-verify
  completes leaves the editor in a state where the NEXT build's drive runs but its `MAP SAVE`
  writes **nothing** — the verify's UCC export then aborts `Failed loading package: Can't find
  file '/work/<uuid>.dx'`. Roughly **half** of reused builds fail this way (3/6 in one run, 2/4 in
  two others; the per-build pattern is not cleanly deterministic). It is **NOT** the GC "Cleaning up…" dialog
  (dialog absent; a defensive dismiss+settle does not help) and **NOT** the UCC batchexport being a
  second `wine` process (isolating the export to a separate container does not help). With verify
  disabled (`no_verify`) the same warm editor builds cleanly **every** time, and a genuinely-reused
  *successful* build was verified equal to a fresh build — so the drive + `MAP SAVE`
  are reliable and reuse does not corrupt content; the disruptor is
  the H3 verify's interaction with the warm editor (its live `OBJ DEPENDENCIES` qualify dump / the
  editor being mid-verify) racing the next build's fire-and-forget drive (same class as the §89
  "`wine_ctl exec` is fire-and-forget, `MAP SAVE` races the still-running rebuild" finding, surfaced
  because warm reuse is the first path to drive a *second* build after a verify). Live 2026-07-19,
  spike `../spikes/2026-07-18-warm-editor-materialize/` (`results.md`; harnesses
  `warm_editor_probe.py` / `warm_editor_noverify.py`). **Consequence for warm materialize:** the H3
  verify must run against a SEPARATE throwaway editor (as `qualify.export_and_qualify` already does),
  or after a robust editor-quiesce/idle barrier — not against the warm editor between builds.
- **`Editor.log` is a 4KB stdio-buffered stream — already-written content can sit invisible to
  an external reader (`stat`/`tail`) until something pushes total bytes-since-last-flush past
  the next 4096-byte boundary.** Confirmed live 2026-06-20: every observed log-size delta in a
  long investigation was an exact multiple of 4096. A settle command that's a silent no-op when
  nothing matches (e.g. `OBJ LIST CLASS=Mesh NAME=zzz` with no such mesh) adds zero bytes and
  never forces a flush — a genuinely-already-complete dump can look permanently "stuck" purely
  because the read raced ahead of the next flush. Fix: use a settle/filler command GUARANTEED to
  produce a large amount of output (`OBJ LIST CLASS=Class` — every loaded class, ~tens of KB,
  always non-empty), and check for a real completion marker in the read text rather than
  guessing from a fixed sleep. See `qualify.dump_obj_dependencies` and
  `dev/docs/spikes/2026-06-20-obj-dependencies-untextured-poly-correlation.md`.

### The GUI editor cannot run under x86-32 EMULATION; UCC can 🔬

On an **aarch64** host (Apple Silicon), `docker build --platform linux/amd64` of `uned/Dockerfile`
succeeds and wine runs, but **`unrealed.exe` dies at startup every time**:

```
General protection fault!
History: SyntaxHighlighting::AddQuote <- SyntaxHighlighting::Setup
      <- WCodeFrame::OnCreate <- WM_CREATE
```

It is deterministic, not the intermittent startup flakiness `editor.ensure_editor` retries around —
four reap-and-respin attempts all crashed identically. Verified on the **unmodified** image with no
asset mounts, no ini changes and no console command issued, so nothing about a caller's setup is
implicated: the fault is in the editor creating its UnrealScript code-editor window
(`WCodeFrame`) under `qemu-i386`.

**`UCC.exe` is unaffected** — a console app that creates no windows. In the very same container, under
the same emulation, `xvfb-run -a wine UCC.exe batchexport <map>.dx Level T3D 'Z:\work\out'` exported
retail maps successfully. That is the control that isolates the fault to GUI window creation rather
than to wine or the emulation generally.

**Consequence for tooling:** on such a host the **offline/UCC** routes work (native decode, map
export, `batchexport` textures) and every route needing the live editor does not — `level
materialize`, `level preview --game`, and any `MAP EXPORT`/`EDIT COPY` oracle. Those need an x86-64
host. (2026-07-27)

## Viewport focus & input model (UED22)
- **UED22's viewport input is a focus-bound "activate-then-operate" model: the first mouse gesture
  in a newly-clicked viewport is spent *activating* it; the operation rides on the *next* gesture.**
  📖 A drag (camera-look / brush- or actor-move) is honored only once the viewport is **captured**,
  and `UWindowsViewport::SetMouseCapture` engages capture **only if `GetFocus()==this window`**. A
  click into an unfocused viewport first transfers Win32 focus (`WM_SETFOCUS` →
  `UWindowsClient::MakeCurrent`), so that click's own drag is the focus-establishing gesture, not an
  operating one. This is an OldUnreal rewrite specific to **UnrealEd 2.2** (`WinDrv.dll`
  `UWindowsViewport`); retail UED 1.x / stock UED 2.0 used a plain absolute `WM_MOUSEMOVE` model with
  no focus-gated capture, so the symptom is UED22-only. It is **not** `WM_MOUSEACTIVATE` eating the
  click (that handler returns `MA_ACTIVATE`, not `MA_ACTIVATEANDEAT`, so the click *is* delivered) —
  the trigger is focus/input **timing**: it reproduces natively under Lutris+Proton but **not** through
  the noVNC bridge (which emits an absolute move before the press, letting focus+capture settle).
  Levers to try: `[WinDrv.WindowsClient] CaptureMouse=False` or `UseDirectInput=True`. (spike:
  `../spikes/2026-06-26-ued22-viewport-focus-click-eaten/`, static DLL disasm + live narrowing 2026-06-26)

## Containers / package resolution
- ✅ **To set `[Core.System] Paths` (or any `unrealtournament.ini` change) at launch, bind-mount a
  byte-exact crafted ini over `/opt/UED22/unrealtournament.ini` BEFORE wine starts — and you must
  do it byte-for-byte AND ensure nothing `sed -i`-edits that file.** Two live-verified traps
  (spike `2026-07-14-paths-wildcard`): (1) the ini is **CRLF** and wine's parser GPFs on LF, so a
  Python `read_text`/`write_text` round-trip (universal-newlines → LF) makes the editor fail to boot
  — craft with `read_bytes`/`write_bytes`. (2) `sed -i` on a **single-file bind mount** fails (its
  temp-then-rename-over can't replace a mount point) and, under `set -e`, kills the entrypoint → no
  boot; so the entrypoint's own `Paths` `sed -i` block and a pre-launch ini bind-mount are mutually
  exclusive (remove the former to use the latter). **Resolved 2026-07-14 (asset-wiring Part C): the
  entrypoint's `$DEUSEX_ASSETS_DIR` `Paths` `sed -i` block was DELETED entirely** — Paths are now
  composed host-side and bind-mounted pre-launch for every container (`editor.engine_ini_mount`,
  shared by the GUI editor and the no-GUI `stub.ephemeral_build_container`), so nothing edits the ini
  in the container anymore. A post-launch `sed`/edit is separately futile — the GUI editor rewrites
  the ini from its boot-time in-memory config and erases it (see below).
- 🔬 **`OBJ LOAD PACKAGE=<name>` (name only) does NOT appear to search `[Core.System] Paths`** — it is
  not a reliable way to test whether a Paths entry resolves a package (even a known-good
  `Paths=/resources/A/*.utx` reads as "not loaded" through it). Content packages resolve via `MAP
  LOAD`/demand-load or an explicit `OBJ LOAD FILE=<path>`; uedcli's materialize uses the latter. So
  the middle-directory wildcard `Paths=/resources/*/*.utx` remains UNVERIFIED (not shown to fail —
  just untestable this way); verify it end-to-end (a real materialize with wildcard-only Paths) if the
  line-count optimisation is ever wanted. (spike `2026-07-14-paths-wildcard`.)
- **The locally cached `dx-lum-uned:latest` image can be STALE relative to `Dockerfile` —
  `docker compose run`/`up` silently reuses it, never auto-rebuilds on a Dockerfile change.**
  Confirmed live 2026-06-20: the image cached on this devbox still had the pre-`Extra/AI`→
  `Tools/uedcli`-rename `ENTRYPOINT`, even though `Dockerfile` had long since been corrected to
  `/repo/Tools/uedcli/uned/entrypoint.sh` — every FRESH per-session editor (`ensure_editor`,
  i.e. every real `level apply`/`level preview`/`session start <dx>`) failed immediately
  (`bash: /repo/Extra/AI/entrypoint.sh: No such file or directory`, container exits 127) while
  the already-running persistent `dx-lum-uned` kept working fine (it doesn't need to pull the
  new image — it's already up). **If a fresh per-session editor won't start, `cd
  Tools/uedcli/uned && docker compose build` before debugging anything else.** This is a
  per-machine operational fix, not something a commit can carry. **This now bites HARDER under
  container-fs isolation:** the whole UED22 substrate is BAKED into the image (directly at
  `/opt/UED22`), and `entrypoint.sh`/`wine_ctl.py` are baked at `/opt/uned/` — no longer read off
  a `/repo` mount — so a script or substrate change does NOT take effect until you rebuild, where
  the old mount picked it up live. Any edit under `uned/` needs a `docker compose build`.
- **`/opt/UED22`'s inis are FLAT and lowercase** — `unrealtournament.ini` directly under
  `/opt/UED22/`, no `System/` subdirectory anywhere in this substrate (confirmed on the
  persistent container, a fresh per-session one, and the committed repo substrate alike). Any
  code that hardcodes an ini path must use `/opt/UED22/unrealtournament.ini`.
- **`sed -i '/pat/a TEXT' file` only accepts a SINGLE line of `TEXT`** — a literal embedded
  newline in the `-e`/script argument terminates the `a` command's text early and leaves the
  remainder as an invalid dangling command (`sed: extra characters after command`). Appending
  N lines needs the classic backslash-newline-continued form: `a\` then each line (including
  the first) ending in `\` except the last. Bit this live 2026-06-20 adding 2+ `Paths=` entries
  at once (`packages.write_paths_and_reload`) — a single entry never exposed it.
- **A HOST-absolute path is NOT valid inside the editor's container.** A host absolute path
  (e.g. `/home/human/src/dx_lum/Textures/X.utx`) doesn't exist inside the container's
  filesystem at all. `OBJ LOAD FILE=<host path>` / a `[Core.System] Paths=<host path>` ini
  entry both fail to resolve (`Can't find file 'Z:\home\...'`). And there is **no `/repo` mount
  anymore** (container-fs-isolation, D4) to re-root onto — the container sees the repo's content
  only through the BAKED substrate (`/opt/UED22`), the READ-ONLY config-driven content mounts
  (`/resources/<n>`, per-command — asset-wiring cutover 2026-07-14, was `/deusex`+`/content`), and
  the `/stubs` v69 cache. Any code that resolves a package file on the HOST (necessary — the Python
  process must `os.listdir()` the real filesystem) must remap the host path onto whichever of those
  container-visible roots contains it before handing it to a container-facing call. See
  `packages._remap_to_container` (the single remap boundary, called inside
  `packages.ensure_load`).
- **The reverse direction has the same trap.** A relative `.dx` path a user types (`--out`,
  `--map`, …) resolves against the PROCESS cwd (or is absolute), exactly like every other CLI
  tool — pinned to host-absolute *once, at the CLI boundary* (`os.path.abspath`), and the
  resulting HOST path must be `cp_in`'d before any container-facing read (previous bullet).
  (Historical note: the session store used to record *repo-relative* / legacy `/repo/...` paths
  re-rooted by `repo_paths.to_host_path`; both the store and that module are deleted —
  layout reorg 2026-07-17 — so cwd-relative CLI resolution is the ONLY path class left. The
  2026-06-21 lesson stands in spirit: pin a user path to absolute ONCE, at the boundary,
  never deep inside the flow — a late `Path(p).resolve()` silently re-anchors on whatever the
  process cwd happens to be.)
- **CLOSED 2026-06-20 — was: "a package can have its OWN further package dependencies your
  level's `.dx` never directly references."** `CoreTexMetal.utx` itself depends on
  `CoreTexDetail` (a detail-texture overlay package); loading `CoreTexMetal` alone used to fail
  (`Can't find file for package 'CoreTexDetail'`) because `dxpkg.direct_packages` (and therefore
  `ensure_load`) only ever saw a level's OWN direct import-table deps, never a dependency's own
  further deps — let alone a CONTENT-to-content dependency like this one (`CoreTexMetal.utx` →
  `CoreTexDetail`), which a code-only closure couldn't have caught either. Fixed by wiring
  `dxpkg.transitive_closure` into all three manifest call sites (`apply._theirs_packages`,
  `dispatch._extract_manifest`, `qualify.export_and_qualify`) AND extending the closure itself to
  recurse into content packages, not just code (`.u`) ones — `parse_header`/`direct_packages`
  are generic UPackage-format readers, so they read a `.utx`'s own import table identically.
  Needed version tolerance too: levels are version 69, the install's content packages are
  overwhelmingly 68 (same name-table layout), now all three supported — 61/68/69. The five
  version-61 packages (`CoreTexDetail`/`CoreTexWater`/`Palettes`/`Render`/`TITAN`) use a
  different name-table format (null-terminated string + 4-byte flags, no compact-index prefix)
  confirmed 2026-06-23 (🔬 `spikes/2026-06-23-capability-gaps-round2.md`); their own deps are
  just Core/Engine (substrate), so the closure terminates cleanly after recursing into them.
  Measured against the real install: closures over 6 real maps land at 6-65 packages, not the
  whole ~190-file install. See `dev/docs/specs/2026-06-18-uedcli-package-extraction-design.md`
  and `board/to-spec/`.
- **`[Core.System] Paths` is first-match-wins, and only `UCC`/the by-name linker honors it — a live
  console `OBJ LOAD` does NOT** (🔬 2026-07-01, `spikes/2026-07-01-paths-precedence/`). Two dirs on
  `Paths` each holding a same-named package: the one listed FIRST resolves (order, not filesystem
  luck; confirmed both orderings + a substrate-shadow control). But: (a) **`UCC.exe` reads the ini
  fresh per invocation and does the real by-name glob search** — `UCC batchexport <pkg> Texture pcx`
  is the reliable precedence probe (the exported set reveals which file won). (b) **No live-editor
  console verb does a by-name `Paths` search:** `OBJ LOAD PACKAGE=Foo` is a silent no-op,
  `OBJ LOAD FILE=<bare-name>` fails; only `OBJ LOAD FILE=<resolved path> PACKAGE=` works (explicit
  file, bypasses `Paths`) — which is exactly why uedcli's `apply` resolves the file HOST-SIDE and
  `OBJ LOAD FILE=`s it, so overlay shadowing is a host-resolver job, not the editor's. (c) Only
  **directory-glob** `Paths=` entries (`<dir>/*.utx`) are searched — a full-file-path entry is
  ignored.
- **The running GUI editor rewrites `unrealtournament.ini` from its boot-time in-memory config and
  ERASES any `Paths=` line added after launch** (🔬 2026-07-01, same spike) — worse than "doesn't
  re-read mid-session": it clobbers your edit, and a slow gap between edit and read lets it win the
  race (spurious `Can't find file`). **Do the ini `Paths=` edit and the consuming op in ONE atomic
  `docker exec`.**

## T3D format

> The T3D on-the-wire format (block nesting, property line forms, winding,
> fractional vertices, what T3D can't carry, authored-vs-computed taxonomy)
> is documented in [`t3d.md`](t3d.md). This section covers only the
> **gotchas** — the surprising behaviors that bite.

- **`MAP IMPORTADD` grid-snaps** placement — set `MAP GRID X=1 Y=1 Z=1`
  first for exact coords. The format itself carries fractional coordinates
  faithfully (see [`t3d.md`](t3d.md) "Fractional vertices"); the snap
  happens on import, not in the T3D text.
- ✅ **`EXEC` does NOT abort on a failed line, so a failed `MAP LOAD` leaves the PREVIOUS level
  loaded and the next `MAP EXPORT` writes THAT** — a complete, healthy-looking export of the wrong
  map. Hit live 2026-07-26 (`../spikes/2026-07-26-ucc-export-completeness/`): three maps the
  substrate could not load each "exported successfully" as byte-identical copies of the map loaded
  before them; only the identical file sizes gave it away. **Guard by emptying the level first
  (`MAP NEW` before `MAP LOAD`)** so a failed load yields an unmistakably tiny export, and check the
  actor count. The general rule this instances: **a completion marker proves a script RAN, never
  that it did what it was asked** — so no script-driven operation may be judged by its marker alone
  (`commands.md` "`EXEC <file>`").
- ✅ **The editor is NOT authoritative on the CASE of an actor name; the package is, and UCC reports
  it faithfully.** UE1 `FName`s are case-insensitive, and on `MAP LOAD` a name already registered in
  the editor process wins over the spelling the package stores. Measured 2026-07-26 across 5 retail
  maps: UCC always wrote the package's stored spelling, while a REUSED editor wrote `Light1` for
  maps storing `light1` — and a FRESH editor loading the same map wrote `light1`. So a reused
  editor's `MAP LOAD` exports drift with what it loaded earlier in the session.
  **`EDIT PASTE` does NOT drift** — three successive `MAP NEW`+paste builds in one editor round-trip
  `probelight1`, `ProbeLight1`, `probelight1` each verbatim. So the boundary is the verb: **`MAP
  LOAD` into a reused editor re-cases, `EDIT PASTE` does not** (mechanism unestablished). This
  matters because `normalize.compare_view` keys actors by VERBATIM name (property keys and class
  names are casefolded; actor names are not) — so re-opening a built map in a reused editor could
  fail the post-verify on a correct build, while `level materialize`'s own build path, which never
  `MAP LOAD`s, is unaffected.
- **Static-array actor properties (`Foo(N)=<value>`) round-trip
  faithfully through uedcli (since 2026-06-25).** The T3D format
  serializes any UScript `var Foo[K]` array as separate indexed lines
  (`KeyPos(1)=(Z=128.0)`, `MultiSkins(2)=Texture'…'`, …) — see
  [`t3d.md`](t3d.md) "Indexed static-array form" for the full format spec.
  `model._PROP` now captures the `(N)` index as part of the key, `emit`
  re-emits the line verbatim, and `normalize` keeps authored indexed props
  (only `AIProfile(N)` is computed-stripped). This was previously a gap —
  `model._PROP` matched only `Key=Value`, silently dropping every indexed
  line — fixed by the mover-support work (`Mover` keyframes / multi-skin
  arrays depend on it; resolved, no longer a gotcha).
- **No coplanar auto-merge** on `BRUSH IMPORT`/`MAP IMPORTADD` (a 7-poly
  split-face cube round-trips as 7). Merging is only the explicit "Merge
  Polygons" command / a builder flag.
- **The `Group` component of a qualified `Texture=Package.Group.Name` is
  NEVER required, even when the object genuinely has one.** Confirmed live
  (2026-06-20): `Area51Wall_A` actually lives in `Group=Metal` inside
  `CoreTexMetal`, and the bare 2-part `Texture=CoreTexMetal.Area51Wall_A`
  (no group) bound it correctly — re-export came back with the bare bound
  name, proving it resolved the same object the 3-part form does. The
  editor searches a named package's objects by `Name` regardless of group;
  group is a display/organizational detail only. **uedcli convention:
  always write/construct qualified texture refs as `Package.Name` — never
  include the group**, even when one is known to exist. This does NOT apply
  to a ref *read back* from the editor — store and round-trip whatever the
  editor printed verbatim; only ref **construction** skips the group.
  See [`t3d.md`](t3d.md) for the polygon `Texture=` field reference.
- **A qualified `Texture=` does NOT auto-demand-load its package on
  `MAP IMPORTADD`, even when the package is on the `[Core.System] Paths`
  search list.** The authoritative evidence is the controlled fresh-container
  correlation spike
  (`../spikes/2026-06-20-obj-dependencies-untextured-poly-correlation.md`,
  five `MAP NEW`→import→export rounds): importing a brush face with
  `Texture=CoreTexMetal.Area51Wall_A` into a fresh editor re-exported with
  **no `Texture=` at all** — unbound. The SAME T3D bound correctly once
  `CoreTexMetal` was explicitly `OBJ LOAD`ed first. **Caveat — the spike
  record is not unanimous:** an earlier probe (Test 3 of
  `../spikes/2026-06-19-t3d-package-qualification.md`) *appeared* to show a
  qualified ref demand-loading its package in a warm session. It does not
  hold under the materialize path's fresh-container conditions; why the two
  differ (import verb? residual session state?) is unresolved and would need
  a live re-test. The shipped `apply` path explicitly `OBJ LOAD`s every
  manifest package regardless — a safe superset that doesn't depend on the
  answer. **Practical rule: a package referenced only via a qualified
  `Texture=` inside imported T3D must be explicitly `OBJ LOAD`ed BEFORE
  the import — being on the `Paths` list is necessary but not sufficient.**
  Fixed 2026-06-20 in `apply`'s materialize path
  (`packages.obj_load_entries`). See also [`t3d.md`](t3d.md) "What T3D
  cannot carry" for what IS lost vs what is just unbound.
- ✅ **`OBJ DEPENDENCIES PACKAGE=MyLevel` emits an EXTRA `Engine.Polys` block
  for the level's own world BSP `Model` — an AGGREGATE of every brush's
  surviving surfaces — and its position among the per-brush blocks is NOT
  stable.** Besides one `Engine.Polys` block per authored brush (each carrying
  that brush's textured polys in poly order), the dump carries one more
  non-empty `Engine.Polys` block: the world `Model`'s post-CSG surface set,
  whose texture list is the union of all the brushes'. Live-probed 2026-07-14
  (`../spikes/2026-07-13-semisolid-save/probe_tree.py`, `probe_aggregate.py`):
  it appeared **last** for a 2-brush room+cube level (`[6,0,6,0,12,0,0]`, the
  `12`=6+6), **first** for the 95-brush castle (an 853-texture block, ahead of
  the first brush), and in the **middle** for a World-shell+cubes level
  (`[6,6,18,6]`). It ALSO appears a second time as a same-textured
  `Engine.Model` block (per-brush inner Models are empty). An older 2026-06-20
  probe saw this world-Model block EMPTY (a single subtractive brush); it is
  non-empty once any brush contributes a surviving textured surface. **Practical
  rule: never correlate dump blocks to brushes by position or count — bind each
  brush to the block whose per-poly object-names match its own, and drop the
  unclaimed aggregate** (`qualify.qualify_level_textures`, content matching,
  2026-07-14; see `decisions.md` same date).
- ✅ **A `--solidity semisolid` brush does NOT break `LIGHT APPLY` or `MAP
  SAVE`.** A one-shot materialize failure once looked semisolid-specific, but
  the exact conjunction (full castle + 16 semisolids + `LIGHT APPLY` + `MAP
  SAVE`) saved cleanly across 3 repeats plus solid+light and semi+no-light
  controls (`../spikes/2026-07-13-semisolid-save/probe_bug2.py`, 2026-07-14).
  The one-off was a transient silent editor wedge (see "Stability" above), not a
  code defect. Semisolid emission is byte-correct (actor-level `PolyFlags=32`,
  NOT per-poly `Flags=32`).
- ✅ **A materialize round-trip is faithful only up to four editor-owned
  representation details — canonical comparison must ignore all four.** Driving a
  real 161-actor level through `level materialize` + H3 post-verify surfaced them
  in order (2026-07-14, each fixed in `normalize`):
  1. **LevelInfo singleton actor NAME** — engine-assigned (`LevelInfo0`); a trunk
     `LevelInfo_4dosan` re-exports under the editor's name. Canonicalized to a
     sentinel (`_levelinfo_rename`).
  2. **Geometry stored as IEEE float32** — an authored `43.552099` re-exports as
     `43.552097`. Coordinates are float32-quantized for hashing (`_to_f32`);
     integers are exact.
  3. **Polygon `Normal` recomputed from winding** — authored `(0.707,0.707,0)`
     came back as the true slope `(0.541,0.541,0.643)`. Dropped from the hash (see
     "Winding defines the face" in `t3d.md`).
  4. 🔬 **Props equal to the class default are OMITTED on export** — confirmed
     across multiple props: `LightPhase=0` (Light default 0) AND `LightPeriod=32`
     (Light default 32) are both dropped, while NON-default values of the same
     props (`LightPhase=130`, `LightPeriod=24`) round-trip fine. So it is
     default-VALUE omission, not a computed field — do NOT strip these
     unconditionally. A trunk carrying a redundant default fails post-verify. NOT
     yet handled (needs class-default awareness); tracked in `board/inbox/`.
     Work around it by not storing default-valued props in the trunk.

## Pivots (`PrePivot`) — NEVER rewrite a brush's pivot
- **`PrePivot` is part of the actor→world transform, not cosmetic.** An actor's `PrePivot`
  (FVector) shifts its local origin: a brush's world vertex is
  `Location + R_Rotation·(vertex − PrePivot)`, **not** `Location + vertex`. (Confirmed by the
  select-inside spike: `actor_bounds` that omitted `PrePivot` mis-centered a brush by its
  PrePivot, e.g. Brush2228 off by 496 in Y — `spikes/2026-06-16-select-inside.md`.)
- **`Mover`s rotate about their pivot.** A door/lift keyframe rotation is taken about the
  PrePivot-defined pivot, so nudging `PrePivot` silently swings the mover through the wrong arc.
  Other consumers may depend on the exact value too (texture-lock pivoting, BSP, prefab
  placement) — treat it as **load-bearing** even when you don't know who reads it.
- **RULE: never change `PrePivot` unless that is the explicit, deliberate intent of the verb.**
  uedcli preserves it as an ordinary authored prop (it is **not** in
  `normalize.COMPUTED_PROPS`, so it round-trips and is never stripped), and every model-side
  transform must leave it byte-for-byte intact: `actor move` writes only `Location`,
  `actor rotate` writes only `Location` + `Rotation` — neither touches `PrePivot`. A transform
  that "re-centers"/"snaps"/"bakes" a pivot is a real semantic edit and must be its own opt-in
  verb, never a side effect of `clean`/`normalize`/`emit`.
- **The world transform `Location + R·(vertex − PrePivot)` is honoured everywhere** — DONE
  2026-06-19 via `rotation.actor_prepivot` + the shared `rotation.local_offset`. Measurement:
  `world_vertices`, `query.level_bounds`/`list_polys`/`list_vertices`, `preview` (render +
  `--frame`), `writes.actor_bounds` (→ `stashlib` capture), `best_grid_pivot`.
  The write side inverts it: `brush clip`/`vertex move` map a world `--at`/plane → local by
  `R⁻¹·(world − Location) + PrePivot` — **rotation-aware** (a clip normal de-rotates by `Rᵀ`, a
  `--by` delta by `R⁻¹`). Points/deltas use the TRUE matrix inverse, not `Rᵀ`: the float32 GMath `R`
  isn't perfectly orthonormal, so `Rᵀ` drifts a point by up to ~1e-3uu at ±32768 extent (a normal
  correctly stays `Rᵀ` — its exact pullback). uedcli still never *writes* `PrePivot`. **Scale
  (`MainScale`/`PostScale`) IS now applied** model-side — the world/inverse math generalizes `R` to
  the full linear part `L = PostScale·R·MainScale` (`rotation.actor_linear`; a normal stays `Lᵀ`).
  See the "Scale & sheer" section below and `architecture.md` "Scale".

## Rotation (FRotator) trig is a TABLE, not float `sin`
- **The engine renders FRotator rotations via the `GMath` integer sine lookup table, not float
  trig.** `core.dll` exports `FGlobalMath::SinTab(int)`/`CosTab(int)` + the global `GMath`; the
  table is the standard UE1 `TrigFLOAT[16384] = sin(i·2π/16384)`, **indexed `(field >> 2) & 16383`
  — the 16-bit FRotator field right-shifted by 2 with TRUNCATION (not rounding)**, `cos` using the
  same truncated index. Pinned live to ~1e-5uu via DEINTERSECTION world-geometry readout
  (`Yaw=4095` discriminates truncate→idx 1023 from round→1024; truncate matched, round was ~0.09uu
  off). Evidence: `spikes/2026-06-19-group-rotate-exact-parity.md`.
- **Consequence:** computing a rotation with float `math.sin(field/65536·2π)` differs from what the
  editor actually renders by **up to ~0.074uu** for any field that isn't a multiple of 4 (the low
  2 bits the editor truncates). It is exact only at multiples of 4. So any tool that must match the
  editor's geometry (preview, bounds, parity tests) must drive its matrices from the SAME table —
  uedcli does (`rotation.gmath_sin`/`gmath_cos`). The float32 storage of the table is the residual
  floor (~1e-5uu), so `_f32`-round the table values to match.
- A **mouse-drag** rotation can't be byte-reproduced from the stored field alone: the editor orbits
  Location with the raw free drag angle but stores the rounded integer field, so the two disagree by
  the rounding (~0.005uu). uedcli is immune — it derives Location AND `Rotation` from one integer
  field.
- **Multi-actor group-rotate ground truth (console-selected set), verified live to ≈0.005uu against
  `EDIT COPY` readback.** ✅ Driving the rotate gizmo over a *console*-selected multi-selection:
  (1) **pivot = the grid origin `(0,0,0)`**, not the bbox centre/centroid/any actor — a console
  `SELECT ALL`/`OFCLASS`/`SELECTNAME` leaves the pivot widget at the origin (a human GUI select would
  move it onto the selection, so "pivot = origin" is specifically the headless case; uedcli defines
  its own pivot regardless); (2) **Location orbits rigidly** `new = pivot + R·(Location − pivot)` with
  the same GMath-table matrices as single-actor rotation; (3) **orientation composes by naive
  per-component FRotator ADDITION, not matrix product** — a single-axis drag adds its delta into one
  FRotator field and leaves the other two, coinciding with a matrix product only when the existing
  rotation commutes with the delta axis (decisive case: yaw-delta onto existing `Pitch=4096` matched
  `R_delta·R_existing` world, differed from local). So the editor is **matrix-correct for positions but
  Euler-naive for orientations**, inheriting UE1 gimbal coupling; `MAP ROTGRID` does not snap the
  synthetic drag. (spike: `../spikes/2026-06-19-multiactor-rotate-groundtruth.md`, live 2026-06-19)

## Scale & sheer (`MainScale` / `PostScale` / `SheerRate`)
A brush actor carries two scale transforms plus a sheer. uedcli **applies** scale in its model-side
measurement, stores it in typed fields, and bakes it (`brush apply-transform`) — see `architecture.md`
"Scale" and spec in board item `scale-support-mainscale-postscale-use-store-bake`. The substrate's exact behavior is pinned
(`../spikes/2026-06-25-scale-transform-mechanics.md` ✅ live +
`../spikes/2026-06-25-mainscale-postscale-applytransform.md` 🔬 disassembled):
- **The world transform is `world = Location + PostScale·R·MainScale·(v − PrePivot)`.** `MainScale`
  is **local / pre-rotation**, `PostScale` is **world / post-rotation** (✅ verified live). So a
  non-uniform `PostScale` under a rotation **shears** the brush (`PostScale·R·PostScale⁻¹` is not a
  rotation) — UnrealEd's own rotate gizmo distorts a non-uniform-PostScale brush identically and
  silently; `MainScale` under rotation stays rigid.
- **`MAP EXPORT` emission format** (H3-critical — uedcli must reproduce byte-for-byte):
  `<Field>=( [Scale=( [X=][,Y=][,Z=] ),] [SheerRate=,] SheerAxis= )`. A `Scale` axis is written
  **iff ≠ 1.0** (identity components dropped; negatives ARE written), the whole `Scale=(…)` is
  omitted if all three are 1.0; `SheerRate=` is written **iff ≠ 0.0**; `SheerAxis=` is **always**
  present (default `SHEER_ZX`); 6-dp throughout.
- **`SheerAxis=SHEER_AB` shears axis B by axis A:** `B_new = B + k·A`, one off-diagonal term, all
  other axes unchanged (✅ all pairs). The coefficient `k = f(SheerRate)` is a deliberate GUI snap,
  **not** the raw rate (🔬 disassembled from `core.dll`, validated on a 20-point live scan):
  `f(r) = 0` for `|r|≤0.05` (deadzone); `sign(r)·(|r|−0.05)` for `0.05<|r|≤0.55`; `sign(r)·0.5` for
  `0.55<|r|≤0.65` (snap-to-0.5 notch); `sign(r)·(|r|−0.15)` for `|r|>0.65`. It lives in the coords
  math, so it governs **both** rendering and `ACTOR APPLYTRANSFORM`.
- **`ACTOR APPLYTRANSFORM` bakes all three into the verts and transforms `PrePivot` (does NOT zero
  it), keeping `Location`** — see `commands.md`. A **negative**-determinant transform (odd number of
  −1 axes, i.e. a mirror) **reverses polygon winding** (`FPoly::Transform` swaps vertex `[i]↔[N−1−i]`
  when `det(T)<0`, det including the shear term) so the baked brush stays CSG-valid.

## Selection
- **`SELECTNAME NAME=<name>` IS a live select-by-name** (🔬 corrects the earlier "impossible"
  claim — see `commands.md`). It selects exactly the named actor — point actors **and** brushes,
  including `MAP IMPORTADD` brushes that `SELECT INSIDE` can't reach — replacing the current
  selection, no-op on a missing name. **Caveat:** for IMPORTADD brushes it selects-for-read
  (`EDIT COPY` sees it) but `ACTOR DELETE` still no-ops (the missing-`Bound` quirk below); point
  actors are fully actionable. `SELECTNAME` + `ACTOR DELETE` is used by the
  **camera-rotation helper** (`dispatch._camera_rotation_helper`, wired as `level preview
  --rotate`): it places a transient `Light` carrying the desired rotation, `SELECTNAME`s it,
  `CAMERA ALIGN NAME=`s it (adopting its full FRotator), then deletes the helper for zero
  residue. The **materialize / apply path does NOT delete actors by name** — it is a full
  re-import from a clean `MAP NEW` (`materialize.py`): every point actor re-enters via `MAP
  IMPORTADD`, every brush via `EDIT PASTE` (see "How brushes enter the level" below).
- Other selection paths are by class/region/texture/matching (`edactSelectOfClass`,
  `polySelectMatchingTexture`, `edactBoxSelect`). `editobj <Name>` opens no bound window.
- **Brush selection needs full containment**, point actors select by pivot. A brush is
  INSIDE-selected only when the builder box **fully encloses** its geometry (not pivot-inside,
  the rule for Lights etc.).
- **`PF_Selected` does NOT round-trip** (selection lives on derived BSP surfaces, not the
  authored brush PolyList) — you can't ask the editor "which poly is this surface". Identify a
  poly **model-side by `(brush, index)`** via `brush poly list` + the preview viewer.

## How brushes enter the level — THE key finding
- **`ACTOR SELECT INSIDE` selects a brush only if it entered via `BRUSH ADD` or a well-formed
  `EDIT PASTE` — NOT via `MAP IMPORTADD`.** Proven by `EDIT CUT` + re-IMPORTADD of the editor's
  own canonical T3D → unselectable. Mechanism: BRUSH ADD / paste run the CSG path that computes
  the brush's `Bound`; `ULevelFactory` (IMPORTADD) doesn't, and `MAP REBUILD` doesn't recompute
  it. `SELECT ALL` *does* see IMPORTADD brushes; only the volume test skips them. ⇒ **uedcli
  adds brushes via `EDIT PASTE`, point actors via `MAP IMPORTADD`.**
- ✅ **`MAP IMPORT` (the whole-level REPLACE form) is no better than `MAP IMPORTADD` — same missing
  bound, same zero-node build.** Live 2026-07-26
  (`../spikes/2026-07-26-map-import-brush-bounds/`): one editor, three rounds over one two-brush
  fixture, differing only in the verb that introduced the brushes — `EDIT PASTE` → **16 nodes**,
  `MAP IMPORTADD` → **0**, `MAP IMPORT` → **0**. Both import forms go through the same
  `ULevelFactory`, and the replace form does not compute the bound either. **All three preserve
  actor names**, so names are not what rules the import verbs out — only the missing bound is. This
  closes the recurring "why not just import a file instead of driving the clipboard?" question:
  there is no import-shaped escape route, because the one add path that *does* compute bounds
  (`BRUSH IMPORT` + `BRUSH ADD`) renames brushes to `Brush1…BrushN`, which uedcli's name-keyed model
  cannot accept. Pinned by
  `uedcli/tests/test_engine_facts.py::test_only_edit_paste_gets_a_brush_into_csg` against the three
  real `.dx` files that probe produced.
- ⚠ **The failure is invisible to everything except a node count.** In the failed rounds both
  brushes are present in the level's own re-export, with their geometry — the actor list, the save
  and the parse all look correct. The offline tell is
  `native.umodel.parse_model_body(...).nodes == 0` on the built map's world model (the saved `.dx`
  is also ~4.4 KB smaller, being the absent BSP).
- **Identify the transient red builder brush by `Class=Brush` + inner model name `Brush` + no
  `CsgOper` — NOT by `Name=="Brush0"`.** ✅ Every real world/content brush enters via the add path
  carrying an explicit `CsgOper=CSG_Add`/`CSG_Subtract`, and the editor names authored brushes' inner
  model `Model<N>` (uedcli's own use `Model_<actorname>`). The live builder brush is the only actor
  whose `Begin Brush Name=` is the reserved unnumbered singleton `Brush`, and it never carries a
  `CsgOper`. `Brush0` is not a constant — a fresh editor numbered the builder brush `Brush1` and kept
  the counter across `MAP NEW`, and `LevelInfo` (not the builder brush) is actor 0 — so index/name
  gating fails in the common fresh-editor case. No authored brush can have inner model `Brush` **and**
  no `CsgOper`, so a false positive is impossible; this is uedcli's `is_builder_brush` predicate (and
  `actor add` skips such actors). (spikes: `../spikes/2026-06-18-builder-brush-identification.md`
  probed live 2026-06-18; robustness re-confirmed `../spikes/2026-06-23-capability-gaps-round2.md`
  live 2026-06-23)
- **An `IMPORTADD`'d brush is also skipped by CSG entirely — `MAP REBUILD` builds NO BSP from it,
  so the level stays SOLID (zero carved space).** Stronger than the selectability point above and
  the real reason `EDIT PASTE` is mandatory: a level whose subtract brush entered via `IMPORTADD`
  has **0 BSP nodes** after `REBUILD` (the same `Bound`-less brushes CSG ignores). It still `MAP
  SAVE`s — the `.dx` parses, has actors, renders its brush *wireframe* in the editor — but it has no
  built geometry. **Consequence (verified live 2026-06-28):** such a `.dx`, loaded in the actual
  Deus Ex game (`open <map>`), loads its packages + actors fine but crashes at
  **`MatchViewportsToActors` → "Failed to spawn player actor"** — because the world is solid, the
  player encroaches everywhere and `SpawnActor` returns None. The same map rebuilt through the
  `EDIT PASTE` path (`writes._re_add`) carved correctly (**68 BSP nodes**) and loaded → spawned →
  rendered in-game first try. So `EDIT PASTE` for brushes is required for a *game-loadable* map,
  not just an editor-selectable one. **And this confirms UnrealEd-2.2 (v69) map output IS
  game-compatible — the v68/v69 version gap is a red herring;** the spawn failure was 100% the
  missing CSG, not the package version. (Native BSP-node check: `umodel_parser.parse_model_serial`
  → `len(nodes)==0` is the offline tell that a build is solid/uncarved.)
- **`EDIT PASTE` drift: +32uu on ALL THREE axes** (copy has no offset). uedcli pre-subtracts 32.
  ⚠️ The compensation belongs to the PASTE, not to the geometry: a `(cx−32, …)` placement in
  editor-driving code is a cube that lands at `(cx, …)` in world space. Reading such an offset
  as authored geometry and reproducing it on a non-paste path (e.g. a native port, or
  `BRUSH IMPORT`, which does NOT drift) misplaces the brush by 32uu — this actually happened
  to the intersect/deintersect spec, see `decisions.md` 2026-07-25.
- **Emit ordering (fixed bug):** the actor's `Brush=Model'..'` reference must be emitted
  **after** the `Begin Brush…End Brush` block (the editor's own order). Before the block → the
  actor binds to an undefined model → unbound, **unselectable** brush. Omitting it entirely
  **crashes `MAP REBUILD`**.
- A brush needs valid texture vectors (`Origin`/`Normal`/`TextureU`/`TextureV`) or CSG GPFs;
  `MAP IMPORTADD` of a brush can GPF in `PrepBrush`. Point-actor IMPORTADD location is exact.

## Surfaces / polys
- 🔬 **`Masked` is a property of the TEXTURE, set at import — and a texture's flags are OR'ed into
  every surface it is applied to.** In UnrealEd's texture-import dialog `Masked` is a checkbox on the
  *imported texture object*, and it is stored on that texture's export in the package. At render time
  the engine ORs the texture's own flags into the surface's, so a texture imported as masked draws its
  **palette-index-0** pixels as see-through holes on ANY surface — **with no surface polyflag set at
  all**. Consequences, both of which cost real time:
  - **Auditing surface flags cannot find it.** A wall rendering see-through because its texture is
    masked has polys that decode to `flags: none`. An agent sent to fix "no poly carries `Masked`"
    found the premise true and the bug still present — the bug was the inverse.
  - **A masked texture is only correct where real geometry sits behind it** (a grille, a fence, a
    mover leaf, a detail brush against a wall). On a *solid* brush face it is a hole into unbuilt
    space: `CoreTexMetal.ladder_a` across the north flank of two stacked solid containers meant you
    looked straight through both into the yard. The same trap was hit independently on a second level
    (a masked lattice painted onto a solid shaft wall).
  - Corollary: **`level preview --native` is a free detector** — it renders masked faces opaque, so an
    index-0 region shows as raw magenta. Container-free and seconds, versus a `--game` render.
  *(Import-side mechanism: owner, 2026-07-26. Render-side behavior observed live in `--game` renders
  on two levels — `../spikes/levelbuild-friction/agent-reports.md`. Stored property probed and
  measured 2026-07-26 — see the next entry.)*
- ✅ **The stored property is `bMasked`, a UE1 bool on the `Texture` export, written PRESENCE-ONLY.**
  UE1 omits any property equal to its class default and `UTexture.bMasked` defaults False, so
  **present ⇒ masked, absent ⇒ not masked**; a stored `bMasked=False` never occurs. Measured across
  the 2,669-texture Deus Ex corpus: **191 carry `bMasked` (7.2 %), all True.** It decodes with the
  existing `utexture._read_props` — no new parser needed.
  **Therefore a face draws index 0 as a hole iff `poly.flags & PF_Masked (0x2)` OR its texture carries
  `bMasked`.** Both halves are load-bearing: gating on the poly flag alone misses
  `CoreTexMetal.ladder_a` (`bMasked`, 66 % of its texels index 0) painted on an unflagged solid wall —
  the ContainerYard see-through-the-containers bug, whose polys decode to `flags: none`.
  - **Index 0 is an ordinary colour on an unmasked texture, and treating it as transparent
    unconditionally is catastrophic.** **464 of 2,669** textures use index 0 while NOT carrying
    `bMasked` — including flat colour swatches (`LUM_CoreTex.White`, `.Red`, …) that are **100 %**
    index 0 and would render as nothing at all. `LUM_InfoPortraits.ArthurCallaway` is the committed
    counter-example: no `bMasked`, palette[0] = real black `(0,0,0)`, 2.2 % of texels.
  - **Reserved magenta at palette[0] does NOT mean masked.** `CoreTexMetal.ShipGrayMetal_A`,
    `CoreTexWater.dirtywater` and `MolePeople.WirePanel` all park `(255,0,255)` at index 0 and carry
    no `bMasked` — and all three use it for **0 %** of their texels. The key colour is a convention,
    not a flag.
  - **Decoder gotcha:** `TextureObj.palette_ref` is an object **ref**, not an export index — it must
    go through `export_index_of_ref` or `decode_palette` raises *"palette body not at EOF"*.
  *(`../spikes/2026-07-26-texture-masked-property/findings.md`; pinned by
  `test_engine_facts.test_utexture_bmasked_is_stored_presence_only_and_never_as_false` and
  `…test_index_zero_is_an_ordinary_colour_on_an_unmasked_texture`.)*
- **Per-poly `PolyFlags` + `Texture`/`Pan`/`TextureU/V` survive the paste path** → surface
  attributes are **model-side edits** (set poly fields → emit → paste). Verified: `flags=4`
  (Translucent) preserved through paste+rebuild.
- **Polygon `Item=` is the face's `ItemName`** — a per-face semantic label the BrushBuilders
  stamp (`Base`/`back`/`Step`/`Rise`/`Side` on a staircase, `OUTSIDE` on a generic/cube brush).
  It round-trips through T3D and drives **Surfaces → Select → Matching → Item Name** (grab all
  treads, all risers, …). `model.Polygon.item` carries it; `builders` set it.

## CSG model
- ✅ **`BRUSH FROM INTERSECTION` / `DEINTERSECTION` is `builder ∩ world`, in two phases** — decoded to
  instruction level in
  [`../spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`](../spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md)
  and ported natively as `bspcsg.rs::intersect_brushset` (uedcli `brush intersect`/`deintersect`).
  **Phase 1** clips each BUILDER face down the world tree (intersect keeps the pieces INSIDE solid,
  deintersect the pieces in EMPTY space); **Phase 2** clips each straddling WORLD face down the
  builder's convex temp BSP and appends the survivors — which is why the result inherits the
  surrounding surfaces' **texture AND PolyFlags**, and why `deintersect` reverses those caps (its
  solid is the negative of intersect's). Phase 2 is skipped entirely when the world has no BSP
  (`World->Nodes.Num != 0` guard) — the editor-UX reason you must `MAP REBUILD` before the trick
  produces a closed solid. The builder's own faces come out with `PF_NotSolid|PF_Semisolid`
  STRIPPED (LOOP-1 `NotPolyFlags = 0x28` for every oper except `CSG_Add`), so a semisolid face in
  the result can ONLY have arrived as a Phase-2 cap off a semisolid **additive** — which is exactly
  what a glass-paned mover door wants (a semisolid face still **blocks**, same collision as solid;
  only *nonsolid* is walk-through — see
  `spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` §3). The old "my mover came out
  walk-through" framing was a myth.
- ✅ **A leading `CSG_Add` into an EMPTY world does not behave like the later ones** (live-verified
  2026-07-25, `fixtures/intersect/h_leading_additive_deintersect.t3d`). UnrealEd filter-classifies
  it normally, so a subsequent overlapping `CSG_Subtract` cuts its faces away and the region reads
  as plain void. (uedcli's native core instead SEEDS a leading Add as the convex world shell — right
  for a real level's first brush, divergent here; tracked in `board/inbox/`.)

- **The CSG/BSP build mechanism is disassembled** in
  `../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` (2026-06-24, from the UED22
  DLLs). Key facts grounded there: `csgRebuild` applies brushes **in actor order** (last op on a
  region wins — confirms `MAP SENDTO`/reorder repairs); a "hole" is an `FPoly` the build
  **discarded** at `FPoly::Finalize` (<3 verts, or zero-area via `CalcNormal`/`NormalizeSlow`'s
  `1e-8` size² floor, or vertices thinned by `RemoveColinears` at ~`1e-4`); and the splitter
  `FPoly::SplitWithPlane` treats anything within a **±0.25 uu band** of a partition plane as
  coplanar — the numeric root of off-grid holes. A bad-enough degenerate poly takes the
  `Critical Error` path → CSG GPF, not just a hole.
- **More build thresholds + collision facts** (🔬 byte-verified, same two 2026-06-24 BSP spikes;
  the collision facts are from `../spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md`):
  - **Coplanar *merge* uses a finer bar than the split band:** `bspMergeCoplanars` treats two
    surfaces as the same plane within `THRESH_NORMALS_ARE_SAME = 2e-5` (distinct from the ±0.25 uu
    split band), and re-running it can collapse a face below 3 verts — a second drop point.
  - **World collision is STRUCTURAL, not per-poly:** `UModel::LineCheck`/`PointCheck` walk the BSP
    node planes and **never test `PolyFlags` solidity bits during the walk** (a full scan of all six
    collision statics found zero `PF_*` tests). Solidity is baked into the tree *shape* by CSG, not
    re-decided at trace time — which is why a semisolid/portal misuse is a structural collision trap,
    not a flag the engine re-reads.
  - **A portal brush is forced to `PF_NotSolid` at CSG parse** (`csgRebuild` `0x4a800`–`0x4a821`:
    clears `PF_Semisolid`, sets `PF_NotSolid`), so a `Semisolid+Portal` on one brush is
    engine-stripped to a nonsolid portal — `doctor`'s "semisolid+portal" finding is real.
- **Unreal's world is SOLID by default** — the key mental model. Subtractive brushes carve
  *empty* space out of infinite solid; additive brushes add solid *back* (and only matter
  where something was subtracted). Levels are built subtractively (carve rooms), not by adding
  blocks in a void.
- **The paste method == the GUI `BRUSH SUBTRACT`, proven by full-level export diff.** Same 256³
  cube via (A) `make_brush_actor(csg="subtract")`→PASTE→REBUILD vs (B) `BRUSH IMPORT`→`BRUSH
  MOVETO`→`BRUSH SUBTRACT`→REBUILD yields a **geometrically identical** `CsgOper=CSG_Subtract`
  actor. Only cosmetic diffs: our actor keeps its chosen `Name=` (vs editor auto `BrushN`), and
  (B) leaves the cube in the red builder brush. A subtract brush *is* just an actor with
  `CsgOper=CSG_Subtract`. Solidity rides `PolyFlags` (NotSolid=8 / SemiSolid=32); CSG order =
  creation order (`MAP SENDTO FIRST/LAST`).
- **`BRUSH FROM INTERSECTION` reflects subtracts, NOT free-standing additive solids.** It sets
  the builder brush to `builder ∩ remaining-solid` = box MINUS everything subtracted. An
  additive cylinder *alone* in the box yields the box unchanged (the box was already solid);
  additives only show where they refill subtracted space.
- **Clipping a SLANTED face + grid-snap → non-planar — RESOLVED by preserving fractions.**
  A clipped face stays in its source plane, but the OLD `emit`/`validate` snapped every vertex
  to the integer grid; for a *non-axis-aligned* source face (a cone's side) that pushed a
  vertex off the tilted plane and `validate_brush` rejected it (cone clip at `z=0` → vertex
  0.865 off, tol 0.5). Now `clean` preserves genuine fractions (the true cut points stay on
  their tilted plane), so cone/slant clips validate. Axis-aligned faces were always immune
  (they snap within their plane). Locked by `test_clip_cone_on_slanted_face_stays_planar…`.

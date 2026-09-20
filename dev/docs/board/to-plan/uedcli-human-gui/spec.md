# Spec — uedcli human GUI (P1: read/audit)

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** A browser GUI that shows a level from the git-tracked T3D trunk in an UnrealEd-like
four-viewport layout, lets a person navigate and inspect it, and — the point of P1 — **audit what
the AI changed**, actor by actor, with before/after comparison. No editing in P1.

**Why.** The owner wants to interleave human and AI edits on one trunk without the
`.dx`/`.unr` export→reimport round-trip, and needs full auditability of AI changes. P1 delivers the
audit half and the read/navigate surface; editing is P2.

**"Read-only" means: P1 never writes the *trunk*.** It is not disk-read-only — `serve` writes its
audit-snapshot store and its `preview_cache` under the gitignored `.uedcli/`, and the client writes a
camera-bookmarks file (below). None of these touch the trunk or any level data.

**Non-goals (P1).**

- No editing of level data (that is P2). P1 never writes the trunk.
- No git orchestration ever (owner ruling): the GUI never creates branches/worktrees and never
  merges. It *visualizes* git; the user drives git in the terminal.
- No desktop app in P1 — but the client/`serve` boundary is kept clean so a Tauri/Electron wrapper
  is later packaging work, not a rewrite.
- `actor diagram`'s and `level photo`'s server-side rasterizers are **not** replaced; they remain
  the authoritative still-image exporters. Live viewports draw client-side (below).

## Background: what already exists (reuse, do not rebuild)

- **The trunk** is the source of truth: a per-actor T3D directory tree
  (`<maps-dir>/<level>/actors/<name>/…`), git-tracked. `direction/trunk-and-editor.md`.
- **`level photo --native`** (`uedcli/preview_native.py`) already solves the trunk with the Rust
  core and renders posed stills with no editor and no container:
  1. marshal brush actors → `uedcli_native.build_geometry_bspcsg` (Rust CSG/BSP solve),
  2. `_node_polys` → per-surface world polygons joined back to source brush polys (texture/UV),
  3. `uedcli_native.bake_lighting`/`bake_radiance` (Rust lightmap bake),
  4. `uedcli_native.render_frame(polys, textures, camera, size, …)` (Rust software rasterizer) →
     RGB bytes.
- **`preview_cache.py`** caches the ~24s CSG solve (`store_geometry`) and the fully-lit scene
  (`store_scene`), keyed by content hashes, under `.uedcli/preview/`. A level whose geometry is
  unchanged reuses the solve; unchanged geometry+lights reuse the lit scene outright.
- **`actor diagram`** (`uedcli/preview.py`) is a stdlib 2D orthographic/isometric schematic
  rasterizer (Top/Front/Side + iso), PNG out.
- **Texture decode** (`utexture.py`/`utexture_decode.py`) yields `DecodedTexture` (mip0 `rgb` bytes
  + a `mask` byte-per-pixel), plus the full mip pyramid — usable as an RGBA atlas source.
- **Snapshots** exist: the `stash` register (`stash_register.py`/`stashlib.py`) stores a full trunk
  snapshot in the trunk's own per-actor T3D format, model-side, no git, under `.uedcli/stash/`.
- **Semantic-diff inputs** exist: `t3dtree`/`model` parse a trunk (or snapshot) into actors with
  properties, folders, labels, and `order_value` (CSG order, a per-actor LexoRank sidecar).

## Architecture

```
browser client  ──HTTP/WS──▶  uedcli serve  ──▶  uedcli model-side library
(camera + draw)                (all logic)        (trunk, solve, textures, diff, snapshots, git-read)
```

**`serve`** is a new verb exposing the existing library over HTTP + a WebSocket. It holds **all**
domain logic. It is read-only in P1 (never writes the trunk). It **binds localhost only** with no
auth (a local single-user tool, not a network service); multiple read-only viewers may connect
(read-only, so no arbitration needed).

**The client** owns exactly two things it must own for a real-time viewport: **camera/view state**
and **GPU/canvas drawing of a scene payload `serve` hands it**. It contains no model, diff, solve or
git logic. This split is the DRY seam (below) and the desktop-wrapper seam.

### The scene payload (one payload feeds all four viewports)

`serve` produces one **scene description** per level state, derived from the same `--native` solve
`level photo` uses (reusing `preview_cache`):

- solved world polygons: world-space vertex rings + UV frame + texture-table index + poly flags,
- baked lightmap per surface (the `render_frame` lightmap tuple),
- an actor list: name, class, bounding box, position/orientation, folder, labels, `order_value`,
- a texture atlas (from `utexture` decode: RGB + mask → RGBA).

The client draws all four viewports from this one payload:

- **3 × 2D orthographic** (Top/Front/Side) — Canvas/WebGL 2D projection of the polygons + actor
  bboxes. Smooth pan/zoom/select client-side.
- **1 × 3D perspective** — WebGL draws the textured, lightmapped polygons. Smooth fly-through.

### Rendering DRY (the owner's core concern)

The heavy, correctness-critical work — CSG solve, lighting bake, texture decode — happens once in
Rust/Python and is shared as the scene payload. The client only *draws* it. So geometry, lighting
and framing cannot diverge between the GUI and **`level photo --native`**: they come from one solve.

**The GUI is a `--native`-tier view.** `level photo` has two tiers: `--native` (Rust solve +
`render_frame`, no editor/container) and `--game` (a faithful in-game render in a headless container)
— see `direction/trunk-and-editor.md`. The GUI reuses the `--native` path, so it inherits that tier's
known gaps: overlapping-subtract geometry (doorways) can mis-render, and there is no `--game`
sky/mesh/true-lighting ground truth. The DRY guarantee is therefore against `--native`, not against
`--game`.

The residual difference from `level photo --native` is the final pixel loop (client GPU raster vs.
Rust `render_frame`). To erase even that on demand, a **"photo" action** routes through the same
`render_frame` and returns a pixel-identical `--native` still. Whether the GUI should also reach a
`--game` still for lighting judgment is deferred (it needs a container boot per shot, not real-time).

`actor diagram` stays the authoritative 2D-schematic exporter the same way.

### The audit flow (the reason P1 exists)

AI edits hit the trunk **instantly** (each uedcli verb is a discrete logged mutation — no GUI Save
involved). To audit them, a *before* state must survive the instant write:

- **Audit-snapshot store on trunk change.** `serve` watches the trunk and snapshots it on change,
  regardless of who wrote it or whether the AI ran through the GUI. This guarantees a *before* for
  any change, git present or not. The standing `safety.md` "no uedcli-side snapshot/history" rule is
  a CLI rule; the GUI is explicitly exempted for this audit store (`safety.md`, "The GUI keeps an
  audit-snapshot store"). The store is **non-git-tracked** (under the self-ignoring `.uedcli/`) and
  **highly compressed** to keep disk small, LRU-pruned to a budget. It is an editor convenience, not
  a recovery mechanism — git stays the recovery route.
- **Debounce / coalesce semantics.** A rapid burst of writes (many verbs in one AI task) coalesces
  into ONE snapshot taken after the burst settles, not one per verb — otherwise a multi-verb task
  floods the store. Consequence: the store's granularity is per-quiescent-point, not per-verb; the
  *before* of a coalesced snapshot is the trunk state at the last quiescent point before the burst.
  Auditing a single verb inside a burst is out of scope for P1 (a committer who wants per-verb
  granularity commits per verb; git then holds it).
- **File watcher → live reload.** When the trunk changes, `serve` pushes a WS event; the client
  re-fetches the scene and redraws. This is how AI changes appear live in the GUI.

  **Superseded (2026-09-14) by `dev/docs/board/to-spec/gui-explicit-rebuild-pinned-build-state-mode/
  spec.md`**: the watcher no longer auto-pushes a silent reload. A settled trunk change instead
  flips a "changes available" signal; the trunk/actor view only refreshes via an explicit **Load**
  action, and solved geometry only refreshes via a separate explicit **Rebuild** — matching
  UnrealEd's own explicit-build model rather than auto-updating. See that spec for the full design.

**Semantic diff.** Between two states (each: the live trunk, a snapshot, or — if git is present — a
commit), `serve` computes a per-actor change list:

- `added` / `removed` (an actor gained/lost),
- `prop-changed` — any actor property differs; **`moved` (a Location change) folds in here**,
- `poly-changed` — a brush's geometry or texture differs; **`retextured` folds in here**,
- `order-changed` (`order_value`), `folder-changed`, `label-changed`,
- `other` — a raw catch-all for any textual delta not classified above.

**The diff is as detailed as the git text diff.** The trunk is text, so the git/text diff is ground
truth; the semantic diff is a structured interpretation on top. Invariant: **100% of the text delta
maps to a semantic entry** (the `other` catch-all guarantees nothing is hidden).

**Derived, not stored.** The diff is computed on demand from the snapshots (which *are* stored) and
cached — it is not persisted as a separate artifact, to avoid a second source of truth that drifts
from the snapshots.

**Audit navigation.** Clicking a change auto-frames the camera to the union bounding box of the
old+new actor state (`actor bbox` gives the box). Two comparison modes:

- **onion-skin overlay** — old state translucent/wireframe in a highlight colour, new state solid
  (best for `moved`),
- **A/B flip** or split viewport (best for `retextured`/appearance).

"Next change" walks the change list, auto-framing each.

**Camera bookmarks.** Named camera poses, saved by the client in a sidecar file (editor state, not
level data). It lives **outside the watched trunk path** so writing it never trips the
snapshot/reload watcher. The GUI writes it but does not commit it; the user may git-track it by hand
if they want to share it.

### Git as an optional feature, never a dependency

Core state — trunk + snapshots — is model-side; the GUI works with no git repo. When a repo is
present, git *adds* read-only capability: browse commit history, diff against a commit (a third diff
source alongside live-trunk and snapshot), and attribute changes to a commit's author (agentic vs
human) at commit granularity. The GUI never creates branches/worktrees and never merges (owner
ruling).

## Components (P1)

| Component | New / reuse | Responsibility |
|---|---|---|
| `uedcli serve` verb + HTTP/WS app | new | expose the library read-only over the wire |
| scene endpoint | mostly reuse | trunk → scene payload; polygons/lightmaps reuse `preview_native` + `preview_cache`; the actor metadata (bbox/pose/folder/label/`order_value`) is assembled fresh — neither `preview_cache` tier holds actor metadata |
| texture atlas endpoint | new (thin) | pack `utexture`-decoded `rgb`+`mask` into an RGBA atlas (assembly is new; the decode is reuse) |
| photo endpoint | reuse | passthrough to `render_frame` for a pixel-identical `--native` still |
| semantic diff module | new | per-actor diff between two states, with the `other` catch-all |
| audit-snapshot watcher | mostly reuse | debounced/coalesced compressed snapshot on trunk change; LRU prune. Compresses the `stash`-format tree |
| git-read adapter | new (thin) | commit log, diff-vs-commit, author attribution — read-only, optional |
| browser client | new | four viewports, inspector, audit panel, camera bookmarks — draw only |

**Two genuinely new non-trivial pieces:** the semantic diff module and the client renderer. The rest
is wiring over existing code.

## Data flow

1. Client requests the scene for a level state → `serve` solves (or hits `preview_cache`) → returns
   the scene payload + atlas.
2. Client draws the four viewports; camera/selection are local.
3. Trunk changes (AI verb, or the user in the terminal) → watcher snapshots + pushes a WS reload →
   client re-fetches the scene.
4. Audit: client asks `serve` for the diff between two chosen states → renders the change list →
   click auto-frames + overlays/flips.
5. Photo: client posts a camera pose → `serve` calls `render_frame` → returns a PNG.

## Error handling

- A solve failure (bad geometry, missing texture/package) returns a structured error the client
  shows in-panel — never a bare traceback (per `CLAUDE.md`: no Python exception reaches the user).
- Missing git repo: the git-read features are simply absent; everything else works.
- A snapshot-disk-budget breach prunes oldest-first; never blocks a trunk write (P1 does not write
  anyway).

## Testing

Per the project rules, scope tests to what the change touches (`bin/test -k <module>`), full suite
once before merge. P1 test surface:

- semantic diff: fixtures of two trunk states exercising each category + the `other` catch-all;
  assert 100%-of-text-delta coverage (no unclassified change is silently dropped).
- scene payload: a small level solves to the expected polygon/actor/atlas shape; `preview_cache`
  hit/miss behaves.
- snapshot watcher: a trunk change produces exactly one debounced snapshot; LRU prune respects the
  budget.
- `serve` endpoints: read-only contract (no endpoint writes the trunk); error paths return
  structured errors, not tracebacks.

## P1 GUI — settled details

Decided with the owner (2026-09-13). These bind the P1 build.

**Stack.** Frontend: React + TypeScript + react-three-fiber (three.js) + Vite, in an isolated `web/`
dir. Backend: FastAPI + uvicorn wrapping the model-side library. (Adds a Node/Vite toolchain to the
repo — kept out of the Python package.)

**Layout.** Classic UnrealEd quad: Top / Front / Side orthographic + one Perspective, always
visible; double-click a pane to maximize/restore. Organization panel + inspector dock left; audit
change-list docks bottom.

**Camera (faithful UnrealEd 1.x drag-fly).** Perspective: LMB-drag = dolly forward/back + turn/yaw;
RMB-drag = look in place; LMB+RMB-drag = pan (up/down + strafe). Ortho: drag-pan + both-button-drag
zoom, plus modern scroll-zoom. One addition: **Alt-drag orbits** around the selection. (Verified
against the Unreal/BeyondUnreal Mouse-Control wikis; the original is mouse-only, no WASD.)

**Selection & inspector (read-only).** LMB *tap* (below the camera-fly drag threshold) selects in
any pane; Ctrl+tap multi-selects; ortho marquee; clicking an actor in the tree selects + frames it.
One selection, highlighted across all four panes + tree + inspector. The inspector shows name, class,
transform, folder, labels, `order_value`, then the full raw T3D property set (grouped, collapsible);
in audit mode changed properties show old→new inline.

**Shading & actor representation.** Full UnrealEd-like view modes per viewport: textured+lit (native
lightmap bake) / textured-unlit / flat / wireframe. Brushes draw textured+lit; non-brush actors draw
as their real meshes when the `--native` path renders them (`meshrender`), else a class-coloured
box/sprite.

**Loading & performance.** Cold open (no cache): draw the authored brush shapes as **wireframe
instantly from the trunk** (no solve), show a "solving BSP + lighting…" progress, then swap to the
solved+lit scene when the (~24 s) solve finishes. **Delivery: textures load first, then geometry**, so
solved geometry paints already-textured (no untextured→textured pop). Re-solve after a change keeps
the current scene visible with an "updating" badge and swaps when ready (no blank flicker); the solve
runs on a background worker, **latest-wins** (a newer change supersedes an in-flight solve); a
light-only change reuses the cached geometry (the `preview_cache` geometry/light hash split).

**Superseded (2026-09-14) by `dev/docs/board/to-spec/gui-explicit-rebuild-pinned-build-state-mode/
spec.md`**: no automatic background solve. Cold-open (or opening a level with no saved build) shows
wireframe from the trunk and **stays wireframe-only** until an explicit **Rebuild** — matching
UnrealEd (a level shows nothing built until you Build, ever). A level that already has a SAVED build
opens already-lit immediately (the pin is restored from the on-disk pointer at Load). "Re-solve
after a change" is also superseded: a trunk change never triggers a re-solve by itself; only an
explicit Rebuild does, against whatever the current Loaded view is. See that spec for the full
design.

**Structure & navigation.** In-GUI **level picker**, one level open at a time; switching loads that
level's scene + its snapshot history. Organization panel = a **folder tree** (primary hierarchy;
select a node → select/frame its actors) + **label filter facets** (toggle chips, OR-combined,
matching `actor find --label`) + a find box mirroring `actor find` (name/class/`--prop` + folder
globstar + label glob). "(no folder)"/"(no label)" nodes reach the unset sets (`--no-folder`/
`--no-label`).

**Audit UX.** Compare any two states via a **timeline + A/B pickers**; default before = the state just
before the latest change, after = current. The change list groups **by category** (added / removed /
prop-changed[incl. moved] / poly-changed[incl. retextured] / order / folder / label / other) with
one-click regroup by folder or flat-by-actor. Clicking a change auto-frames the union bbox of its
old+new state; next/prev walks the list. Compare visualization **auto-picks by change type**
(onion-skin for moves/geometry, A/B flip for appearance; split-screen also available), overridable
per change.

**Snapshots (the audit store; `safety.md` GUI exemption).** A **content-addressed dedup store** under
the gitignored `.uedcli/`: each actor file is a hash-keyed compressed blob; a snapshot is a manifest
`{timestamp, level, {actor-name → hash}, changed-count}`. Unchanged actors are shared across
snapshots, so many snapshots stay small. A file-watcher on the level's trunk dir takes one snapshot
per settled write-burst (debounced ~300–500 ms; a multi-verb AI task coalesces to one snapshot).
Per-level scope. **Disk-budget LRU** (configurable cap, ~500 MB default); pruning frees only blobs no
surviving snapshot references. The store carries no author claim (a working-tree write has none) and
is **independent of git** — a snapshot survives a `git reset` that discards the git history, until
LRU-pruned.

**Timeline with git.** Two lanes on one time axis — a **snapshot lane** and a **commit lane** —
cross-linked by content-hash match (a snapshot equal to a commit's tree is badged "committed as
`<sha>`"). A commit with no snapshot is still diffable (its trees are read from git on demand); a
snapshot never committed is diffable from the store. Either lane can be toggled.

**Theme & look.** Dark-first, with a light + system-follow toggle. Semantic colours — added=green,
removed=red, prop/moved=amber, poly/retextured=violet, order=teal, folder=blue, label=magenta,
other=gray; selection = bright cyan/white outline; onion-skin old = translucent desaturated ghost,
new = solid (removed tints red, added tints green). Exact shades tuned for dark+light contrast at
build.

**Keybindings.** Camera drags + Alt-orbit + scroll (above); `F` frame selected; double-click pane =
maximize; `1`–`4` = wireframe / unlit / flat / lit (focused pane); `[`/`]` prev/next change; `Space`
A/B flip; `O`/`P`/`S` onion / split / flip; `Ctrl+click` multi-select; `Esc` deselect; `/` or
`Ctrl+F` focus search.

**Grid & coordinates.** Ortho panes show an adaptive **Unreal-Units** grid; a UU coordinate readout
follows the cursor; the selected actor's location/size is shown; grid toggle.

**Not yet decided (P1, open):** empty/error/loading state details (no level open, solve failure, no
snapshots yet, no git repo, missing texture) and inspector niceties (jump to a referenced actor via
`Base`/`Owner`, texture thumbnails, copy value). Left to the plan / build-time discretion unless the
owner rules otherwise.

**Also open:** the exact rendering definition of the "flat" shading mode (listed above alongside
wireframe/unlit/lit) was never pinned down against real UnrealEd behavior — needs the same
RE-and-verify treatment as other UnrealEd facts in this codebase before Slice 2 build reaches it,
not assumed from general knowledge.

## Deferred (scope boundaries, not specified here)

- **P2 — editing.** Human edits via the model-side write path, under the standing **flock +
  refuse-same-actor-edit** rule (`safety.md`); no GUI-specific concurrency. AI edits stay instant.

  **Persistence: staged + explicit Save (ruled 2026-09-14).** A human edit is not written to the
  trunk directly. It stages into the same audit-snapshot store this spec's "Snapshots" section
  already defines (content-addressed dedup blobs + manifest, under the gitignored `.uedcli/`) — not
  the `stash` porcelain (`stash_register.py`), which stays a separate, user-facing, manually-named
  register. Save applies the staged actors into the trunk via the model-side write path. Later:
  disaster recovery from this store (e.g. the GUI crashing mid-edit) is a natural extension, not
  built now.

  **Save/Load conflict handling (ruled 2026-09-14, symmetric both directions; merge mechanic ruled
  2026-09-20).** If the trunk changed for an actor also touched by a staged edit since staging
  began, neither Save nor an explicit Load proceeds silently: both name exactly which actors changed
  underneath and require explicit user confirmation before merging — never a silent overwrite in
  either direction. The merge mechanic is **per-property, with mandatory explicit resolution
  required on a real same-property conflict** — a trunk-side change to a DIFFERENT property than the
  staged edit merges in automatically, no prompt; a trunk-side change to the SAME property blocks
  that actor's Save until the user explicitly picks staged-or-trunk (never a default/auto-pick, and
  never a blanket confirm-and-overwrite). First built by `gui-p2-actor-translate-ctrl-drag`.

  **Does not shift `direction/trunk-and-editor.md` (ruled 2026-09-20).** See
  `dev/docs/rationale/gui-editing.md` for the engineering reasoning — staging is one more writer
  reaching the same trunk write path every other verb already uses, not a change to what the trunk
  is or how it is merged.

  The atomic-chained-commands idea (a transaction verb spanning multiple mutations, all-or-nothing
  under one flock hold) stays open — see `questions/atomic-chained-verb-transaction.md`.
- **P3 — git-feature layer / heavy editing.** Only read-only git remains permitted (owner ruling);
  branch/worktree/merge orchestration is rejected. Vertex/CSG/texture-align editing lives here.

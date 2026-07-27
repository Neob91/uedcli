# uedcli docs — the whole-tree index (dev + user)

This is the **developer/agent index for the entire uedcli documentation ecosystem** — every doc,
what it's for, and which is authoritative. The **user-facing cut** (how to drive the CLI and design
levels) lives one tree over at [`../../docs/`](../../docs/README.md); by house rule that tree never
references this one, so the cross-tree routing lives **here**.

`uedcli` makes level design a **queryable, scriptable, auditable** text surface an LLM can drive
entirely as text — no GUI. The **git-tracked T3D trunk is the source of truth**; the `.dx`/`.unr`
map file is a build artifact; UnrealEd-2.2-under-wine (in the `dx-lum-uned` container) is a
**build-only** tool — `level materialize` drives it to compile the trunk into a map file. Preview
renders **in-game** (`--game`, the default) or with the **native** offline rasterizer, not in the
editor.

## Which doc is for what (read this first)

Every doc has ONE job. Don't mix them up:

| Doc | Answers | Tense / status | Mutability |
|---|---|---|---|
| **[../../docs/usage.md](../../docs/usage.md)** | "How do I use the CLI?" | current commands | tracks the CLI |
| **[../../docs/leveldesign/](../../docs/leveldesign/README.md)** | "How do I design a **good, buildable level** (with uedcli)?" | user-facing level-design craft | the curated user cut of the dev knowledge base |
| **[architecture.md](architecture.md)** | "How is it built **now**?" | what IS (implementation) | updated to match whenever the code changes — never stale |
| **[direction.md](direction.md)** | "What are we building **toward**?" | what we WANT (the compiled target) | reconciled whenever a decision lands; superseded points dropped |
| **[decisions.md](decisions.md)** | "**Why** is it this way, and what did we reject?" | the ledger of choices (UTC-timestamped) | active decisions never reworded — supersede, don't edit; fully-superseded & spike-"gate" entries may be pruned (git keeps history) |
| **[unrealed/](unrealed/README.md)** | "How does **UnrealEd** (the editor) actually behave?" | verified editor-engine facts (✅/🔬/📖) | updated as findings are verified |
| **[unrealed/t3d.md](unrealed/t3d.md)** | "What is the T3D on-the-wire text format?" | format reference (block nesting, property forms, winding, what T3D can't carry) | updated as format is verified |
| **[unrealed/texalign.md](unrealed/texalign.md)** | "What does the editor's own `POLY TEXALIGN` do to a surface's texture frame?" | per-mode formulas/guards/anchors, measured; the uedcli diff | updated if the substrate changes |
| **[unrealed/leveldesign/kb/](unrealed/leveldesign/kb/README.md)** | "What's the **comprehensive** UE1/DX level-design knowledge?" (the dev-side engine/DX reference behind the user cut) | the exhaustive compiled reference (geometry/BSP, zoning, lighting, textures, movers, actors, DX class catalog, AI, human scale, design craft) | updated as findings are verified |
| **[engine-internals/](engine-internals/README.md)** | "How does the **game runtime** behave, and how do I RE / live-debug it?" | game-DLL facts (`Render.dll`/`Engine.dll`) + RE-workflow & wine-debug **gotchas** | appended to as traps are hit |
| **[direction/](direction/README.md)** | "What are we building **toward**?" — what **the owner** decided: product intent AND process rulings | one doc per topic, **revised in place** (no history — git keeps that) | **agents may NEVER write it without their explicit yes** (`CLAUDE.md` "Direction docs") |
| **[rationale/](rationale/README.md)** | "**Why** is the code this way, and what did we reject?" — engineering decisions an agent made | one doc per module/subsystem, revised in place | agents maintain it freely; every entry carries `Rejected` + `Refs` |
| **[rules/](rules/README.md)** | "What process rule binds me *right now*?" (tests, spikes, background work) | process rules moved out of the always-loaded `CLAUDE.md` | read-on-demand; `CLAUDE.md`'s router names the moment to read each |
| **specs/** + **plans/** | "How will we design/sequence this one feature?" | ephemeral per-feature scratch | deleted once the work lands |
| **spikes/** | "What did we actually observe in this experiment?" | durable evidence | kept, cited by the docs above |
| **[board/](board/README.md)** | the work-state cluster — flow + stages (see its `README.md`) | living |  |
| **[board/inbox.md](board/inbox.md)** | "What's noticed but not yet sorted?" (head of stream — captures ideas/bugs/chores, AI flags for the owner, and their own open questions) | raw capture → triage | living |
| **[board/to-spec.md](board/to-spec.md)** · **[to-spike/](board/to-spike/)** · **[to-plan.md](board/to-plan.md)** | "What's next, by stage?" | one home per item | living |
| **[board/to-build/](board/to-build/)** | "What's reviewed & ready to build *now*?" | the on-deck **build queue / source of truth** → links a plan | living |
| **[board/done.md](board/done.md)** | "What landed recently / has deferred remnants?" | short reference tail | living |

A gap between `direction.md` (want) and `architecture.md` (is) is **expected** — it's the work
not yet done. A gap between a topic doc and the code, or between `direction.md` and the latest
decision, is a **bug** in the docs.

**Context-loading:** in a uedcli agent session only `direction.md` is auto-loaded into context;
every other doc here (incl. `architecture.md`, `decisions.md`, all `unrealed/*.md`, and all
`rules/*.md`) is **read-on-demand** — the agent must `Read` it before the task that needs it. The
router that says which doc to read when lives in [`CLAUDE.md`](../../CLAUDE.md)
("Read-on-demand docs — the router").

## Read these
- **[../../docs/usage.md](../../docs/usage.md)** — the CLI: query/mutate verbs, the `preview` viewer,
  `brush poly list`, brush clip, stash/prefab, the texture catalog (`sync`/`list`/`search`/`tags`/`classify`).
- **[../../docs/leveldesign/](../../docs/leveldesign/README.md)** — level-design craft for uedcli users: geometry/BSP,
  zoning, lighting, textures, movers, NPCs, human-scale numbers, and the Deus Ex immersive-sim design
  philosophy — mapped onto the verbs. The exhaustive engine reference behind it is the dev knowledge
  base at [`unrealed/leveldesign/kb/`](unrealed/leveldesign/kb/README.md).
- **[architecture.md](architecture.md)** — layers & modules, the
  model→validate→emit→paste write pattern, invariants (D1/D2/D6…), the git-tracked T3D trunk,
  how to add a verb, preview internals, testing, the UED22 substrate.
- **[unrealed/](unrealed/README.md)** — the hard-won, verified UnrealEd-2-under-wine
  knowledge base, split into `commands.md` (exec verbs), `quirks.md` (gotchas), `rendering.md`
  (screenshots), and `extracting-from-dll.md` (how it's mined). **Read before touching the
  driver** — the "don't relearn this" reference.
- **[dev-runtime.md](dev-runtime.md)** — how uedcli **runs** during development: the
  `bin/uedcli` / `bin/test` wrappers over the auto-managed host-native `.venv/` (which
  **requires `python3.12` on `PATH`**), the optional `uedcli-native/` Rust extension, and the
  deferred Nuitka release path. (uedcli is **not** containerised — only the editor/build
  containers it drives are.)
- **[parallel-editors.md](parallel-editors.md)** — how to drive many ephemeral
  editors at once (`docker compose run` per work item): per-run wineprefix volume, unique
  export paths, the memory-bound concurrency cap, cleanup.
- Roadmap / open work: **`board/`** — `inbox.md` (capture pool) → the stage queues
  (`to-spec`/`to-spike`/`to-plan`) → `to-build/` (the build queue); + `done.md`; start at
  **`board/README.md`**. Spike evidence: **`spikes/`** (canonical).
  Original design spec: `docs/superpowers/specs/2026-06-16-uedcli-design.md` (repo root).

## The five facts that drive everything
1. **Brushes enter the level via `EDIT PASTE`, point actors via `MAP IMPORTADD`.** Only
   paste/`BRUSH ADD` brushes are later `ACTOR SELECT INSIDE`-selectable (IMPORTADD brushes
   never are). uedcli handles the split + the +32uu paste drift automatically.
2. **All edits are model-side:** compute on the `Actor`/`Brush`, `validate_brush`, emit
   canonical T3D, materialize via paste/IMPORTADD; modify = delete-then-readd. No GUI driving.
3. **Polys are identified model-side by `(brush, index)`** (`PF_Selected` doesn't round-trip);
   `brush poly list` + `preview` map index↔face.
4. **The editor crashes often** (even idle) into a "window gone" zombie; every `wine_ctl`
   command fast-fails non-zero on a dead/crashed editor, and recovery is a container
   `--force-recreate`.
5. **Surface attributes (flags/texture/UV) survive the paste path** → they're model-side
   edits too; the CLI uses flag **names**, not bit values.

## What's built vs open (snapshot — `board/` is the source of truth)
- **Built:** query (`actor find/show/get`, `brush poly list`, `level doctor`); mutate
  (`actor add/delete/move/set/rotate`, `brush clip`, `brush vertex move`, `brush poly set`);
  generators (`actor build`, `brush build` cube/cylinder/cone/sheet/staircase/spiral/extrude/revolve);
  **movers** (`mover key count/move/rotate/remove/list`); the color `actor preview` viewer
  (quad/iso/zoom/highlight/labels/CSG-colour/point-actor sprites+markers/collision+range overlays);
  the **git-tracked T3D trunk** (`level status`/`list`,
  edited on ordinary git branches — the session store was replaced by git);
  `stash`/`prefab` capture-place-share; **`brush intersect`/`deintersect`** (the native CSG set merge);
  `level materialize` (pure build) and `level preview` (batch posed-snapshot renderer via
  `CAMERA ALIGN`); the offline texture catalog (`sync`/`list`/`search`/`tags`/`classify`);
  package stubbing (`substrate stub`); the global-CLI foundation (`project show`, two-config
  scheme); fast driver liveness.
- **Open:** the rest of the global-CLI/projects work (content-addressed caches, pipx/Nuitka
  packaging); the de-containerization roadmap (native `.dx`/texture read); the offline BSP-build
  engine (build-emergent hole detection, parked mid-spike); zones + AI pathing; camera-rotation
  READ (parse from `MAP SAVE`). See `direction.md` + the board.
- **Deferred:** level-validation text feedback; duplicate/mirror.

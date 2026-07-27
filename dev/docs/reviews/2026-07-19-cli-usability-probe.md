# uedcli CLI usability probe — 2026-07-19

**Method.** Six independent agents, each playing a veteran Deus Ex / UnrealEd 2.x
level designer on first contact with `uedcli`, drove the CLI **cold**: discovery via
`-h`/`--help` and live command runs only — **no source read, no dev-docs read** — so
the findings measure what a user can figure out from the CLI surface *alone*. Each
agent owned one slice of UnrealEd level authoring and worked in its own throwaway
`probe-*` level. Slices:

1. Level lifecycle & project
2. CSG brush geometry
3. Textures & surfaces
4. Actors & lighting
5. Movers & event/trigger wiring
6. World systems (AI-nav, sound/music, zones/portals/sky, prefabs, stash, folders)

**Overall.** The whole authoring pipeline is reachable — every agent completed most
of its goals — and the `generator → actor add -` / `find → prop set -` composition
model is genuinely liked once learned. Errors name the offending value and list valid
choices; no Python traceback ever leaked. The items below are the friction on top of a
working tool, most severe first.

---

## 🔴 1. The "selected level" is shared, unlocked, global state

Hit independently by **4 of 6 agents** (geometry, actors, movers, world) — the single
most severe finding.

`level select` writes ONE machine-local pointer in `.uedcli/`. Any concurrent `uedcli`
process flips it, and every verb that defaults to "the selected level" (`actor add`,
`find`, `status`, …) silently follows. Agent 4 created `probe-actors`, placed a
PlayerStart + 5 lights + 3 decorations, and **all of it landed in another agent's
`probe-textures` level with zero error**. Agent 6's 3 PathNodes went to the wrong
level; agent 5's door vanished (`Actor not found` on the very name `actor add` had just
reported success for).

- The only race-safe usage is `--target level/<name>` on *every* call — but that isn't
  the default, isn't signposted, and (see §2) isn't even accepted on several verbs.
- **Caveat:** the probe harness amplified this by running 6 agents at once. But it is a
  *real design property*, not a test artifact — the repo's own `CLAUDE.md` states
  "expect multiple separate agentic sessions to work on the same repos concurrently."
  Silent cross-level writes are a live hazard.
- Fix directions surfaced by agents: a `UEDCLI_LEVEL` env var (mirroring `--project`),
  a per-shell/session binding or `flock` instead of a global pointer, or at minimum a
  **warning when a mutation runs with no explicit `--target`**.

## 🔴 2. `--target` coverage is inconsistent — which breaks the escape hatch from §1

`--target` is the *only* safe workaround for the race, yet it's missing exactly where
it's needed:

| Verb | `--target`? |
|---|---|
| `actor build` (generator) | ❌ missing |
| `actor show` | ❌ missing |
| `actor move` | ❌ (single-name only) |
| `stash capture` | ❌ missing |
| `level status` / `level doctor` | ❌ — can only inspect the racy selected level |
| `event graph` | ❌ — `unrecognized arguments: --target` |
| `actor add/find/delete/prop/rotate/folder`, `brush poly`, `mover key` | ✅ |

So the two "is my level OK?" verbs (`status`, `doctor`) and the wiring inspector
(`event graph`) can *only* read the unsafe pointer.

---

## Missing commands (by area)

### Level lifecycle (agent 1; echoed by 5)
- **`level list`** — no way to enumerate your own levels *at all*. `project show` dumps
  261 packages + every base-game map but never your authored levels; a failed `level
  select` names the maps dir without listing its contents. Biggest single lifecycle gap.
- **`level delete` / `rename` / `clone`** — none exist. Throwaway levels can't be
  cleaned up or renamed in-tool; "copy this level as a start" is impossible.
- No `undo` / `save` / `commit`. Top-level help says *"Git is the history,"* but `level
  status` prints *"project is not a git repo (it lives inside the uedcli tool tree...)"*
  — the advertised recovery path is a dead end in this layout. (Worth reconciling the
  help text regardless.)
- `status` is counts-only, no `--json` (only `doctor` has it).

### AI navigation (agent 6) — the biggest world-system gap
- PathNodes place fine, but there is **no path layer whatsoever**: no `actor connect`,
  no reachspec build, no `level paths build`, and neither `materialize` nor `doctor`
  mentions paths. An NPC dropped in has no navigation network.

### Textures / surfaces (agent 3)
- **No way to SEE a texture** — no `texture show`, thumbnail, or image export; "sight"
  is name + WxH only across 4791 textures. (Directly relevant to the open
  board item `texture-catalog-redesign-superseded`.) Also 0/4791 are classified, so
  tag/color/description search is dead in practice.
- **No texture scale, no texture rotate** — two of UnrealEd's four canonical surface
  ops absent (only pan + `poly align` frames exist).

### Sound / music (agents 5, 6)
- **No sound/music catalog** — textures get `texture list/search/tags`; sounds/music
  get nothing. You must already know the exact `Package.Group.Name` — precisely the
  undocumented knowledge a designer lacks.
- ObjectProperty refs (`AmbientSound`, `Song`, `OpeningSound`, meshes) are **stored
  unvalidated** — a typo'd ref exits 0 and ships a broken level silently.

### Events (agent 5)
- `event` can *analyse* wiring (`graph`, with lint — well-liked) but **cannot author
  it**. No `event link/wire <src> <dst>`; wiring means hand-editing `Event`/`Tag`, so
  you must already know the UE1 mechanic.

### Geometry (agent 2)
- No `brush find`/`list` (must use `actor find --kind brush`); no brush-level
  intersect/deintersect (only `stash intersect/deintersect`); CSG reorder is `actor
  order`, not `brush` — the brush namespace is fragmented across `brush`/`actor`/`stash`.
- No arch / hollow / tetrahedron / sphere generators; no verb to change an existing
  brush's solidity.

### Actors (agents 4, 6)
- No `actor duplicate` (works via `show | add -`); `class show` never prints **default
  values** (the most useful fact for lighting); `actor find --class Light` is **not
  subclass-aware** → "recolor all lights" silently skips Spotlights; no `folder
  rename/move` (only `find | folder set --to`).

---

## Misunderstandings the CLI invites

- **`find | set -` looks universal but isn't.** `brush poly set` rejects `-` (`surface
  selector must be BRUSH:SELECTOR, got '-'`) while its sibling `poly align` accepts it;
  `actor move`/`actor show` take a single name while `rotate`/`delete`/`prop set` take
  sets. The core "verbs compose via stdin" philosophy has holes that trip users
  mid-pipeline.
- **`--select` reads as "this level is now mine"** — it's a global blind set, not a
  session lease (root of §1).
- **`nonsolid` (build) vs `notsolid` (poly flag)** — same concept, two spellings.
- **Rotation is degrees-in, raw-rotator-units-out** — you type `-45` and `prop get`
  reads back `Pitch=57344`.
- **`mover key add` help says "append"** but on a fresh mover the first `add` *edits*
  the pre-existing key 1 (count stays 2); looks like a lost write.
- **`--at` = geometric center on all axes** for cube/cylinder/cone/sheet, **but
  front-bottom corner for staircase** — per-shape anchor convention.
- **`--prefab-dir` goes before the subverb for `prefab`, after it for `stash promote`.**
- **`+Z` is the ceiling, `-Z` the floor** on a subtract brush.

## Help / error quality

- **Strong:** invalid-enum/flag errors name the value *and* list every valid choice;
  author-time texture-ref validation; `class show --depth all` with enum members inline;
  the `NumKeys → use 'mover key'` redirect; `event graph` lint. No Python traceback ever
  leaked. Per-shape `--help` (especially `--at`/`--rotate` semantics) is excellent.
- **Weak:** `--facing -Z` fails (`expected one argument` — argparse eats the leading
  dash; only undocumented `--facing=-Z` works); silent success on `poly
  set`/`brush clip`/`brush replace`/`prop set -` (no "changed N" summary); single-name
  verbs given multiple names bubble up the *top-level* usage block, looking like the
  whole CLI broke; upstream pipe errors flow downstream as data (`unknown brush
  'usage'`, `capture source has no actors`).

---

## Recommended priority order

1. **Fix the selected-level race (§1)** — session/env binding or a no-`--target`
   warning; and **add `--target` to `actor build/show/move`, `stash capture`, `level
   status/doctor`, `event graph` (§2)**.
2. **`level list`** (+ let failed `select` enumerate) — then `delete`/`rename`/`clone`.
3. **Make `find | *set -` uniform** — `poly set` (and `actor move/show`) should accept
   `-` like their siblings.
4. **AI path network** — connect/rebuild paths, or at minimum document what
   `materialize` does with nav.
5. **`texture show` for the LLM** (already spec'd) + a **sound/music catalog** +
   **validate ObjectProperty refs**.
6. Smaller: `class show --defaults`, subclass-aware `find --class`, texture
   scale/rotate, `event wire`, consistent mutation feedback, `nonsolid`/`notsolid`
   unification, `--facing=-Z` help note.

---

## Per-slice outcome summary

| Slice | Goals | Verdict |
|---|---|---|
| Lifecycle | create/select/status/doctor/materialize/preview | works; no list/delete/rename/clone; git-history messaging contradictory |
| CSG geometry | room/platform/doorway/stairs/pillar/spiral | all built; namespace fragmented; no arch/hollow; hit §1 race |
| Textures | catalog/apply/per-face/flags | apply+flags great; can't see textures; no scale/rotate; `poly set` no stdin |
| Actors & lighting | classes/lights/decor/find/move/bulk | works; no defaults in `class show`; `find --class` not subclass-aware; hit §1 race |
| Movers & events | door/elevator/keyframes/wiring/graph | all done; `event` read-only (no wire verb); `mover key add` "append" misleading; hit §1 race |
| World systems | nav/sound/zones/prefab/stash/folders | zones best-supported; no path layer; no sound catalog; prefab-create hidden; hit §1 race |

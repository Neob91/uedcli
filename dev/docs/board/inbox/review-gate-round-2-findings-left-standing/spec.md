# Spec: verb-first level-design guides + a human-scale measurement spike + a Claude Code skills plugin

**Status:** design (spec review gate pending — at the headcount `CLAUDE.md` **Review gates** specifies).
Ephemeral — once built, fold the durable outcomes (the rewritten guides, the spike evidence, the
plugin's existence) into the topic docs / `spikes/` and this file may be deleted.

**Binding decision (do NOT re-litigate):** `decisions.md`
**`2026-07-19 (level-design docs + AI-skills plugin) — verb-first craft guides shipped as a Claude
Code plugin`**. That entry records every choice below AND the rejected alternatives (GUI-retrofit
vs verb-first, hand-authored numbers vs a measurement spike, binary-bundled plugin vs
marketplace-from-repo, monolithic vs per-task skills). This spec designs **HOW**; for **WHY** and
the roads not taken, read that ledger entry — they are not restated here.

---

## 1. Problem

The `dev/docs/unrealed/leveldesign/` guides (`README`, `csg-and-bsp`, `lighting`, `movers`,
`textures-and-surfaces`, `zoning-occlusion-performance`) are good *craft* references but were
written from the **UnrealEd GUI operator's** seat — "commit the builder brush with *Add Special*",
"set flags in *Surface Properties*", "*Transform Permanently*". uedcli users (and the LLM driving
it) never touch that GUI; they compose **verbs** against the git-tracked T3D trunk. Three concrete
gaps surfaced while building the castle by hand:

1. **GUI-first framing.** Each guide teaches menu operations, not the uedcli verb that achieves the
   same thing. `movers.md` is the sole exception — it is already verb-first (it names `brush build
   --mover-class` and the `mover key` verbs) and is the model the others should follow.
2. **No DeusEx human-scale numbers.** Nothing tells an author how tall a corridor should be, how
   wide a doorway, how high a step, where a `PlayerStart` sits relative to the floor, or how big the
   player's collision cylinder is. Without these, an agent guesses scale and produces unplayable
   geometry.
3. **No real DX class catalog.** The guides say "place a `Light` actor" / "a `SkyZoneInfo`" but
   never enumerate the actual DeusEx classes an author reaches for, nor how to discover them.

## 2. Scope & non-goals

**In scope:** (a) a full verb-first rewrite of the five non-mover guides (+ README refresh);
(b) a measurement spike producing grounded human-scale numbers and a regenerable DX class catalog;
(c) a Claude Code skills **plugin** (in-repo layout + bundled-docs symlink; used locally via a
`skills/`→`.claude/skills/` symlink for now — marketplace distribution is **blocked on the pending
CLI-only repo move**, §6.1.1); (d) wiring `leveldesign/` into
the `CLAUDE.md` "read BEFORE X" router.

**Non-goals:** no new uedcli verbs are invented for this effort — the rewrite maps the craft onto
the verbs that **already exist** (verified below). If a craft step has no verb (e.g. grid-snap is
guidance, not an enforced operation), the guide says so plainly rather than implying a command.
No changes to the editor-driving path, the build pipeline, or the T3D format.

---

## 3. The verb surface the rewrite maps onto (verified 2026-07-19)

Every mapping below was checked against `bin/uedcli … --help` on this checkout. The composing
convention is the repo's core CLI philosophy: **generators print a T3D snippet to stdout; `actor
add -` consumes it into the trunk; per-surface edits run model-side via `brush poly`.**

| Craft task | uedcli verb(s) | UnrealEd GUI equivalent (kept as an annotation) |
|---|---|---|
| Carve/place world geometry | `brush build {cube,cylinder,cone,sheet,staircase,spiral,extrude,revolve} --csg {add,subtract} --solidity {solid,semisolid,nonsolid} --texture …` \| `actor add -` | shape the red builder brush → *Subtract*/*Add* |
| Solidity choice | `--solidity solid\|semisolid\|nonsolid` on `brush build` | *Add Special* solidity / brush flags |
| Point actors (lights, zone info, sky info, triggers) | `actor build Package.Class --prop KEY=VALUE --at X,Y,Z --rotate P,Y,R` \| `actor add -` | *Actor → Add \<Class\> Here*, then Properties |
| Lights | `actor build Engine.Light --prop LightRadius=… --prop LightType=… --prop LightEffect=…` | place a `Light`, edit its Lighting props |
| Lighting **bake** | **no standalone verb** — the lightmap bake runs *inside* `level materialize` / `level photo`; authoring lights is pure `actor` edits | GUI "Build Lighting" / F8's lighting pass |
| Movers | `brush build <shape> --mover-class <Package.Name>` \| `actor add -`, then `mover key count`/`move`/`rotate`/`remove`/`list` | *Add Mover*, record keyframes |
| Zoning | `actor build Engine.ZoneInfo --prop … ` \| `actor add -`; zone-portal sheet via `brush build sheet --flag portal` \| `actor add -` | place `ZoneInfo`; sheet brush + *Add Special → Zone Portal* |
| Water | `brush build sheet --flag portal --flag translucent` \| `actor add -` (the water surface) **plus** `actor build Engine.ZoneInfo --prop bWaterZone=True` \| `actor add -` (recipe §4.1) | translucent portal surface + `bWaterZone` ZoneInfo |
| Texturing / surface flags / alignment | `brush poly find` → `brush poly set --texture … --add-flag … --remove-flag …` ; `brush poly pan --to/--by` ; `brush poly rotate --by` ; `brush poly scale --by` ; `brush poly align --wall\|--floor\|--ring` ; `brush poly list` | select faces in *Surface Properties*, set texture/flags/pan/align |
| Skybox | `actor build Engine.SkyZoneInfo …` in a separate sky box, sky-room faces `--add-flag Unlit`, playable "sky window" faces `--add-flag FakeBackdrop` | `SkyZoneInfo` + *Fake Backdrop* surfaces |
| Grid discipline | **guidance only — no enforcement verb.** The guide states the on-grid / clean-multiple / 90°-rotation rules and notes uedcli does not snap for you | GUI grid-snap toggle |
| Class discovery | `class list` (inheritance tree; `--flat`, `--subclass-of`, `--depth`), `class show <Class>` | Actor Class Browser |

Two verb facts worth pinning for the rewrite so it doesn't overstate:
- `brush build …` emits a T3D snippet to **stdout**; it does **not** write the trunk. The write is
  always `… | actor add -`. Guides must show the full pipe, not `brush build` alone.
- `brush poly set` targets faces by `BRUSH:SELECTOR` (e.g. `Wall1:3,5` or `Wall2:all`); `brush poly
  find` prints those selectors for piping. Flags are set **by name** (`--add-flag Masked`), never by
  bit value.

---

## 4. Deliverable A — docs rewrite (verb-first, GUI-annotated)

**Shape of every rewritten guide:** verb-first prose is primary; each craft step names the uedcli
verb (with a runnable one-liner where it helps), and a short *"UnrealEd GUI equivalent: …"* note in
parentheses or a callout preserves the mental model for a GUI-aware reader. This is a reframing, not
a content cull. Human-scale numbers (from Deliverable B) are cited, never
invented; until the spike lands, a guide may reference "see the human-scale table (spike pending)".

**Retention checklist (a "full rewrite" is diffed against this keep-list, so hard-won content can't
silently drop).** Every rewritten guide MUST preserve, verbatim where they are facts:
- the **confidence markers** (✅ uedcli-used/live-verified, 🔬 live-probed, 📖 binary-extracted) on
  every UnrealEd fact — a reframed sentence keeps its marker;
- the **"Debunked" callouts** (e.g. the no-antiportals note in the zoning guide, both lighting-guide
  debunks) — these are expensive negative findings and are carried over intact;
- the **dated spike citations** (e.g. the `2026-06-24` CSG-disassembly spike, the `2026-07-15`
  lighting-bake box) — every claim keeps its evidence pointer;
- the **verbatim "Settled" surface-flag facts** — any flag name/semantics already verified in
  `textures-and-surfaces.md` is copied as-is, not paraphrased into a weaker claim.

The build-gate reviewers check the rewritten guides against this list; a missing marker, callout,
citation, or settled fact is a gate failure, not an editorial judgement call.

File-by-file:

- **`csg-and-bsp.md`** — rewrite the subtractive workflow, brush order, solidity table, and BSP-hole
  repair around `brush build … --csg/--solidity | actor add -` and `actor order` (CSG precedence is
  the trunk's `(order_value, name)` sort — `actor order --first` is the verb analog of "To First").
  Grid discipline stays as **guidance** with an explicit "uedcli does not enforce snapping" note.
  Keep the disassembly mechanism box and the `2026-06-24` spike citation.
- **`zoning-occlusion-performance.md`** — zones/portals via `actor build Engine.ZoneInfo … | actor
  add -` and a portal sheet (`brush build sheet --flag portal | actor add -`). **The water recipe
  (§4.1) is the first concrete entry in this guide.** Retain the no-antiportals Debunked callout and
  the poly-budget numbers.
- **`lighting.md`** — this guide is **already the most current** (it correctly states `MAP REBUILD`
  wipes lighting and `LIGHT APPLY` bakes, and carries the `2026-07-15` bake-mechanism box). The
  rewrite is light: reframe light *placement* as `actor build Engine.Light --prop … | actor add -`,
  and state plainly that from the uedcli seat **there is no standalone bake verb** — the lightmap
  bake happens inside `level materialize` / `level photo`, so "run `LIGHT APPLY` after retinting"
  becomes "re-`materialize`/`photo` to see lighting; authoring lights is pure `actor` edits". Keep
  the `LightType` vs `LightEffect` split, the `LE_Negative` note, and both Debunked callouts.
- **`textures-and-surfaces.md`** — surface flags, alignment, `MyLevel`, and skybox rewritten around
  `brush poly find/set/align`. Flag names map to `--add-flag`/`--remove-flag`; alignment maps to
  `brush poly align --wall|--floor|--ring` and `brush poly pan/rotate/scale`. Skybox becomes the `SkyZoneInfo` +
  `FakeBackdrop`/`Unlit` recipe using `actor build` + `brush poly set`. `MyLevel` stays described as
  editor/engine mechanism (note whether uedcli exposes an embed path or it's editor-only — **open
  question Q3**).
- **`movers.md`** — already verb-first; **touch-ups only** (confirm verb names still current after
  the rewrite, cross-link the new water/zone recipes if a mover borders a water zone). It is the
  template the others adopt.
- **`README.md`** — refresh the page blurbs to reflect verb-first framing, add the human-scale
  table + DX class-catalog pointers (Deliverable B), and keep the provenance/confidence sections.

### 4.1 The water recipe (concrete, goes in `zoning-occlusion-performance.md`)

A water volume in UE1 is a **zone** whose `ZoneInfo` has `bWaterZone=True`, with the water's top
surface being a **translucent** sheet that also acts as the **zone portal** separating the
water zone from the air zone above it. A `brush build sheet` is **already NotSolid by default**, and
its surface flags are set **at build time** with `--flag`, so the whole thing is two one-step,
already-working commands (no separate `brush poly` pass, no unknowable post-`actor add` sheet name):

```
# 1. the water surface: a portal + translucent sheet spanning the opening between air and water.
#    Sheets default to NotSolid; --flag sets the surface flags at build time, so it lands ready.
brush build sheet --width W --height H --plane xy --flag portal --flag translucent | actor add -

# 2. the water zone marker, placed inside the flooded region below the sheet
actor build Engine.ZoneInfo --prop bWaterZone=True --at <x,y,z-inside-water> | actor add -
#    (DeusEx.WaterZone is the substrate-specific alternative to a bWaterZone Engine.ZoneInfo)
```

The surface-flag **names** (`portal`, `translucent`) are known and settled (they are in
`query.py PF_NAMES`). What is not yet live-verified is the **semantics** in this specific UED22/DeusEx
build — i.e. whether a `portal`+`translucent` NotSolid sheet plus a `bWaterZone` actor actually
yields a swimmable water zone. That is a live-probe question, deferred to the build gate, not a spec
blocker — **open question Q1**. Everything else (the sheet being NotSolid, the `bWaterZone` ZoneInfo,
portal = the water surface) is settled from the existing guides.

---

## 5. Deliverable B — human-scale measurement spike

**Slug:** `dev/docs/spikes/2026-07-19-deusex-human-scale/` (harness committed alongside the
markdown, per the spikes rule — never left only in gitignored `_scratch/`).

The spike has **two halves with different data-access methods** — this split matters because there
is **no offline uedcli verb that ingests a binary `.dx` into a measurable T3D trunk**. uedcli verbs
read the *trunk* (the T3D tree), and the trunk for a shipped map only exists after an **editor `MAP
EXPORT`** produces it. So map-geometry measurement is NOT "no editor"; class-default measurement is.

**Half B1 — player/class anchors (OFFLINE, no editor).** The player collision cylinder and other
class defaults are read straight from the game's `.u` schema, no map corpus needed:
- Build a throwaway instance and read the resolved default:
  `actor build <PlayerPawnClass — e.g. DeusEx.JCDentonMale> | actor add -`, then
  `actor prop get <name> CollisionRadius` and `actor prop get <name> CollisionHeight`. An unset
  property **resolves to the class default** (the decode-offline read semantics — direction.md "One
  package-format core"), which is exactly the number we want.
- **Do NOT source numbers from `class show`** — `class show <Class>` prints property **names and
  types only, not default values**. The values come from the `actor build … | actor prop get` route
  above (or the equivalent schema-default decode), never from `class show`.
- Same route for other class-default sizes an author reaches for (human NPC cylinders, decoration
  collision extents): build the class, `actor prop get` the collision fields.

**Half B2 — architectural dimensions (REQUIRES a one-time editor `MAP EXPORT`).** Room heights/
footprints, corridor widths/heights, doorway width & height, step rise & run, ceiling clearances,
and `PlayerStart` height-above-floor are properties of shipped **map geometry**, which uedcli can
only measure once the map is a trunk:
- **Budget a one-time editor `MAP EXPORT` step** that exports a handful of shipped `DX/Maps/*.dx`
  into a **trunk corpus** under the spike dir. This is the only editor touch in the spike and it is
  explicit — the "model-side, no editor" claim is dropped for this half.
- Then measure that corpus **model-side** with `actor bbox`, `brush poly list`, and actor
  `Location`s.
- **Identification method (concrete, not "survey hundreds of brushes"):** anchor measurements to
  **named `PlayerStart`s and a small set of landmark brushes** — measure the geometry immediately
  adjacent to each PlayerStart (the floor it sits on, the corridor/room enclosing it, the nearest
  doorway) and a hand-picked few landmark brushes, rather than sweeping every brush in the map. A
  PlayerStart is a known human-scale anchor, so the geometry around it yields corridor/ceiling/
  doorway numbers with a clear provenance.

**Output:** a compact, **citable, regenerable** human-scale table (a value + how it was measured +
the source map/class) folded into `leveldesign/README.md` (and referenced from the guides). The
harness is a script under the spike dir so the numbers can be regenerated when the substrate or our
measurement code changes; per the spikes rule, land a **committed regression** that re-asserts at
least the load-bearing anchors (e.g. the player cylinder dims, an OFFLINE B1 fact) against the real
package so a violation trips a red test.

**DX class catalog:** derived from `class list` (regenerable, the source of truth) plus a curated
**top-N** of the classes an author actually reaches for (lights, ZoneInfo/SkyZoneInfo, Trigger,
common movers, decorations). The catalog documents *how to regenerate it* (`class list --flat …`)
so it can't rot into a stale hand-list — the curation is a thin editorial layer over the live tree,
not a parallel copy.

---

## 6. Deliverable C — the Claude Code skills plugin

### 6.1 Layout

```
Tools/uedcli/claude/plugins/uedcli/
  .claude-plugin/plugin.json                          # NEW — plugin manifest
  docs -> (within-repo relative symlink) ../../../dev/docs/unrealed/leveldesign/   # → Tools/uedcli/docs/… ; see §6.3
  skills/
    build-water/SKILL.md
    build-mover/SKILL.md
    zone-a-level/SKILL.md
    light-a-scene/SKILL.md
    texture-surfaces/SKILL.md
    build-skybox/SKILL.md
    grid-discipline/SKILL.md
```

- The non-hidden **`claude/`** dir under `Tools/uedcli/` groups all Claude-integration assets (today
  just this plugin). It sits **outside** the `uedcli/` Python package, so it needs **no packaging
  change** — it ships via git, never via the wheel/Nuitka binary. This **in-repo plugin layout** and
  the **bundled-docs-via-symlink** design (§6.3) are settled and unchanged; only the *distribution*
  mechanism (below) is deferred.

### 6.1.1 Distribution — UPDATED DECISION (Andrzej, 2026-07-19)

uedcli is being **moved into its own CLI-only repo**, separate from the ~3.3 GB `dx_lum` mod repo.
The **repo-as-its-own-marketplace** distribution (a `.claude-plugin/marketplace.json` at the repo
root, `/plugin marketplace add <repo-url>` → `/plugin install uedcli@<marketplace-name>`) is
**BLOCKED ON that repo move** — and the move is exactly what makes it viable: a small, clean CLI-only
repo is a fine thing to clone into the plugin cache, whereas cloning the whole 3.3 GB mod repo (the
problem the reviewers flagged) is not. So **no `marketplace.json` is created yet**, and distribution
is **blocked-on-the-repo-move**; a separate `to-spec` board item tracks that move and the marketplace
wiring that lands with it.

- **INTERIM (dev use only), until the repo move + marketplace land:** **symlink the plugin's
  `skills/` into `.claude/skills/` locally** — no marketplace, no install flow. This exercises the
  skills in-place during development while the layout and bundled docs stay exactly as specified
  above. (The `${CLAUDE_SKILL_DIR}/../../docs/…` reference of §6.2 still resolves, since the symlink
  preserves the skill's position under the plugin root.)

### 6.2 The skills (thin per-task wrappers, ~15 lines each)

Each `SKILL.md` is a **thin wrapper** — a task trigger + a short recipe that **cites the bundled
guide** for the real content, so there is **ONE source of truth** (the docs) and the skills don't
duplicate it. Proposed set (one per common authoring task):

| Skill | Task | Cites |
|---|---|---|
| `build-water` | add a water volume | zoning guide §4.1 water recipe |
| `build-mover` | add a door/lift/mover | `movers.md` |
| `zone-a-level` | seal a map into zones + portals | zoning guide |
| `light-a-scene` | place & tune lights | `lighting.md` |
| `texture-surfaces` | texture/flag/align faces | `textures-and-surfaces.md` |
| `build-skybox` | add a skybox | `textures-and-surfaces.md` (skybox) |
| `grid-discipline` | keep geometry on-grid / clean multiples | `csg-and-bsp.md` grid section |

Each names the concrete verb pipeline (from §3) and reaches its bundled guide through the skill-dir
variable Claude Code exposes: **`${CLAUDE_SKILL_DIR}/../../docs/<guide>.md`**. From a skill at
`plugins/uedcli/skills/<skill>/SKILL.md`, `${CLAUDE_SKILL_DIR}` is that skill's own dir, so `../../`
climbs to the plugin root (`plugins/uedcli/`) and `docs/<guide>.md` is the bundled guide via the
symlink (§6.3). The path **stays within the plugin root** (it never escapes to `../` above the
plugin), so it is allowed under the cache-isolation constraint, and a marketplace-installed copy
resolves it inside its own cache.

### 6.3 The cache-isolation constraint and the within-repo symlink

A marketplace-installed plugin runs from a **cached copy** of only the plugin directory, and
**cannot reference files outside the plugin dir** — a `../` path escaping the plugin root is
**blocked**. So the craft docs must physically live **inside** the plugin. To avoid a second copy of
the guides (which would immediately diverge from the canonical docs), bundle them via a
**within-repo relative symlink** at `Tools/uedcli/claude/plugins/uedcli/docs`, with target
**`../../../dev/docs/unrealed/leveldesign/`**. From the plugin dir
(`Tools/uedcli/claude/plugins/uedcli/`) that `../../../` climbs to `Tools/uedcli/`, so it resolves to
the real guides at **`Tools/uedcli/dev/docs/unrealed/leveldesign/`** — note there is **no repo-root
`docs/`**; the canonical guides live under `Tools/uedcli/docs/`. **Same-marketplace symlink targets
are dereferenced/copied into the cache** at install time (see Q2 — resolved as documented-safe), so
the installed plugin gets a real copy of the guides while the repo keeps exactly **one editable
source** (`Tools/uedcli/dev/docs/unrealed/leveldesign/`). The symlink is **relative** (never
absolute) so it resolves in every clone. **Open question Q2** (now a documented-safe assumption, not
a blocker): an optional local-clone install probe can confirm the dereference on the exact Claude
Code version in use.

### 6.4 Router wiring

Add a `leveldesign/` row to the **`CLAUDE.md` "read BEFORE X" router** (the UnrealEd navigation
section) so the guides are discoverable on demand: *"`dev/docs/unrealed/leveldesign/` — Read BEFORE
authoring level geometry/lighting/zoning/texturing: the verb-first craft guides (what makes a good,
buildable level, mapped onto uedcli verbs)."* This is the one edit this effort makes to `CLAUDE.md`.
(Not done in this spec — `CLAUDE.md` is out of scope for the spec file per the task; it lands in the
build step.)

---

## 7. Sequencing

1. **Docs rewrite (Deliverable A) + measurement spike (Deliverable B) first**, in parallel — the
   spike feeds the human-scale numbers the guides cite; the guides can be drafted with
   "spike-pending" placeholders and have the numbers slotted in when the spike lands.
2. **Skills plugin (Deliverable C) second**, built **over the now-verb-oriented docs** — the skills
   cite guides that already speak in verbs, so they stay thin. Router wiring (§6.4) lands with C.
3. **Review gates** (per `CLAUDE.md` **Review gates** — cold reviewers in parallel at the headcount it
   specifies, findings resolved before proceeding; the count is deliberately not restated here):
   - **Spec gate — now**, on THIS file, before any implementation.
   - **Build gate — later**, after the guides + spike + plugin are built, before declaring done.
   Both reviewers get the artifact cold; every finding is fixed or explicitly dismissed.

---

## 8. Open questions

- **Q1 (water recipe flag *semantics*, NOT names).** The surface-flag **names** are already known
  in code — `query.py PF_NAMES` enumerates them (`portal`, `translucent`, `fakebackdrop`, `unlit`,
  `masked`, …) — so the recipe (§4.1) uses them directly, no gap there. What is unverified is the
  **semantics** in this specific UED22/DeusEx build: does a `portal`+`translucent` NotSolid sheet
  plus a `bWaterZone` actor actually produce a swimmable water zone? That needs a live
  `photo`/`materialize` probe. It is **not a spec blocker** — defer it to the **build gate**, where
  the built recipe is exercised once and the finding folded into `textures-and-surfaces.md`.
- **Q2 (symlink dereference) — RESOLVED as documented-safe (downgraded from CRITICAL).** The Claude
  Code plugin-install behavior is that a **same-marketplace symlink target is dereferenced and copied
  into the plugin cache** (§6.3), so the bundled-docs-via-symlink design is sound as written. A
  local-clone install probe is **optional insurance**, not a gate — run it if convenient to confirm
  on the exact version in use, but it does not block the design. If a future version ever changed
  this, the fallback is a build-time copy step with a committed check that the copy matches the
  canonical guides.
- **Q3 (`MyLevel` from uedcli).** Does uedcli expose an asset-embed path equivalent to importing
  into the `MyLevel` pseudo-package, or is that editor-only? The texture guide's `MyLevel` section
  should say which — verify against the `texture` verb surface and the materialize path.
- **Q4 (spike map corpus).** Which shipped DeusEx maps form the measurement corpus, and are they
  present/readable in this checkout's asset dirs? Confirm before the spike so the numbers are
  reproducible from a known set.

---

## 9. Rationale & rejected alternatives

Not restated here. See `decisions.md`
**`2026-07-19 (level-design docs + AI-skills plugin)`** for the choices and every rejected
alternative (GUI-retrofit vs verb-first-primary; hand-authored numbers vs the measurement spike;
binary-bundled plugin / `--plugin-dir` print vs marketplace-from-repo; a separate plugin repo vs the
repo-as-its-own-marketplace; one monolithic skill vs per-task skills).

---

## 10. Compiled source knowledge (research pass, 2026-07-19)

This section captures the level-design knowledge distilled from an exhaustive crawl of external
UE1/DeusEx resources, **separated into ENGINE-GENERIC (UnrealEngine 1) vs DEUS-EX-SPECIFIC** per the
task requirement, with contradictions reconciled (several against the actual DeusEx binaries on this
box). It is the **input the Deliverable-A rewrite draws on** — the guides pull from here; the durable
facts land in `unrealed/leveldesign/*.md` during the build, not in this ephemeral spec.

> **These findings now have durable homes** (created 2026-07-19, superseding §10–§12 as the record):
> the **full** compiled reference at
> [`dev/docs/unrealed/leveldesign/kb/README.md`](../../../unrealed/leveldesign/kb/README.md) (dev,
> keeps everything incl. asset-creation/modding/GUI depth), and the **curated user subset** at
> [`../../leveldesign/`](../../../../leveldesign/) (for uedcli users). §10–§12 below are the working notes
> those were built from — the knowledge base is now authoritative. Confidence:
tutorial lore is 📖 (leads-to-confirm) unless a fact is marked 🔬 (live-probed vs the real DX package
this session) or cites our disassembly spike (strongest).

### 10.1 Sources crawled + provenance (read this before trusting a fact's scope)

| Resource | What it is | Scope |
|---|---|---|
| **Steve Tack's DX Lab** (`stevetack.com/archive/TacksDeusExLab/`, 65 pages) | THE Deus-Ex level-editing tutorial site (broken TLS → curl `--insecure`) | **DX-specific** |
| **Wolf's Tutorials** (DX Community-Update GitHub, 14 zips) | **Actually UNREAL (1998) tutorials by Tony Garcia "Wolf", patch 225f / build 220.** Engine mechanics carry to DX; **all game content (classes/packages) is Unreal's, NOT DX** | **engine-generic** (do NOT promote Wolf's package/class names to the DX catalog) |
| **tactical-ops.eu `/info/editor/`** | Large UT99/Unreal editor-tutorial mirror; strong on technique + property names, weak on prescriptive dimensions | engine-generic |
| **lodev lighting** (`lodev.org/unrealed/lighting/lighting.html`) | SINGLE page (frameset nav; no subdir) — full light-property reference | engine-generic |
| **BeyondUnreal/OldUnreal Legacy wikis + UT99 source** (unrealarchive.org mirrors, Slipyx/UT99) | Human-scale numbers + the BSP corpus | engine-generic |
| **ut99.org file id=14742** | **UNRETRIEVABLE** — JS bot-check / 403. Coverage overlaps tactical-ops, so the gap is small | — |

**Access note for future passes:** stevetack needs `curl --insecure` over http (cert is
`*.win.arvixe.com`). ut99.org downloads are gated behind a crypto-JS bot-check; the linked file
could not be fetched — if its content is wanted, Andrzej must supply the file directly.

### 10.2 Binary verifications done this session (🔬 vs the real DX packages)

Grepped the actual `DX/System/{Engine,DeusEx}.u` name tables + embedded script:

- **`LE_Negative` is ABSENT from DeusEx `Engine.u`.** The DX `ELightEffect` members are exactly:
  `LE_None, LE_TorchWaver, LE_FireWaver, LE_WateryShimmer, LE_Searchlight, LE_SlowWave, LE_FastWave,
  LE_CloudCast, LE_StaticSpot, LE_Warp, LE_Spotlight, LE_NonIncidence, LE_OmniBumpMap,
  LE_Interference, LE_Cylinder, LE_Unused` (16). DX **lacks** UT99's `LE_Shock/LE_Disco/LE_Shell/
  LE_Rotor` (DX is an earlier engine build). ⇒ **`lighting.md`'s "`LE_Negative` subtracts light
  (Settled; verified)" is a live DOC BUG** — there is no stock negative-light effect in this build.
- **DX `ELightType` DOES include `LT_Pulse`/`LT_Blink`** (embedded enum source) — our LT_ list is
  correct: `LT_None/Steady/Pulse/Blink/Flicker/Strobe/BackdropLight/SubtlePulse/TexturePaletteOnce/
  TexturePaletteLoop`.
- **DX class catalog CONFIRMED present in `DeusEx.u`:** `DeusExMover, BreakableGlass, BreakableWall,
  ElevatorMover, WaterZone, Keypad1/2/3, HackableDevices, SecurityCamera, AutoTurret, AlarmUnit,
  NanoKey, ScriptedPawn, DataLinkTrigger, AllianceTrigger, PatrolPoint, DeusExLevelInfo,
  ComputerSecurity, ComputerPersonal, ComputerPublic, DamageTrigger, InterpolationPoint,
  DeusExDecoration, DeusExPickup`. **`LavaZone`/`PainZone` are NOT DX classes** (UT-only) — DX does
  pain via `ZoneInfo bPainZone`.
- These are the seeds of the spike's committed engine-facts regression (§5): assert `LE_Negative`
  absent + the DX enum membership + the class-catalog presence against the real package.

### 10.3 Corrections to apply to the EXISTING guides during the rewrite

The rewrite (Deliverable A) MUST fold these in — they are errors or imprecisions in the current
guides, now reconciled:

1. **`lighting.md`: drop `LE_Negative`.** Binary-verified absent from DX. Replace the "negative
   light to carve shadow" advice with: there is **no stock negative-light `LightEffect` in this
   engine build**; darken by placing fewer/less-bright lights or lowering zone `AmbientBrightness`.
   Keep the render-time-attenuation mechanism box. (`LE_Negative` is a UT2004-era value.)
2. **`csg-and-bsp.md` / `zoning-…md`: fix "a brush touching a zone portal must be solid."** Precise
   truth (corroborated by Steve Tack, Wolf, tactical-ops): the **portal SHEET is NON-SOLID**; it is
   the **zone-BOUNDARY geometry that must be solid**, and a **semisolid abutting a boundary/portal**
   is the real BSP-wrecker. Reword to that.
3. **`zoning-…md`: poly budget.** Epic's rule is "**never >150 polys in view**" (the hard ceiling);
   present our "150–400" as a looser stretch range, 150 as the safe ceiling. **Add the new hard
   limits: max 64 zones/map; zone see-through depth 3.**
4. **`movers.md`: engine base classes vs DX.** The engine mover subclasses are `Mover, RotatingMover,
   LoopMover, AttachMover, ElevatorMover, GradualMover, MixMover, AssertMover`; **DeusEx uses its own
   `DeusExMover` family instead** (`BreakableGlass/BreakableWall/ElevatorMover/CEDoor`). Add the
   **keyframe "inverted record" trap** (author at key 0; select the *target* key first, then move;
   `NumKeys` must equal the count) and the **mover self-lighting "black door"** fix
   (`bDynamicLightMover`/`WorldRaytraceKey`/Unlit rings). Keep return-group AND `MoverEncroachType`
   as **distinct** (don't conflate).
5. **`textures-and-surfaces.md`:** `Fake Backdrop` needs an **`Unlit` companion** on the displaying
   surface; `Masked` = palette **index 0**; `Translucent` masks DARK, `Modulated` masks LIGHT;
   `Mirror` is a surface flag (`Mirror`+`Unlit`), editor-invisible, NOT a portal. **MyLevel:** an
   imported texture is **discarded on rebuild unless applied to a surface first**; screenshot
   texture must be named exactly `ScreenShot`, mipmaps off. Enumerate the **Add Special presets**
   (Transparent Window / Masked Decoration / Invisible Collision Hull / Zone Portal / Water /
   Semi-Solid Pillar). Note **sheets never collide** — block with an Invisible Collision Hull or a
   1-unit cube, and **collision hulls / masked brushes must not touch geometry** (→ HOM).
6. **Cross-cutting doc note (validates our architecture):** UnrealEd's **brush `.u3d` Save/Load is
   broken — Export/Import `.t3d` is the reliable path** (Wolf T1). This is worth a one-line callout
   because it independently validates uedcli's git-tracked-T3D-trunk design.
7. **Hue-wheel values** differ between tutorials (Steve Tack R0/O20/Y40/G80/C120/B160/P200; Wolf
   R0/O25/Y50/G60/B150/P190) — the wheel is continuous byte 0–255; present values as **approximate**,
   not canonical. Reminder: `LightSaturation` is **inverted** (255 = white/no tint; lower = more
   saturated).

### 10.4 Human-scale numbers (feeds §5 spike + the guides)

Reconciled; **ENGINE-GENERIC unless marked DX**. The single cross-confirmation worth stressing:
Steve Tack's DX "**16 units = 1 foot**" and the Legacy-wiki "1 ft = 16 uu" AGREE — it is an engine
convention DX inherits and authors think in explicitly.

| Quantity | Value | Source | Scope |
|---|---|---|---|
| Unit scale | 1 uu = 0.75 in; **1 ft = 16 uu**; 1 m = 52.5 uu; 256 uu = 16 ft | Legacy:General_Scale; Steve Tack | generic (DX explicit) |
| Max world | 65536 uu (2¹⁶) / axis | Legacy:General_Scale | generic |
| **Player collision cylinder — DX 🔬** | JC Denton **Radius 20 (40 wide) × Height 47.5 (95 tall)**, Mass 150; MJ12Troop identical | uedcli `actor prop get` (decoded from `DeusEx.u`) | **DX** (UT99 pawn was 17×39) |
| **Player eye height — DX 🔬** | `BaseEyeHeight=40` above center → **~87 uu above floor** | uedcli decode | **DX** (UT99 was 27→~66) |
| **Jump / speed / step — DX 🔬** | `JumpZ=300`, `GroundSpeed=320`, `WaterSpeed=300`, **`MaxStepHeight=25`**, `AccelRate=1000` | uedcli decode | **DX** (UT99 JumpZ was 325) |
| Stair rise (recommended) | **16** uu | Legacy:Making_Stairs; Steve Tack | generic + DX |
| Stair run | 16 steep / **32 good** / 48–64 stately | Legacy:Making_Stairs | generic |
| Ceiling height | min **83**, recommended **128** | Legacy:General_Scale | generic |
| Corridor width | min **48** | Legacy:General_Scale | generic |
| Doorway | ~**128 tall × 64 wide**; DX doors **144×72 or 128×64**, 1–8 thick | Legacy; Steve Tack | generic + DX |
| Duck passage | 52 w × 66 t (⚠ UT99 has no crouch; applies to DX/duck-capable) | Legacy:General_Scale | DX-relevant |
| Grid | power-of-two; **16 = default = 1 ft = default stair rise**; 8/4/2 for detail | Wolf, Steve Tack, Legacy | generic |
| Default `LightBrightness` | **64** (≈⅓ of reach) | tactical-ops | generic |
| `LightRadius` → world | ≈ **(LightRadius+1)×25 uu** | our spike + lodev | generic |
| Poly budget | Epic hard **≤150 in view** (looser 150–400 stretch) | tactical-ops | generic |
| Zones | **max 64/map; see-through depth 3** | tactical-ops advanced_portals | generic |
| Mover keyframes | max **8** (0–7) | Wolf, Steve Tack | generic |
| Mesh surfaces | max **8** | Steve Tack | generic (mesh fmt) |
| Texture size | pow2, **max 256** renderable (512+ won't render) | Wolf, Steve Tack | generic |
| DX device strengths | lock 10% / hack 20% / door 25% / turret 50% / wall 40% | Steve Tack | DX |
| DX camera FOV | 65536=360°, default 4096=22.5°; swing 8192=45° | Steve Tack | DX |
| **PlayerStart height above floor** | **40 uu** | Legacy:PlayerStart | generic |
| **PathNode spacing** | **300–700 uu** (≤300–350 on ramps/stairs; ≥50 min or "paths too close" error; ≥50 from corners); DX: **<700 uu, <350 on stairs** | Legacy:Bot_Pathing; DX SDK | generic + DX |
| Corona `DrawScale` | 0.1–0.3 | Legacy:Corona | generic |

**Spike (§5) impact:** **B1 (offline class-defaults) is effectively DONE inline — uedcli already
decodes class defaults**, so the DX-authoritative numbers above were read directly with no editor and
no separate spike, via `actor build <Class> | actor add - | actor prop get - <Prop>` (an unset
property resolves to its class default — `direction.md` "One package-format core"; verified
2026-07-19 against `DeusEx.u`). The spike's B1 half therefore collapses to "run these reads and pin a
regression"; **only B2 (shipped map-geometry corpus, needing a one-time editor `MAP EXPORT`)** remains
genuinely editor-bound. Concretely, `class show` prints names/types only — the **values come from
`actor prop get` on a built instance** (as spec'd). Quick-reference DX defaults decoded this session:
JC Denton cylinder 20×47.5 / eye 40 / JumpZ 300 / MaxStepHeight 25; MJ12Troop cylinder 20×47.5,
maxRange 1000, BaseAccuracy 0.2, Health 100; `Engine.Light` LightRadius 64 / Brightness 64 / Hue 0 /
Saturation 255 / LT_Steady / LE_None; `ParticleGenerator` frequency 1 / checkTime 0.1 / lifeSpan 4 /
riseRate 10 / drawScale 0.1; `SecurityCamera` cameraFOV 4096 (22.5°) / cameraRange 1024 / swingAngle
8192 (45°); NanoKey cylinder 2.05×3.11.

### 10.5 DEUS-EX-SPECIFIC facts (the engine-vs-DX separation)

Everything here is DX and does NOT apply to raw UnrealEngine 1. (Full detail in the research
findings; the guides cite the ones an author reaches for.)

- **Scale convention** `16 uu = 1 ft` (above) — DX authors size doors/steps/panels in it.
- **`DeusExMover` family** (NOT engine `Mover`): `bIsDoor, bLocked, bOneWay, lockStrength,
  bPickable, doorStrength, bBreakable, KeyIDNeeded`; subclasses `BreakableGlass` (1u translucent),
  `BreakableWall` (doorStrength 40%→lower for crowbar), `ElevatorMover`, Carone `CEDoor`.
- **Ladders are TEXTURE-DRIVEN** — any texture whose **Group name is `Ladder`** is climbable
  (`ladder_a`, `LadrBrwnMetal` in `CoreTexMetal`), no actor/flag. ⇒ **supersedes this spec's earlier
  tentative `bIsLadder`/LadderZone assumption** — correct it wherever it appears.
- **Water** = `WaterZone` (= `ZoneInfo` `bWaterZone=True`) — confirms §4.1. **Pain** = `ZoneInfo
  bPainZone`+`DamagePerSec`+`DamageType` (DX has no `PainZone` class).
- **`HackableDevices`** base (`bHackable`, `hackStrength`): `Keypad1/2/3`, `SecurityCamera`,
  `AlarmUnit`, `AutoTurret`/`AutoTurretSmall` (place these, not the `…Gun` variants; fixed 50% hack).
- **`ScriptedPawn` + alliances** (`InitialAlliances[0..7]` = name/level −1|0|1/permanent; player =
  "Player"; `AllianceTrigger` flips; `PatrolPoint` chains + `Orders=Patrolling`).
- **Conversations:** external **ConEdit**; `ucc make` → `Pkg.u`+`PkgText.u`+`PkgAudioMissionNN.u`;
  owner = character **BindName**; in-game "InfoLink" = class **`DataLinkTrigger`**; `DeusExLevelInfo`
  `missionNumber` 16–97.
- **Computers** (`ComputerSecurity/Personal/Public`), 8 accounts, `ComputerNode` logo (15 fixed
  values), `lockoutDelay` 60s; **`titleString`/`titleTexture`/`nodeName` documented but never
  implemented** in stock code.
- **Info devices / DataCubes** (text → player Notes; markup `<P>/<COMMENT>/<DC=r,g,b>/<JC>`),
  **DataVault images** (400→512 pad→4×256, MIPS off).
- **Custom-content pipeline:** packages under `\DeusEx\<Pkg>\Classes`, `EditPackages=`, `ucc make`;
  **meshes ≤8 surfaces**, `MESHMAP SCALE` 1 (MilkShape) or 1/256 (DX), byte-angle rotations;
  **textures pow2 ≤256**, `#exec TEXTURE IMPORT … FLAGS=` (Masked 2/Transparent 4/Env 16/Modulated
  64/FakeBackdrop 128/TwoSided 256/…); sounds 16-bit/22k/mono; **music tracker `.umx`, 6 dynamic
  patterns, 256 lines freezes UnrealEd**; augs via `AugmentationCannister→AddAugs` (standard pairs).
- **Map linking:** `Teleporter URL="Map#Tag"`; maps `.dx`, mission-number-prefixed, **matching
  mission numbers both sides** or state won't persist.
- **UT content to EXCLUDE (not DX):** DM-/CTF-/DOM-/AS- gametypes, UT bot-AI path heuristics,
  UT `Water/Lava/Slime` ZoneInfo subclasses, and every Wolf/UT package name (NaliFX, GenIn,
  DoorsMod, …). The **engine mechanism** transfers; the **content** does not.

### 10.6 BSP problems & how to avoid them — DEEP (per Andrzej's emphasis)

This is the load-bearing craft topic and the most myth-ridden. It is **engine-generic** (the code is
the UT `UnFPoly.cpp`/`UnBsp.cpp` lineage that DeusEx shares — see the disassembly spike
`spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`). Distilled from ~40 community sources and
**reconciled against that spike**, which is the ground truth wherever they disagree. The rewrite
should carry this depth into `csg-and-bsp.md` (with the confidence markers preserved).

**The one meta-finding that reframes everything:** the community reliably gets the *fixes* right and
the *mechanism* wrong. The dominant folk explanation — "off-grid geometry causes a **floating-point
overflow** and the engine gives up on the maths" — is **FALSE**. No value exceeds the double range.
The true cause is a small set of **discrete numeric validity tests with specific tolerance bands**;
off-grid coordinates land *inside* those bands, so faces get **mis-classified as coplanar**,
**collapsed below 3 vertices**, or **rejected as zero-area** — and a rejected `FPoly` *is* the hole.

**Problem catalog (community view → true mechanism):**
- **BSP hole** — a missing/see-through world face (or a `Black Space` triangle at a brush
  confluence), which in solid space can also **kill the player**. True cause: an `FPoly` discarded by
  `FPoly::Finalize` (`NumVertices < 3` → "Not enough vertices"; ~zero area → "Zero-area polygon"; a
  bad-enough one throws a **Critical Error** crash), usually because `RemoveColinears` collapsed
  vertices that drifted **< ~1e-4 uu** apart / near-colinear, or `SplitWithPlane`'s **±0.25 uu**
  band mis-handled an almost-aligned plane (slivers + T-junctions).
- **HOM (Hall of Mirrors)** — a *rendering* symptom (un-cleared framebuffer). **Three causes, only
  one is BSP:** (1) a BSP hole exposing the void; (2) a transparent/masked/invisible texture with
  nothing behind it; (3) too-short distance fog with no skybox. A **solid** brush's discarded face →
  HOM; a **semisolid**'s → an *invisible polygon* instead (it doesn't occlude).
- **Leak** — two intended zones merge (e.g. "whole level full of water"). Cause: portals not
  watertight, OR a hole *on a portal face* (the same `FPoly` mechanism applied to the portal).
  Diagnose in **Zone/Portal view**.
- **Non-planar poly / "invalid brush"** — pulling one vertex of a quad off its plane, or two
  coincident verts. **Cleanest community↔disassembly match:** mappers observed the exact crash
  string `FPoly::Finalize<-FPoly: Not enough Vertices (0)`. An `FPoly` carries ONE plane; an
  off-plane vertex makes classification and rendering diverge (cracks/HOM) or collapses the face.
- **Coplanar flicker / z-fight** — two surfaces in the same plane. The famous **"1-unit gap"** fix
  (lift a nonsolid sheet ≥1 uu off the floor) **works precisely because 1 uu > the 0.25 uu split
  band**, pushing the planes into distinct nodes. (`No Bound Rejection` flag = a render band-aid, not
  a geometry fix.)
- **Node/poly explosion** — every brush face is a partitioning plane; an off-grid/awkward face
  becomes a global **"Supercut"** that splits many faces AND seeds float error into every
  interpolated vertex. Node:poly ~1.5–2:1 good, >3 warning; **hard ceiling ≈ 65536 nodes → UnrealEd
  crashes** (stock UE1/DeusEx; the OldUnreal **227j** patch raises this — **do NOT design DX maps to
  227j limits**).
- **Invisible poly / Zone-0 face** — the zone flood-fill put a poly (usually a semisolid) in a
  non-visible zone. `PF_ForceViewZone` forces render but can leave it unlit — **symptomatic only**.

**Prevention — Tier A (verified mechanism; community fix AND disassembly agree):**
1. **Grid discipline / integer on-grid coords / powers of two** (think 2-4-8-…-256; prefer 96/112/128
   over 100). Off-grid signature to hunt: coords reading **`15.999976`** where `16` belongs. *Why:*
   exact plane coincidence → exact splits, nothing in the 1e-4 collapse or 0.25 split bands.
2. **Rotate SOLID (world-cutting) brushes only in 90° increments.** An arbitrarily-rotated solid
   throws off-grid planes that partition the whole world BSP. *Corrects a common over-claim:*
   Transform Permanently does **not** rescue a 45°-rotated solid — the coords stay irrational.
   (Semisolid/nonsolid/decoration brushes may be rotated to ANY angle — they don't partition the
   world BSP, so their off-grid planes cut only themselves; a rotated box as a semisolid is fine.)
3. **Keep every face planar & convex; never two coincident verts** (crashes Finalize).
4. **Coplanar surfaces: exactly coplanar (then Merge) or cleanly ≥1 uu apart** — never in-plane.
5. **Brush order: subtractive/structural To First; additive/semisolid/nonsolid/mover To Last**
   (last op wins — matches the actor-order rebuild loop).
6. **Push off-grid/curved/detail geometry to SEMISOLID** — it receives cuts but emits no
   world-splitting planes, localising instability and cutting node count. *Constraint:* a semisolid
   must **not touch another semisolid, a nonsolid, or a zone portal**.

**Prevention — Tier B (real fix, folklore "why"):** Transform Permanently after any rotate/scale/
vertex-edit (real win = baked snappable coords, NOT "less runtime maths"); keep node count low
(real lever; "engine gives up at high node count" is folklore — the link is more-splits→more-error);
rebuild at Optimal (runs `bspMergeCoplanars`; "always 3×" is cargo-cult); avoid high-facet
cylinders/spheres; avoid tiny/thin sub-grid brushes; use the build sliders (Minimise Cuts↔Balance,
default 15/100) as a last-resort re-partition.

**Repair (existing hole/HOM) + why:** rebuild Geometry+BSP at Optimal **with Build Visibility Zones
ON** (building BSP without it erases zones); **locate via Zone/Portal view** or a fog detector
(`set PlayerPawn ConstantGlowFog (X=0.3)` — HOM spots turn solid red) or "show paths" (paths won't
form over bad BSP); **snap to grid via console `ACTOR ALIGN`** then Transform Permanently; **reorder**
(To First/Last); **nudge** the culprit; **hand-rebuild the face — select surrounding verts CLOCKWISE
→ Create** (clockwise = correct winding; counter-clockwise = inverted face; random order → Critical
Error); **Merge coplanars**; **1-unit gap** for a coplanar sheet; **convert to semisolid**; **zone
the area off**; backups as the last resort.

**Contradictions between sources — verdicts:**
- "Always intersect/deintersect brushes that meet" → **REJECT**: on-grid brushes join exactly with no
  intersect; intersect makes complex multi-face brushes = MORE splits/error. Use intersect only to
  fabricate a mover shape.
- "Overlapping brushes cause holes" → **FALSE** (explicitly, in multiple UE1 sources): volumetric
  overlap is fine (last-op-wins); only **coplanar-coincident** and **off-grid** geometry cause holes.
- "Brush sinking (add a face coplanar with a subtract to trim it)" → **works only inside the 0.25 uu
  band; fragile** (HOM/collision when it drifts). Prefer surface-flag trim or a real detail brush.
- "Semisolids must touch a subtract" (Red_Fist) → that's **UT2004/UE2** advice; in UE1 keep them
  clear of solids/subtracts/portals.
- "Use semisolids only where players can't reach" → **myth**: semisolids have **full, reliable
  collision and ARE walkable** — you can build floors/ramps from them. Their only special trait is
  that they don't CUT the world BSP, which is exactly why heavy *decorative/detail* use is correct
  and lowers node count.

**Myths to REJECT (with correction):**
1. **"Floating-point overflow / the engine gives up on the maths."** → discrete tolerance bands
   (0.25 uu split, <1e-4 colinear, <3-verts/zero-area). Rule right, reason wrong.
2. **"High node count itself causes holes."** → correlation via shared cause (more off-grid splits →
   more error). The only hard node effect is the **65536 crash**.
3. **Static-mesh round-trip repair** → **UE2+**, unavailable in UE1/DeusEx.
4. **Antiportals / antiportal occlusion** → **UE2+**; in UE1 "portal" = zone portal only.
5. **The "Basic Level Design BSP (Unreal Tournament)" nerivec/michaeljcole wiki page** is actually
   **UE4** content ("Geometry mode", "Details panel", clip tool) — the *concepts* carry back, the
   *tools/UI do not exist in UE1*. Do not cite its UI steps.
6. **227j node/bounds limits** → OldUnreal patch-specific; stock DeusEx keeps 65536.

**Committed regression (per the spikes rule):** the load-bearing engine-facts above that are already
pinned by our disassembly are re-asserted by the `2026-06-24` spike's evidence; the rewrite should
back-reference it, and the human-scale/enum facts get their own asserted regression in the
measurement spike (§5). Sources for the BSP corpus: OldUnreal wiki (`BSP_building`,
`Vertex_Editing_Tutorial`, `Mapping_Tips`, `BSP_surface_flags`) + forums ("Notes on BSP Cuts"),
BeyondUnreal Legacy (`BSP_Hole`, `Hall_Of_Mirrors`, `Semisolid`, `Node_Count`, `Brush_Order`,
`Transform_Permanently`, `Brush_Sinking`), tactical-ops (BB Drac `ued_tutbsp`, `common_probs`),
UT99.org forums. Non-UE1/version-mismatched pages flagged above.

### 10.7 Contradictions surfaced that needed NO user decision (all reconciled)

`LE_Negative` (settled by the binary), "portals need solid" (solidity model + 3 sources), poly
budget (150 ceiling vs 150–400 range), hue-wheel values (approximate continuous wheel), mover
return-group vs `MoverEncroachType` (both real, distinct), and the "floating-point overflow" BSP myth
(disassembly ground truth). **No contradiction remained unresolvable — nothing is pending an
Andrzej decision from this research pass.** The one thing NOT settled here is Q1 (§8) — the *live
behavior* of the water recipe — which was always a build-gate probe, not a docs-research question.

---

## 11. Gap-fill research pass (2026-07-19, "anything we don't know yet?")

A second pass targeting the topics thin in §10: advanced brush geometry, the **non-geometry actor
layer** (collision/physics/decorations/effects/pathing), and DX-only features beyond Steve Tack. DX
class claims below are **🔬 verified present in the pristine `DeusEx.u`** this session. Same
confidence caveat: tutorial/source lore is 📖 (leads-to-confirm) unless binary-verified.

### 11.1 Advanced brush geometry & the shape toolchain (ENGINE-GENERIC)

- **Native brush builders (right-click the toolbar button for params; numeric fields accept `=`
  math expressions like `=64+128`; builders remember params for the session).** The set and their
  key params — these map directly onto uedcli's `brush build {cube,cylinder,cone,sheet,staircase,
  spiral}` verbs, so the rewrite can name the real UnrealEd params:
  - `CubeBuilder`: Height/Width/Breadth, WallThickness, Hollow, Tessellated (default 256³).
  - `CylinderBuilder`: Height, OuterRadius, InnerRadius, Sides, AlignToSide, Hollow (default 8 sides,
    h256, r512). **Engine caps a single poly at 16 sides.**
  - `ConeBuilder`: actually a **pyramid/frustum** (Height, CapHeight, Outer/InnerRadius, Sides).
  - `TetrahedronBuilder`: the "Sphere" button — `SphereExtrapolation` (subdivision; **max ~5**).
  - `SheetBuilder`: one flat poly (zone portals, water surfaces, banners).
  - `VolumetricBuilder`: a **star of sheets** for torches/flame/volumetric FX.
  - `LinearStairBuilder`: StepHeight/StepWidth/NumSteps/AddToFirstStep.
  - `CurvedStairBuilder`: InnerRadius, StepHeight ("**do not set over 32**"), StepWidth,
    AngleOfCurve, NumSteps, CounterClockwise.
  - `SpiralStairBuilder`: InnerRadius, StepWidth/Height/Thickness, NumStepsPerPiece, NumSteps,
    SlopedCeiling/SlopedFloor. **Native spiral-stair brushes CANNOT be subtracted** (known limit).
  - `TerrainBuilder`: a tessellated cube (WidthSegments/DepthSegments) → vertex-edit into terrain.
- **Tarquin's Extended Brush Builders** (third-party `.u` add-ons; install edits
  `[UnrealEd.EditorEngine]` builder entries): mk2 Cylinder (partial revolutions / wedges via
  `SidesUsed`), mk2 Spiral/Curved Stair (**can be subtracted**, fixes sloped variants; Top/Bottom
  Style Flat/Sloped/Stepped), mk2 Torus (Outer/Tube radius, Wheel/Tube sides; drops polys above
  16×16), mk2 Panorama (a ring of sheets for skybox backdrops/waterfalls), Parallelepiped, Wave
  (sine-grid terrain), and the **Extruder** (sweep a 2D profile along a `PathPoints[]` list —
  absolute or relative — for pipes/curved tubes; auto-caps unless the path is a closed loop).
- **Brush Clipping tool:** place clip markers with **Ctrl+RMB in a 2D view** (2 markers = planar
  cut; 3rd = compound 3D cut); **Clip** discards the side facing the normal, **Split** keeps both
  halves as separate brushes; **Flip Clipping Normal** reverses. Transform-Permanent the brush first.
- **Curved geometry:** curved corridors via 2D-editor **Revolve** (move the green pivot away from the
  cross-section; 16 pieces = 360°, `Use`=4 → 90° bend); curved arches via 2D-editor **Bézier**
  segments on a traced BMP; the **iris doorway** = 8 quarter/eighth-segment movers all keyed to one
  `Event`. Vertex-edited curves need a **rebuild BEFORE editing** (moves won't take otherwise) and
  destroy surface alignment (re-align after).
- **UE1 terrain is 100% brush-based — there is NO heightmap `TerrainInfo` actor (that is UE2).**
  Sculpt via `TerrainBuilder`+vertex editing, an external tool (TerrainED → UnrealText/.t3d import),
  or iterative **intersect-before-add** rock CSG. Outdoor philosophy: keep ≤150 polys in view; block
  sightlines with terrain so total polys can be high but never all visible.
- **MeshMaker** (external): converts a brush/prefab `.t3d` into a **mesh `Decoration`** — meshes
  render more faces cheaply, have **no BSP holes**, and can be pushable/destructible/rotating, at the
  cost of **≤8 textures, no tiling, cylinder-only collision**. The fix for ugly faceted brush pillars.

### 11.2 The non-geometry actor layer (ENGINE-GENERIC; DX subclasses flagged)

This layer is what turns clean geometry into a **buildable, playable** level — barely touched in the
current guides.

- **Collision is CYLINDER-BASED** — every actor has an upright cylinder (`CollisionRadius`,
  `CollisionHeight`; total height = 2×CollisionHeight), **always upright regardless of rotation; no
  per-poly/box/capsule actor collision in UE1** (that is UE2). Two flag families:
  *colliding* (`bCollideActors` master switch — required for any `Touch()`; `bCollideWorld`;
  `bCollideWhenPlacing`) and *blocking* (`bBlockActors`, `bBlockPlayers` — UE1 splits these;
  `bProjTarget` = **shootable** / trace-and-projectile target). Canonical recipes: invisible wall =
  `BlockAll` actor (small) or an **Invisible Collision Hull** (semisolid, all-invisible polys — large
  areas/doorways; must NOT touch walls/zone boundaries); non-blocking decoration = all collide/block
  flags off; **shootable-but-walk-through** = `bCollideActors`+`bProjTarget` on, blocks off; glass/
  grille = visual sheet + ICH behind it (**sheets never block on their own**). `bBlockZeroExtentTraces`
  / `BlockingVolume` are **UE2 — out of scope**.
- **`Physics` enum (UE1):** `PHYS_None` (default for static props/KeyPoints), `PHYS_Walking` (pawns;
  needs a `Base`, else falls), `PHYS_Falling` (drop-and-rest props/debris — obeys zone gravity),
  `PHYS_Flying`, `PHYS_Swimming` (water), `PHYS_Rotating` (spinning skybox/fan/pickup — uses
  `RotationRate`), `PHYS_Projectile`, `PHYS_Rolling`, `PHYS_Interpolating` (follow InterpolationPoints
  + `bInterpolating`), `PHYS_MovingBrush` (**every Mover**), `PHYS_Spider`, `PHYS_Trailer` (follow
  Owner). `PHYS_Ladder/Karma/Hovering/RootMotion/CinMotion` are **UE2 — out of scope.** Companions:
  `bStatic` (inert — no Tick/Timer/trigger; don't use just to stop a pickup spinning), `bMovable`,
  `bNoDelete` (can't `Destroy()`; set on brushes/nav points), `bHidden`, `bBounce`, `Mass`,
  `Buoyancy` (>Mass → floats).
- **Decorations:** place a concrete `Decoration` subclass; `DrawType` (DT_Sprite/**DT_Mesh**/DT_Brush/
  DT_None), `Mesh`, `DrawScale` (single uniform float — **`DrawScale3D` is UE2**), `Skin`/
  `MultiSkins[]`. Gameplay: `bPushable`+`PushSound`, `Health`+`EffectWhenDestroyed`+`contents/
  content2/content3` (breakable spilling loot), `bInvincible`, `bBobbing`+`Buoyancy` (float).
  **DX flag:** DeusEx uses its own **`DeusExDecoration`** family (adds a highlight **Name** label,
  `HitPoints`, invincibility) — DX-specific.
- **Effects: UE1/UT has NO particle `Emitter`s (UE2+).** UE1 effects are sprite/trail-based
  (`AnimSpriteEffect`, explosions, `SmokeGenerator`, blood/sparks, trails under `PHYS_Trailer`).
  **Coronas** are a **Light** mode, not an actor: `bCorona=True` + `Skin` (corona tex) + `DrawScale`
  0.1–0.3 + `LightRadius` (visibility distance); `Brightness=0` for a pure glint; `bLensFlare` is
  obsolete (superseded by `bCorona`). **DX flag:** DeusEx ADDS a real particle system — see §11.3.
- **`PlayerStart`** (a NavigationPoint): `bEnabled`, `bSinglePlayerStart` (def True), `bCoopStart`
  (def True), `TeamNumber`; spawns facing the actor's **Yaw** (`bDirectional` arrow); placed **40 uu
  above the floor**; **add more than max simultaneous players** (too few → telefrag).
- **KeyPoint family** = invisible location markers (abstract base, no own props): `AmbientSound`/
  `DynamicAmbientSound`/`TriggeredAmbientSound`, `InterpolationPoint`, `SpecialEvent`, `BlockAll`/
  `BlockMonsters`/`BlockPlayer`, `SpectatorCam`, `ClipMarker`/`PolyMarker`, `ThingFactory`,
  `LocationID` (HUD region name), `GuardPoint`/`HoldSpot`/`WayBeacon` (bot hints).
- **NavigationPoint / pathing:** paths are **compiled** into reachspecs (line-of-sight + traversable,
  storing width/height/distance so bots know they fit); build via console `PATHS BUILD [HIGHOPT|
  LOWOPT]` or F8→Paths Define; debug via **Show Paths** (press `Q` to hide BSP). Per-node controls:
  `bOneWayPath`, `bNoAutoConnect`, `ExtraCost`, `ForcedPaths[4]`, `ProscribedPaths[4]`. Subclasses:
  `PathNode`, `PlayerStart`, `InventorySpot` (auto-made at pickups), `LiftCenter`/`LiftExit`
  (elevator riding), `Teleporter`, `Ladder`, `JumpSpot`/`JumpDest`. Single-player AI markers:
  `PatrolPoint` (route chain via `NextPatrol`/Tag — walks the path network between points),
  `AlarmPoint`, `AmbushPoint` (has a wait radius). Spacing numbers are in §10.4.
  *(Nuance: `PatrolPoint` IS a DX class 🔬; stock Unreal's `AmbushPoint`/`AlarmPoint` are Unreal-AI
  actors NOT present in `DeusEx.u` — DX drives NPCs via ScriptedPawn orders instead.)*

### 11.3 DEUS-EX-SPECIFIC additions (🔬 all verified present in pristine `DeusEx.u`)

- **DeusEx particle/effects family** (stock UT99 has none): **`ParticleGenerator`** (extends
  `Effects`) — the mapper-placed emitter: `frequency` (1.0), `checkTime` (0.1s), `numPerSpawn`,
  `riseRate`, `ejectSpeed`, `particleTexture`, `particleLifeSpan` (4s), `particleDrawScale` (0.1),
  `bParticlesUnlit`, `bScale`/`bFade`/`bTranslucent`/`bGravity`/`bRandomEject`, and — the DX
  enhancement over Unreal's always-on system — **`bTriggered`** (spawn only after a Trigger).
  Presets/siblings: **`WaterDrips`** (ceiling drips, arrow down; `bGravity=True`), **`LaserEmitter`**
  (laser tripwire; 2 reflection points; freezes calc when player >960 uu away), **`ElectricityEmitter`**
  (damaging arc; `DamageAmount=2`, `bDirectional` — arrow to aim; own light), **`Fire`** (flame
  sprite + `LE_FireWaver` light), **`ProjectileGenerator`** (`ProjectileClass`, `WaitTime`,
  `bSpewUnseen`), **`TrashGenerator`** (wind debris — "Paper"/"tumbleweeds", `WindSpeed`).
  Not mapper-emitters: `SmokeTrail` (code-spawned projectile puff), `WaterFountain` (a drinkable
  **`DeusExDecoration`**, not an effect). `SmokelessFire` is declared in source but is not a
  mapper-facing class.
- **DX gameplay-wiring actors** (from the official DX SDK "Level Design" manual, all 🔬-present):
  **`FlagTrigger`** — the mapper face of the DX **flag database** (`player.flagBase` with
  `SetBool/GetBool/GetExpiration/DeleteFlag` — confirmed rich in the binary): `flagName`, `flagValue`,
  `bSetFlag` (write) vs `bTrigger` (gate: fire Event only if the flag matches), `bWhileStandingOnly`,
  `flagExpiration` (**-1 = permanent**). **`GoalCompleteTrigger`** — `goalName` completes a goal the
  `MissionScript` created (`AddGoal`). **`LogicTrigger`** — boolean combiner (AND/OR/XOR + Not) of two
  trigger inputs. **`SequenceTrigger`** (`SeqNum`) + **`MultiMover`** (`SeqKey1..4`/`SeqTime1..4`,
  `bReverseKeyFrames`) + `ElevatorMover` (`bFollowKeyFrames`) — multi-stop elevator/mover sequencing.
  **`BeamTrigger`**/**`LaserTrigger`** (`bNoAlarm`) — directional laser triggers.
- **`DeusExLevelInfo` full props:** `MapName`, `MapAuthor`, `MissionLocation`, `missionNumber`
  (must match the ConEdit conversation mission number), `bMultiPlayerMap`, `Script` (the
  `MissionScript` subclass), **`TrueNorth`** (rotator offset defining world-north for the **in-HUD
  compass** — DX-specific), `startupMessage[4]`, `ConversationPackage` (default "DeusExConversations").
- **ConEdit conversation net-new:** invocation modes **"PC Frobs NPC" / "Player Bumps NPC" / "NPC
  Enters PC Radius"**; InfoLink/Datalink files use the **`DL_`** prefix and are flagged "Datalink
  Conversation" + "Display only once"; `#exec CONVERSATION IMPORT` compiled via `ucc make`; NPC
  `BindName` has no spaces (player = `JCDenton`).
- **DX damage zones are ordinary `ZoneInfo`** with a `DamageType` **string** ("TearGas", "Radiation",
  "Flamed", "Drowned", …) + `DamagePerSec` — NOT bespoke zone classes (confirms §10.5). DX ships
  **`WaterZone`** but not UT's `LavaZone`/`SlimeZone`.
- **Single skybox per level** is an engine limit (DX intro ships two setups but only Paris is used) —
  engine-generic, not DX. **Distance fog** (`Engine.u` `ZoneLight.FogColor` + `FogDistance`) is
  **engine-generic** too; DX adds no bespoke fog class (atmosphere = `ParticleGenerator` dust +
  `ZoneInfo` damage types).

### 11.4 What to add to which guide (rewrite guidance)

- `csg-and-bsp.md` / a new **"brush geometry & builders"** section: §11.1 (native+extended builders,
  clipping, curves, terrain, MeshMaker) — and name the real builder params next to the uedcli verbs.
- A **new "actors, collision & pathing"** guide (currently MISSING — the guides only cover geometry/
  lighting/zoning/textures/movers): §11.2 (collision model, physics enum, decorations, PlayerStart,
  KeyPoints, NavigationPoint/pathing). This is the biggest coverage gap for "buildable" levels.
- `lighting.md`: coronas (§11.2) + engine ZoneLight `FogColor`/`FogDistance` (§11.3).
- A **DX-specific "gameplay wiring"** section (skill-plugin territory): the DX particle family, flags/
  goals/logic/sequence actors, `DeusExLevelInfo.TrueNorth`, ConEdit invocation modes (§11.3).

---

## 12. Third research pass (2026-07-19, "collect more knowledge")

A third pass on the last thin areas: **texture authoring depth**, **populating levels with NPCs**, and
the **craft of good design** (incl. the DX immersive-sim philosophy). Many claims below were
cross-checked against the shipped binaries — ⟨bin⟩ marks a fact verified against
`DX/System/{Engine,DeusEx,Fire}.u` or `DX/Textures/*.utx` this session (highest confidence; the actual
shipped build, not a UT/UE2 proxy).

### 12.1 Texture authoring, procedural & scripted textures (ENGINE-GENERIC unless flagged)

Several of the probe's starting assumptions were **corrected by the binary** — record the corrections:
- **`ScriptedTexture` is a DRAW-ON surface, not a camera feed** ⟨bin⟩ (chain `Bitmap→Texture→
  ScriptedTexture`; props `NotifyActor`/`SourceTexture`; each frame resets to `SourceTexture` then
  calls `NotifyActor.RenderTexture()` where script draws `DrawTile`/`DrawText`; **D3D-only**;
  scoreboards/counters). **Camera-view-to-surface (`DrawPortal`) is UE2-only** — do NOT attribute it
  to DX. `RenderIteratorClass` is the particle/procedural-geometry hook (DX `LaserIterator`/
  `ParticleIterator extends RenderIterator`), unrelated to monitors.
- **DX security-camera monitors do NOT use `ScriptedTexture`** ⟨bin: no `ScriptedTexture` ref in
  `DeusEx.u`⟩. The feed is a **live 3D render composited into the hackable-computer UWindow UI**:
  `SecurityCamera` (Tag'd) → `ComputerSecurity` with `Views[3]` (`struct sViewInfo { titleString;
  cameraTag; turretTag; doorTag }`) → the console UI's `ViewportWindow.SetWatchActor(camera)`. There
  is **no world-mounted monitor surface** showing a camera. Mapper wiring: place camera, Tag it, set
  `Views[0].cameraTag=<tag>`.
- **The procedural fractal-texture family ships in a separate `Fire.u` package, NOT `Engine.u`** ⟨bin⟩:
  `FractalTexture extends Texture`; `FireTexture`/`WaterTexture`/`IceTexture extends FractalTexture`;
  `WaveTexture`/`WetTexture extends WaterTexture`. **`PaletteModifier` does NOT exist in shipping DX**
  (an OldUnreal-227 addition). Authoring: Texture Browser → New → set Class (FireTexture/WaveTexture/
  WetTexture…) + Size (locked at creation) → set `FX_*`/`RenderHeat`/`WaveAmp` **before painting** →
  left-drag paints sparks/drops, right-drag erases. `FireTexture` has `bRising` (two-algorithm switch,
  **no `FireType`**), `RenderHeat`, a **29-value `ESpark`** enum (SPARK_Burn/Sparkle/Pulse/…
  /Lightning/Wheel/Sprinkler) ⟨bin⟩ and `DrawMode` (DRAW_Normal + 4 Lathe modes). `WaterTexture` has a
  **20-value `WDrop`** enum ⟨bin⟩. `WetTexture`/`IceTexture` distort a `SourceTexture` by the wave
  field. Numeric defaults are `native` C++ — not recoverable from the package.
- **Detail/macro/env** ⟨bin⟩: `DetailTexture` is a **Texture-class** property (set once on the base
  texture; **no `DetailScale` in UE1** — the value-8 figure is UE2); `MacroTexture` present but engine
  comment "not currently used"; environment mapping = poly flag `PF_Environment`/surface `bEnvironment`
  for world surfaces, `bMeshEnviroMap`+`Skin` for meshes (gated by the renderer `ShinySurfaces` ini).
  `MultiSkins[8]` is an actor mesh-skin array, unrelated to BSP surface texturing.
- **Scrolling surfaces** ⟨bin⟩: NOT a per-surface speed — set the poly flags `PF_AutoUPan`(0x200)/
  `PF_AutoVPan`(0x400) on the face (flag = "scrolls", no speed) and the **speed lives on the
  `ZoneInfo`/`LevelInfo` as `TexUPanSpeed`/`TexVPanSpeed`** (shared by all auto-pan faces in the zone).
- **Surface poly-flag catalog** (sum decimals to combine) ⟨bin surface-bools⟩: `PF_BrightCorners`
  0x80000 (kills dark edge seams), `PF_SpecialLit` 0x100000 (lit only by `bSpecialLit` lights),
  `PF_SmallWavy` 0x2000/`PF_BigWavy` 0x1000, `PF_NoSmooth` 0x800, **`PF_HighShadowDetail` 0x800000 /
  `PF_LowShadowDetail` 0x8000 = the per-surface lightmap-resolution control (flags, not a number)**,
  `PF_Portal` 0x4000000, `PF_Mirrored` 0x8000000. Console: `POLY TEXPAN/TEXSCALE/TEXALIGN/TEXINFO`.
- **DX texture catalog** [DX] ⟨bin: all 18 on disk⟩: the **`CoreTex*` set is the reusable cross-level
  material palette** (Brick/Ceramic/Concrete/Detail/Earth/Foliage/Glass/Metal/Misc/Paper/Sky/Stone/
  Stucco/Textile/Tiles/WallObj/Water/Wood); level-named packages (`UNATCO`, `Paris`, `NewYorkCity`,
  the `HK_*` family — no single "HongKong") are one-offs. Naming `<condition><descriptor>_<variant>`
  with condition prefixes `Clen/Drty/Damg/Corg/Olde/Fros` (e.g. `ClenGrayMetal_A`). `CoreTexMetal` is
  the largest structural set; `CoreTexDetail` (`DMetal_A`, `DScanline`) feeds other packages'
  `DetailTexture` slots. **The reserved texture Group `Ladder` makes a surface climbable** ⟨bin: DX has
  a `case 'Ladder':` group switch⟩ — this **binary-confirms** the §10.5 ladder finding.

### 12.2 Populating levels with NPCs — the DX ScriptedPawn system [DX] (all ⟨bin⟩-verified)

The current guides don't cover NPCs at all; this is a large DX-specific authored dimension. All below
verified present in pristine `DeusEx.u` this session.

- **`Orders` is a state NAME (not an enum); `FollowOrders()` does `GotoState(Orders)`; default
  `Wandering`.** Mapper-facing values (with `OrderTag`): **Standing** (post; leash via `HomeTag`/
  `HomeExtent` def 800), **Sitting** (a `Seat`), **Patrolling** (a `PatrolPoint` chain whose `Tag ==
  OrderTag`, walked via `NextPatrolPoint`), **GoingTo**/**RunningTo** (walk/run to a tagged actor),
  **WaitingFor**, **Following**, **Shadowing** (stealth-tail), **Wandering** (default; `Restlessness`/
  `Wanderlust`), **Dancing**, **Fleeing**, **Attacking** (both take a tag → become the enemy),
  **Alerting**, **Seeking**. AI-only states (not set by the mapper): StartUp, Conversation, Burning,
  Stunned, Dying, etc. `SetOrders(name, newOrderTag, bImmediate)`; a conversation reprograms an NPC via
  `ConvOrders`/`ConvOrderTag`, applied when the convo ends.
- **Three stimulus blocks (not two):** `var(Reactions) bReact*` = do I ENGAGE (`bReactPresence` def
  True→attack, `bReactShot`, `bReactAlarm`, `bReactCarcass`, `bReactDistress`, `bReactLoudNoise`→seek,
  `bReactProjectiles` def True, `bReactFutz`); `var(Stimuli) bHate*` = what turns me HOSTILE
  (`bHateShot`/`bHateInjury` def True, `bHateWeapon`, `bHateHacking`, `bHateCarcass`…) feeding
  agitation; `var(Fears) bFear*` = what makes me FLEE (`bFearWeapon`/`bFearShot`/`bFearInjury`/
  `bFearCarcass`/`bFearAlarm`/`bFearProjectiles`/`bFearHacking`). Alarm broadcast: `RaiseAlarm`
  (`RAISEALARM_BeforeFleeing` default), `bEmitDistress`, `MaxProvocations` (def 1).
- **Combat/behavior tuning:** `MaxRange`/`MinRange`, `MinHealth`, `BaseAccuracy` (**lower = better**),
  `EnemyTimeout`, `bDefendHome`, temperament floats `Restlessness`/`Wanderlust`/`Cowardice`;
  `InitialInventory[8]` (`struct {class<Inventory>; Count}`) + `bKeepWeaponDrawn`.
- **Class roster** (place a concrete leaf, never an `abstract` base): `HumanMilitary` (MJ12Troop,
  MJ12Commando, UNATCOTroop, Soldier, Terrorist), `HumanCivilian` (Bartender, Businessman1-3, Doctor,
  Sailor, ScientistMale/Female…), `HumanThug`→TerroristCommander, `Animal` (Rat, Greasel, Karkian,
  Gray, Doberman, Pigeon, Fish…), `Robot` (MilitaryBot, SecurityBot2-4, SpiderBot, CleanerBot,
  MedicalBot). Each has a paired `<Name>Carcass` (`CarcassType`). Ambient spawners: `PawnGenerator`/
  `FishGenerator`/`FlyGenerator`.
- **Binding/scripting:** `BindName` (no spaces; the con-system + flags key off it, e.g.
  `BindName$"_Dead"`), `FamiliarName`/`UnfamiliarName` (HUD), `bCanConverse`, `bImportant`/
  `bInvincible`, `InitialAlliances[8]` (`struct {AllianceName; AllianceLevel −1..+1; bPermanent}`;
  player = `"Player"`).
- **Workflow:** (1) **pathnode the level + Define Paths FIRST** (no paths → NPC won't move, silently);
  (2) place a concrete class on the floor; (3) set `Orders`+`OrderTag`; (4) `InitialAlliances`
  (hostile-to-player = add `"Player"` at −1); (5) tune Reactions/Fears/`RaiseAlarm`; (6)
  `InitialInventory`; (7) `BindName` + conversations/triggers; (8) rebuild paths, playtest.
- **UT names that DO NOT exist in DX** ⟨bin: confirmed absent⟩ — don't offer them: `bFearIndoors`,
  `bFearDarkness`, `bFearZones`, `HateTag`, `HateThreshold`, `bGenerateFleshFrag`, `Aggressiveness`,
  `IdealRange`, `SeekTag`, `AlarmTag`, `bCanClimb`, `ThingFactory` (for NPC spawning). Also
  `AmbushPoint`/`AlarmPoint` are Unreal-AI actors absent from DX (§11.2).

### 12.3 The craft of a good level — composition, lighting, flow [ENGINE]

The guides are heavy on mechanics and light on craft; the rewrite (or a new "design craft" guide)
should carry these actionable rules:
- **Composition:** design to the player's size (build to the substrate's pawn dims, not by eye);
  **proportion over everything, sketch to scale with floor heights**; **kill the box** (detail every
  surface — trim edges of platforms/stairs, arch doorways to mount motivated lights; use **shadow to
  hide flat surfaces** where polys won't allow geometry); **avoid the room-corridor-room trap** →
  interconnect across 2+ floors ("a snake eating itself"); **think in 3D / verticality**; **break long
  sightlines** (framerate + readability) but **show the goal**; anchor spaces with **landmarks** and
  make them visually + **audibly** distinct (lifts/teleporters/water/pickups each have a distinct
  sound); deliberate **contrast** (open vs tight, light vs dark).
- **Lighting craft:** motivate every light; **never light flat** (min 2 lights: hotspot + falloff;
  ambient ≤~32); **radius is the primary tool** for distinct pools (default 64 often bleeds — drop to
  ~5 for tight zones, ~175 outdoors); use light/shadow to **guide** (crisp High-Shadow-Detail patterns
  pull the eye; a spotlight beacons) and to **hide** (secrets/enemies in shadow); **color for zone
  identity** (drop `LightSaturation` from 255 to ~64 for a visible tint); prefer many small-radius
  lights over few huge (cost ~r³).
- **Flow & pacing:** **plan layout — and thus gameplay — first, on grid paper**; **blockout in
  primitives, detail last** (the commercial workflow + the only reliable perf regulator); aim for
  "complicated linearity" (interesting *how*, not sandbox); pace tension against rest; **"break up your
  innovations"** (don't stack strobe+fog+high-shadow+big-fight in one open view — keep complex lighting
  in enclosed short-sightline areas); item placement by **risk-vs-reward**; **always signal
  progress/never leave the player lost**; favor Movers/interactivity ("players want to *affect* the
  level, not pass through it").

### 12.4 The DX immersive-sim design philosophy [DX] — the highest-value craft

From the actual DX designers (Spector's "Rules of Roleplaying", Harvey Smith's "Systemic Level
Design", the GDC/Gamasutra postmortems). This is a *different kind* of knowledge — how to make a level
a **problem-space with multiple valid solutions** — and is the core of what "a good DX level" means:
- **"Problems, not puzzles."** An obstacle course, not a jigsaw — solutions must never require reading
  the designer's mind. The single most-cited DX maxim.
- **Multiple solutions to every obstacle, keyed to skills · augmentations · objects · weapons** — so
  the routes that open up *are* the character the player built. The canonical approaches: **Combat /
  Stealth / Hacking / Social**, plus architectural routes (**vents, ducts, ladders, windows, catwalks,
  rooftops, sewers**). Even a raw "left hall vs right hall" fork sorts players into playstyles.
- **How they shipped it (practical for a modder):** the tech couldn't fully simulate it, so they
  **hand-authored three explicit routes per problem — a skill path, an action path, and a
  character-interaction path** — then let systems add emergent extras. **You can get the feel by
  authoring 3 keyed routes; you don't need a full simulation.**
- **Systemic consistency (Smith):** design behavior **by object TYPE, not instance**; "things that are
  the same behave the same by default." Consistency → the player predicts → plans → feels agency
  ("Playing the Game" vs "Playing the Designer"). Emergence (the mine-climbing trick) falls out of
  consistent simple rules. Don't depict non-functional doors/items — every "lie" about interactivity
  erodes planning.
- **Readable stealth as a mechanic:** light/shadow + cover + guard sight/sound are gameplay, not mood;
  consistent sound propagation + throwable props make distraction a player *tool*. Teach affordances
  diegetically (a crowbar by breakable crates).
- **Environmental storytelling:** two channels — conversations, and **in-world text (datacubes/emails/
  books)** that rewards explorers with story *and* mechanical payoff (door codes). Build "*this*
  warehouse where *these* people did *this*."
- **No in-game GPS → legibility by architecture:** no minimap/markers, so the *space* must be legible —
  dominant always-visible landmarks, plausible real-world geography, light/leading-lines toward routes.
  (This is where "spaghetti" fails: many routes + no landmark hierarchy = disorientation — pair
  multi-path with a **readable spine + strong landmark**.)
- **Hub structure & reactivity:** hub-and-spoke with **return visits** to a world that persists/evolves;
  **"fewer characters = deeper characters"**; **choice without consequence is irrelevant**, and
  consequence must be *predictable* (real-world logic) to be fair; Spector's **Choice + Consequence +
  Recovery** (give the player a way to recover from a botched attempt).

### 12.5 Practical optimization & finishing [ENGINE] (net-new beyond "≤150 polys")

- **Node vs poly:** node = BSP leaf nodes (colored polys in Zone/Portal view); **target node:poly ≈
  2:1** (retail 2.5–2.6; unsplit cube 1.0); **hard limit 65,536 nodes**. Rebuild with **Optimal** BSP +
  geometry optimization (never "Lame"); rebuilding *without* optimization gets *worse* each pass.
- **Readout commands:** `STAT FPS` (ms + polys), `STAT ZONE` (visible vs **rejected** — confirms
  culling), `STAT RENDER`/`POLYC`/`MESH`, `MEMSTAT`, `OBJ LIST`; viewport **rmode** views (wireframe;
  **Zone/Portal = the optimization view**; lighting-only). (Depth-complexity rmode is UE2 — may be
  absent in DX.)
- **Zone culling in practice:** portals at **both ends** of a hallway; keep portal brushes simple
  prisms (≤6 verts), order **To Last**; as many *non-adjacent* zones as possible; **~63–64-zone hard
  limit** (exceed → merge / "whole map underwater").
- **Build order:** Geometry → BSP → Lighting → Paths. **Rebuilding Geometry+BSP erases lighting** →
  relight after any geometry change; keep **Build Visibility Zones** checked (unchecking wipes zones).
- **Finishing:** MyLevel `ScreenShot` texture (256×256 P8) + `LevelInfo` Title/Author; testing
  checklist — walk for HOM, hunt **brown null-zones** in Zone/Portal view (semisolid∩world-edge — they
  eat the zone budget), ZoneSound on every ZoneInfo, check KillZ, verify node:poly + `STAT FPS` in the
  busiest views; never run `texture cull` with hidden brushes present (wipes their textures).

### 12.6 Guide-mapping (what the rewrite gains from this pass)

- A **new "texture authoring"** deep section: procedural `Fire.u` textures, `ScriptedTexture` reality,
  detail/env, poly-flag catalog, scrolling, the `CoreTex*` catalog (§12.1).
- The **DX "gameplay wiring" section** (from §11.3) gains the **ScriptedPawn NPC system** (§12.2) and
  the **security-camera→console** recipe (§12.1) — this is prime skill-plugin material.
- A **new "design craft / immersive-sim" guide** (§12.3–12.4) — the "what makes a GOOD DX level"
  half the current mechanics-only guides lack; the DX immersive-sim philosophy is the crown jewel.
- `zoning-…md`/a new "optimization" section gains the concrete node:poly / STAT / rmode / build-order
  workflow (§12.5).

### 12.7 Completeness verdict (after three passes)

Coverage is now broad across geometry, BSP, zones, lighting, textures, movers, the actor/collision/
physics/pathing layer, DX gameplay wiring, NPC AI, and design craft/philosophy. **Genuine residual
gaps** (candidates only; none blocking):
- **ut99.org file id=14742** — still unretrievable (JS bot-check); overlaps tactical-ops.
- **Numeric class defaults — NO LONGER A GAP: uedcli decodes them.** `actor build <Class> | actor add
  - | actor prop get - <Prop>` returns the resolved class default offline (verified 2026-07-19 — see
  §10.4 and its Spike-impact note for the DX-authoritative numbers). The rewrite pulls any default it
  needs this way rather than citing tutorials. **One residual sub-case:** truly `native` classes whose
  defaults live in C++ with empty script `defaultproperties` (the `Fire.u` fractal-texture `FX_*`/
  `RenderHeat` values) are not in the package, so those specific numbers stay unrecoverable offline;
  everything script-defaulted (actors, pawns, lights, movers, particles, decorations) reads cleanly.
  Per-package `CoreTex*` texture enumeration is available via the `texture` catalog verb, not crawling.
- **DX conversation/datacube AUTHORING depth** (the ConEdit tool workflow, branching, wiring door
  codes to flags) — partly covered (Steve Tack + §10.5 + §11.3); a dedicated ConEdit walkthrough would
  finish it, but it edges from *level design* into *mission scripting*.
- Net: external crawling has hit diminishing returns; the few remaining specifics are **read from the
  substrate with uedcli** (defaults, texture catalog) or pinned by the spike's B2 map-export corpus —
  not found by more reading.

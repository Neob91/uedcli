# Zones — scoping draft

**Draft — a SCOPING document, not a build spec.** Zones are a large feature. This maps what already
exists, what is genuinely missing, the big unknowns, and the scope/priority decisions the owner has
to make. It does not commit a CLI surface.

## Goal

Let an LLM level-designer author UnrealEngine-1 zones as text: place and configure `ZoneInfo`
actors, mark zone-portal surfaces, and set zone properties (water, fog, gravity, ambient light,
reverb, sound). The guiding board goal is to expose everything a human can do in the editor without
the GUI; zones are one gap.

Background (engine facts, all in `dev/docs/unrealed/`): a **zone** is a connected region of the
built world. Regions are separated by **zone portals** — surfaces carrying `PF_Portal`. The engine
resolves zone membership during the BSP build (`BSP REBUILD`, with a dedicated `BSP REBUILD ZONES`
pass — `unrealed/commands.md`). A **`ZoneInfo`** actor placed inside a region names and configures
that zone; its properties (`ZoneGravity`, `bWaterZone`, `AmbientBrightness`, fog, reverb, …) are
ordinary actor properties. The engine caps a level at **64 zones**. World collision and the zone
tree are structural properties of the built BSP, not per-actor flags (`unrealed/quirks.md` "CSG
model").

## Current state — most authoring primitives already exist

- **Zone-portal surface flag: DONE.** `portal` is a `PF_NAMES` flag (`0x4000000`,
  `uedcli/query.py:21`). It is settable two ways: at build time via `brush build sheet --flag
  portal` (`uedcli/cli/parsers/brush.py:201-202` — the help even names the zone-portal case), and on
  an existing face via `brush poly set --add-flag portal` (`uedcli/surface.py`, `encode_flags`
  `uedcli/surface.py:38-44`). So "flag the portal surfaces" needs no new verb.
- **`ZoneInfo` placement: covered by the generic path.** `ZoneInfo` is a point actor. It is emitted
  by the generic generator `actor build <Package.Class>` and landed with `actor add -`
  (`direction/generators.md`). Nothing zone-specific is required to place one.
- **Zone properties: covered by `actor prop set`.** `ZoneGravity`, `bWaterZone`, etc. are ordinary
  actor props, set through the existing propedit surface (`uedcli/propedit.py`, `actor prop`). A
  designer discovers them with `class show DeusEx.ZoneInfo --category <Zone/Lighting/...>`.
- **doctor: partial.** `level doctor` flags the `Semisolid + Portal` misuse (`uedcli/doctor.py:377-
  381`) and reads portal flags effectively (actor-level OR per-poly, `uedcli/doctor.py:77-78,122-
  124`). It does NOT count zones, does not check the 64-zone cap, and does not check that each zone
  has a `ZoneInfo` or that portals actually sit on a region boundary.
- **The build step: unverified, and native is broken.** `level materialize`/`level apply` run `MAP
  REBUILD` + `LIGHT APPLY` (`uedcli/apply.py:289`, `uedcli/driver.py:485-487`) but never an explicit
  `BSP REBUILD ZONES`. Whether a plain `MAP REBUILD` assigns zones fully, or whether the dedicated
  ZONES pass is needed, is UNVERIFIED (Open questions). The **native** (editor-free) materialize
  path's zone computation is a known, actively-worked bug — over-fragmentation from a shattered CSG
  tree (`board/inbox/native-zone-over-fragmentation`, `…/native-over-zones-now-confirmed-on-a-
  second`, `…/pin-the-native-zone-flood-against-the-actual`, and others). So faithful native zone
  resolution is NOT available today.

## The core tension — authoring is easy, VERIFYING is hard

Placing a `ZoneInfo`, flagging portals, and setting props are all pure model-side edits uedcli
already does. The hard part is everything that needs the *built* zone tree:

- "Which zone is this actor/surface in?" — a function of the BSP, not of the T3D. Answerable only
  after a build (editor or native), and native is broken.
- "How many zones does this level have? / does it exceed 64?" — same: emergent from the build.
- "Is every subtracted region either sealed by portals into its own zone or intentionally shared?"
  — the real design question, and the hardest to answer offline.

This is why zones cannot be a purely model-side feature the way `brush build` is. The scope decision
is largely: how much of the build-dependent half do we take on now, given native zone resolution is
unreliable and the editor path is slow and crash-prone.

## Design — options

**A. Thin: lean on the generic verbs + a documented recipe (recommended for v1).**
No new zone verbs. Ship: (1) a `docs/leveldesign/` recipe — subtract a region, seal openings with
`brush build sheet --flag portal`, place a `ZoneInfo`, set its props — and (2) targeted `level
doctor` checks that ARE offline-decidable (below). Smallest surface, respects "verbs compose", and
avoids committing a zone-query verb whose backend (native zone resolution) does not yet work.

**B. A `zone` convenience verb family.**
e.g. `zone list` (enumerate `ZoneInfo` actors and their props), `zone place <name>` (sugar over
`actor build DeusEx.ZoneInfo` + prop-set), `zone show <name>`. These are just thin sugar over
existing verbs UNLESS they report built-zone membership — and that membership needs a working build.
Sugar-only is low value; membership-aware is blocked on native/editor. Recommend deferring.

**C. doctor zone checks (recommended, pairs with A).**
Offline-decidable additions to `level doctor`:
- a `ZoneInfo` whose zone can't be determined offline is hard, but "two `ZoneInfo` actors so close
  they likely share a region" and "a `portal`-flagged face that is not a closed boundary" are
  candidates — needs judgement on what is decidable without a BSP.
- the existing `Semisolid + Portal` check stays.
- A true 64-zone-cap check needs the built tree, so it belongs to the build step's warnings, not the
  offline doctor (mirrors the duplicate-`order_value` warning that materialize emits, `direction/
  materialize.md`).

**Recommendation:** A + C. Treat B (a `zone` verb family) as a later nicety, and gate any
built-zone query on a working zone-resolution backend.

## Big unknowns (flag, do not design around)

1. **Does `MAP REBUILD` assign zones, or is `BSP REBUILD ZONES` required at materialize?** Governs
   whether the build step needs a change at all. Verify live before speccing a build change.
2. **Native zone resolution is broken.** Any offline "which zone" query depends on the native CSG/
   zone port, which is the subject of several open `board/inbox` bugs. Until that lands, zone
   membership is an editor-only answer.
3. **DX substrate placeability.** The stripped DeusEx substrate crashes on some engine classes
   (`Keypoint` — see `board/README.md` portability goal). Confirm `DeusEx.ZoneInfo` (and any
   subclasses) import cleanly before relying on the generic placement path.
4. **The 64-zone cap surfacing.** Where does an over-cap level get flagged — the build step
   (needs the count) vs the doctor (offline, can't count reliably)?

## Edge cases (for whatever v1 lands)

- A portal sheet is `PF_NotSolid` + `PF_Portal` (a glass pane wants `PF_Semisolid` instead — it
  still blocks; only portals must be non-solid). The `Semisolid + Portal` doctor check already
  guards the wrong combination.
- A `ZoneInfo` placed in a region with no sealing portals falls into the default zone 0 — silently
  wrong, and only detectable post-build.
- Water/pain/etc. zone behaviour is driven by `ZoneInfo` props, not by geometry — so a correctly
  sealed zone with a mis-set prop is a content bug, not a doctor-catchable one.

## Tests (for whatever v1 lands)

- If A: the recipe is exercised end-to-end (subtract → portal sheet → `ZoneInfo` → materialize)
  producing a level whose re-export carries the portal flag and the `ZoneInfo` with its props.
- If C: doctor unit tests for each new offline check, plus the existing `Semisolid + Portal` case.

## Docs to update on build

- `docs/leveldesign/` — the zone recipe (NEW craft knowledge → needs owner approval before writing,
  per `CLAUDE.md` "Documentation").
- `docs/usage.md` — any new verb/flag/doctor category.
- `dev/docs/unrealed/` — pin the `MAP REBUILD`-vs-`BSP REBUILD ZONES` finding once verified live.

## Open questions

- Scope/priority of the whole feature, and A-vs-B-vs-C — see `questions/zones-v1-scope.md`.
- The build-step behaviour (`MAP REBUILD` vs `BSP REBUILD ZONES`) is a live-verify unknown, not an
  owner fork — resolve with a spike before any build change.

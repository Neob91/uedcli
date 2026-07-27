# Spec: asset catalog — the CLASS arm

**Status:** split out of the unified spec 2026-07-26. **Two spec-gate rounds' findings for this arm are
folded**; the arm's own remaining items are ordinary fixes, not open design questions. **Build this arm
first** — it is the capability an agent most lacks (it cannot see what it is placing), and it is the one
arm with no unresolved owner decision.
**Requested by:** the owner (2026-07-25, session `uedcli:catalog`).
**Ephemeral:** fold the outcome into `architecture.md` + `usage.md` on build, then delete.

> **Part of the split asset-catalog spec set** (split 2026-07-26 after two spec-gate rounds returned
> ~103 findings and the churn proved to be concentrated in the texture and audio arms — see
> `board/inbox.md`). The shared engine, storage layout, verb surface, decisions and prerequisites live in
> **board item `unified-asset-catalog`**, which every arm depends
> on and which is built first. Sibling arms:
> [class](spec.md) ·
> texture (board item `unified-asset-catalog`) ·
> audio (board item `sound-corpus-remeasure`).

---

## 6. The class arm

**Derived facts only; meaning comes from classification.** `class list`/`class show` already derive
schema, hierarchy, defaults and abstractness; the **superclass already says what a class is for**.
The catalog adds the file facts an agent needs to actually *place* the thing, plus the picture, plus
its stored classification.

**Size is the missing fact and it is cheap.** Today an agent can see a crate and still has to guess
its footprint, and whether its origin sits at the base or the centre — so decorations sink into floors
and interpenetrate. The only way to read a default today is the three-command detour
`actor build | actor add - | actor prop get -`, which needs a trunk. `class show` therefore reports
**mesh bbox × `DrawScale`, `CollisionRadius`/`CollisionHeight`, and `PrePivot`/origin offset**. The
mesh decoder already produces the bbox; the rest are class defaults.

**`class show` prints every property's resolved DEFAULT — not just the placement three.** Today it
prints names and types only (`AmbientBrightness: ByteProperty`), and `actor prop get` prints only
properties that were explicitly *set*, so a freshly placed actor appears to have no properties at all.
Between them there is **no way to answer "what value does this property start at"** without the
`actor build | actor add - | actor prop get -` detour named above — which needs a trunk, writes a
throwaway actor into the user's level, and answers one property at a time. Measured cost: an agent
diagnosing a room that had gone fullbright immediately after 8 `Engine.ZoneInfo` actors were placed
spent **over an hour** on `AmbientBrightness`, per-light radii and polyflags before the real cause
turned out to be elsewhere entirely — and the answer it needed (`AmbientBrightness` defaults to **0**,
so a fresh `ZoneInfo` adds no ambient at all) would have eliminated its prime suspect in seconds.

So `class show` reports the **resolved default beside each property**: `AmbientBrightness: ByteProperty
= 0`. A property with no default anywhere reports its type's zero value, marked as such — never blank,
which reads as "unknown".

**Scope of "each property", stated precisely:** `class show` prints the *category-bearing editable*
properties (it groups by UnrealEd category), so this adds a default to each of those — it is not a dump
of every field on the class. Say so in `--help`; "every property" would over-promise.

**Two honest cost notes, because an earlier draft called this "not new machinery" and that was wrong:**

- The **values** are indeed already paid for — prerequisite 1 persists resolved defaults because the
  class arm needs them corpus-wide, and `Engine.ZoneInfo.AmbientBrightness` really does resolve to `0`
  off the tracked packages (verified 2026-07-26, 282 defaults resolved).
- But **provenance is not**. `uprops.resolve_class_defaults` returns
  `dict[(casefold(name), array_index)] -> rendered str` and its root→leaf overlay loop **overwrites
  without recording which ancestor supplied the value**. Reporting "inherited from `Engine.Actor`"
  therefore changes a shared function's return contract, and prerequisite 1's cached blob holds raw
  per-class tags rather than resolved values. The information is available *at* that loop so the change
  is small — but it is a change to a shared seam, not a pure output tweak. **Either implement provenance
  as part of this, or drop the "names the class it came from" promise; do not assume it is free.**

It also removes the documentation workaround this detour currently lives in — one parenthetical inside
the DX class catalog, which is where an agent looking for lighting behavior does not look.

**A class that declares no own properties says so.** `class show DeusEx.DataCube` prints a header, a
superclass chain and `(+142 inherited, in 16 more categories: …)` — and **no property names**, because
`DataCube` declares none of its own. The output is indistinguishable from "this property does not
exist", and the bare category list gives no clue which of the 16 holds the one you want. When a class
has zero own properties, `show` prints an explicit one-line hint naming the two ways through
(`--depth all`, or `--category NAME`), rather than leaving an empty space to be misread.

**`placeable` keeps ONE definition — the existing file-fact proxy** (`classindex.is_placeable`), and its
`--help` is corrected to state what the predicate actually does. **It is FAIL-OPEN**, which the earlier
wording ("non-abstract, descends from `Actor`") hid: the real test is
`descends_from(fqcn, Engine.Actor) and is_abstract(fqcn) is not True`, so a class whose abstractness is
**undeterminable counts as placeable** — deliberately, so it is listed rather than hidden. Two consequences
to settle in the same slice: the help text must name that third case, and the branch is a "don't know"
answered as a confident yes, which sits against `conventions.md` "A predicate answers or it RAISES".
**Pick one and do it: state the fail-open behaviour in the help, or make the undeterminable case raise.**
Do not ship the promised-but-inaccurate string, which is exactly the stale-help failure `conventions.md`
cites by name. *No histogram, no derived "commonly placed"* (decision 1). Whether something is
worth placing is a classification an LLM writes. This keeps `class list` **offline, maps-free and
~0.4 s**, instead of requiring 120 stock map files on disk.

**No verb collision remains.** `class show` keeps the property-browser view and `--category` keeps
meaning the UnrealEd property category; it gains the catalog fields. `class list` keeps its
inheritance tree and existing flags. Previews live on the new `class preview`. **The build must state,
flag by flag, what `class list --json` and `class show --json` emit** — `class list` today prints a
tree with no `--json`, and its `--package` already means "the *placeable* classes defined in P"
(filtered), not a plain corpus scope. This is the one place the four kinds are **not** literally
uniform, and the spec accepts that explicitly rather than pretending otherwise.

**Thumbnails.** `DT_Mesh` → native render from `Mesh` + `MultiSkins[i]` in the class defaults (the
mesh's own `Textures` array is only a fallback — Deus Ex characters carry none). `DT_Sprite` → the
`Texture` default's image — **read the class's resolved `DrawType`; if it is `DT_Sprite`, the picture is
the resolved `Texture` default's image, reported as-is.** *(Owner ruling, 2026-07-26.)* Probed live on
the tracked packages: `Engine.ZoneInfo` → `Texture'Engine.S_ZoneInfo'`, `Engine.Light` →
`Texture'Engine.S_Light'`, `Engine.PlayerStart` → `Texture'Engine.S_Player'`, all with
`DrawType = DT_Sprite`. Note the property is **`Texture`**, not `Sprite`: `Sprite` exists on
`Engine.Actor` but resolved to `None` on every class sampled.

**There is deliberately NO editor-icon detection, and no `preview_state: editor-icon`.** An earlier
draft marked sprite classes whose `Texture` resolves to an "icon group" and had `prewarm` skip them.
That is deleted for two reasons. First it does not work: measured against tracked `uned/UED22/Engine.u`,
**28 of its 32 texture exports are GROUPLESS** — `S_Weapon`, `S_Camera`, `S_ZoneInfo`, `S_Ambient`, … —
and the only groups present are fonts, so a group pattern matches nothing and every sprite class would
have been silently reported `ok`. Second, and decisive: deciding that a lightbulb glyph "tells an agent
nothing" is the tool **inferring meaning**, which §0 forbids. That glyph genuinely *is* what the class
looks like in the editor. The tool produces the picture; the LLM looks at it and decides it is an icon
and worth little. The only name-based alternative (the `S_` prefix) is exactly the name guess
`direction/conventions.md` rejects for class questions.

`DT_Brush`/`DT_None` → `preview_state: no-mesh` (an honest "no artifact exists", not a judgement).

**`--out DIR` file naming.** `<ref>` with dots replaced by `-`, casefolded, plus the angle for multi-angle
kinds: `coretexmetal-ladder-ladrbrwnmetal.png`, `deusexdeco-barstool-iso.png`. Dots are the ref separator so
they cannot survive into a filename unambiguously; casefolding matches the shard paths (§3b) and refs
resolving case-insensitively everywhere else. A collision after that transformation **exits 2 naming both
refs** rather than overwriting — `--out` writes where the user asked, so `direction/safety.md`'s
never-clobber rule applies to it exactly as to any other destination.

**`sound preview` does not exist in phase (a).** Its artifact is the spectrogram, which is phase (b) work
behind the `.uax` decode spike, and music's precedent is that a verb with nothing behind it should not
ship. So phase (a)'s `sound` family is `list`/`search`/`show`/`classify …`/`tags`, and `preview`/`prewarm`
arrive with phase (b).

**Cost shapes the design:** ~254 ms flat / ~332 ms textured at 256 px per render (~75/109 ms at
128 px); mesh *decode* is only ~2–13 ms — the rasterizer dominates. Hence decisions 7 and 11.

**Invalidation stores tuples, not refs.** A thumbnail depends on the class's `.u` *and* every skin
package it references, but the index filename carries only one file's stat identity. The row stores
the contributing packages' `(realpath, size, st_mtime_ns)` in `deps`, re-stat'd on read (~5 µs each).
Without this, a changed texture package leaves the `.u`'s index valid while its thumbnail is stale.

**Two small engine questions to settle during the build:** whether any placeable actor overrides
`DrawType` per-instance (the adapter assumes the class default is authoritative), and which animation
frame is characteristic (thumbnails use frame 0; an `Idle` sequence's `StartFrame` may read better).

---

## Corpus scope for this arm

### 4a. Corpus scope rules (measured, not assumed)

---

## Test coverage — class arm

Read `dev/docs/rules/tests.md` first. Offline fixtures for this arm are the **34 git-tracked `.u` packages**
under `uned/UED22/` (`DeusEx.u`, `DeusExDeco.u`, `Engine.u`, `Fire.u`, `core.u`, …). A synthetic `.u` is
NOT available (a hand-built class package with a mesh would be a slice in itself), and this arm does not
need one.

- **Class facts:** `class show` reports bbox/collision/pivot; `class list` stays offline and maps-free;
  thumbnail invalidation on a **skin package** change, not just the defining `.u` (the row's `deps` must
  carry every contributing package's stat tuple, including the class-defaults package).
- **Defaults in `show`:** `Engine.ZoneInfo.AmbientBrightness` reports `= 0` — the regression that cost an
  agent over an hour — asserted against tracked `Engine.u`, no install needed (verified: 282 defaults
  resolve, `AmbientBrightness = 0`). A property with no default reports its type's zero **marked as such**,
  never blank. A class declaring **zero own properties** emits the `--depth all`/`--category` hint instead
  of an empty list.
- **Provenance is a BUILD CHOICE, and the test list must match it.** `uprops.resolve_class_defaults`
  returns `dict[(casefold, idx)] -> rendered str` and **discards** which ancestor supplied the value. So
  either implement provenance (a change to a shared function's contract, not an output tweak) and test
  "an inherited default names the class it came from", or drop that promise and drop the test. **Do not
  ship the promise untested.**
- **Previews:** `DT_Mesh` renders; `DT_Sprite` reports the resolved `Texture` default's image as-is;
  `DT_Brush`/`DT_None` → `preview_state: no-mesh`. `list`/`search` **never render** (a cold
  `class list --json` completes producing no artifact).
- **`is_placeable` honesty:** whichever branch is taken (state fail-open in the help, or make the
  undeterminable case raise), a test pins it. It is currently
  `descends_from(Actor) and is_abstract() is not True` — **fail-open**.

## Sequencing

1. **Prerequisite: `schema_cache` v2** (engine spec §11.1) — persists resolved class defaults. Gates this
   arm: `DrawType` is default-sourced, so without it every cold `class list --json` re-resolves
   corpus-wide (~14.6 s measured).
1b. **Prerequisite: FULL NATIVE TEXTURE DECODE** —
   board item `three-design-calls-the-native-texture-formats`, the texture arm's
   prerequisite 2. **It gates TEXTURED mesh previews in this arm, which the split originally failed to
   declare.** A `DT_Mesh` thumbnail is textured from the class's `MultiSkins[i]`, so it runs the *same*
   texture decoder as the texture arm — the spike's `render_class.py` builds a
   `utexture.TextureResolver` for exactly this. Today's decoder is P8-only, and that prerequisite exists
   because non-P8/`CompMips` textures are invisible (**30 in this project's own `LUM_CoreTex.utx`**). So
   without it, some classes would render with a missing or wrong skin.

   **A skin that cannot be decoded is an ERROR, not a degraded picture.** *(Owner ruling 2026-07-26.)*
   `class preview <ref>` is a **per-ref request**, so per `direction/asset-catalog.md` "Produce the
   picture, or a named error — never a wrong pixel" it **exits 2 naming the class AND the offending skin
   ref** — it does not flat-shade, substitute, or silently omit the texture. That doc's reasoning is the
   whole point: "a guess that returns a plausible-but-wrong image is worse than a refusal, because nothing
   downstream ever re-checks it", and an agent classifying from a wrongly-skinned thumbnail writes a
   description that is wrong forever.

   The same doc's disposition rule sets the other two cases, and they are **not** exceptions to the ruling
   — they are what "per-ref" is distinguished from: **enumeration** (`class list`) records the row as
   `undecodable` and keeps listing, and a **batch** (`class preview -`) reports the failing refs and their
   skins and exits non-zero, rather than dying on the first.

   *Ordering consequence:* the untextured parts of this arm (`list`, `show`, defaults, facts, `DT_Sprite`
   previews, `DT_Brush`/`DT_None`) do **not** need this and can ship first. Only textured `DT_Mesh`
   rendering waits.
2. Class adapter: enumeration + file facts.
3. `class list`/`class show` on the new engine, including the resolved defaults and the empty-own-props hint.
4. `class preview` (mesh render productised from the spike) + the size/collision/pivot facts.

## Open items for this arm (ordinary, not blocking)

- **`class list` has no unrooted corpus listing.** `classindex.list_classes` documents "there is no
  unrooted 'every class' path — the faithful full dump is `subclass_of=Core.Object, include_abstract=True`",
  and bare `--flat` returns the ~40 direct children of `Engine.Actor`. So the engine spec's
  "`list` = the deterministic corpus listing" is **not meetable for `class` as the verb stands**. Decide in
  this arm: give `class list` an explicit corpus mode, or state the asymmetry and make
  `--classified`/`--unclassified` require it. Also `--include-abstract` currently **raises** unless
  `--flat` and (`--subclass-of` or `--package`), which the new flags must not trip.
- **`class list --package` is placeable-filtered**, so `classify status`'s denominator and
  `list --unclassified`'s corpus disagree. Pick one and say which.
- **Editor-icon detection is DELETED** (owner ruling 2026-07-26): no `preview_state: editor-icon`, no
  icon-group config. Any surviving reference in an older plan slice is stale.

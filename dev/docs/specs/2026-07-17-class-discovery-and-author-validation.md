# Offline class discovery + qualify-and-validate on ingest (classes + textures)

**Status:** SPEC (not built). Revised 2026-07-17 after the review gate (two cold reviewers) + two
rounds of Andrzej decisions. Closes the 2026-07-17 audit's `[implement] p1 No offline actor-CLASS
DISCOVERY` gap (+ its texture-ref twin): an agent on the offline CLI must be able to ask "what can I
place, and what props does it take?" and must be told **at author time** — not 30 s into a Docker
materialize — that a class or texture ref does not exist.

Decisions (+ rejected alternatives) live in [`decisions.md`](../decisions.md) 2026-07-17; this spec is
ephemeral scratch.

## The unifying idea: an OFFLINE class index
Everything here is powered by one new offline structure — a **class index** built by scanning the
composed package search path (`config.composed_search_files`, `.u` files only) and enumerating each
package's UClass exports:

- `bare_to_fqcn: dict[str, set[str]]` — bare class name → the set of `Package.Class` that define it
  (a 2+ set is a cross-package collision). **This is the offline analogue of the live
  `OBJ LIST CLASS=Class` map that `qualify.parse_loaded_classes` builds today — same SHAPE, but NOT
  the same CONTENT:** the live map lists only LOADED classes, the offline index lists EVERY class on
  disk (Part 2's ambiguity policy handles the divergence). So the ingest helper *mirrors*
  `qualify.qualify_level_classes`'s zero/2+ decision logic against this index — it does not literally
  reuse that `Level`-based, `ValueError`-raising function (see Part 2).
- `by_package: dict[str, list[str]]` — package → its class names, for `class list --package`.
- Lazily: a class's abstractness and Super (for `--subclass-of` / placeable / `class show`).

The index is built once per CLI invocation (each invocation is a fresh process). For the discovery
verbs it needs the full parse (properties, ancestry); for **ingest** qualification/existence it needs
only the name/import/export tables (a **header-only scan** — see Part 2's cost note). It backs THREE
things previously imagined as separate: the discovery verbs, class validation, and **offline
bare→FQCN qualification on ingest** (so newly-stored trunk T3D is fully qualified without a live
editor).

New module `uedctl/classindex.py` (or fold into `qualify.py` beside `qualify_level_classes`); a small
`uprops.iter_classes(pkg) -> list[str]` and `uprops.class_is_abstract(pkg, name) -> bool | None`
back it.

## Part 1 — Discovery verbs (a new top-level `class` namespace)
Two read-only, fully-offline, no-editor verbs (a new top-level namespace, symmetric with `texture
list`/`search`, generic-UE1 framed — NOT under `actor`, which reads oddly beside the generator verbs,
nor `substrate`, which is build utilities). All flags carry a real `help=` (CLAUDE.md).

- **`class list [--flat] [--package P] [--subclass-of Package.Class] [--depth N] [--all]`** —
  **UPDATE (decisions.md 2026-07-18 10:56):** the DEFAULT is now an indented inheritance TREE
  (`--flat` gives the pipeable one-per-line list below). The flat browse (Andrzej 2026-07-17: a flat
  ~1200-class dump is unusable) is what `--flat` produces — one `Package.Class` per line, sorted by
  package then name.
  - **Default = the CATEGORIES:** the ~40 direct `Engine.Actor` children (`Engine.Light`/`Decoration`/
    `Mover`…), abstract branch-points INCLUDED (they're the drill targets). Depth 1.
  - **`--subclass-of X`** drills: the PLACEABLE classes that are/descend from X (the leaves), any depth. An
    `--subclass-of` naming a missing class → clean exit-2 "unknown --subclass-of class". The old "all placeable, flat"
    is `--subclass-of Engine.Actor`.
  - **`--depth N`** = a structural browse N levels below the root (Actor, or `--subclass-of`'s class),
    un-filtered (`--depth 1` = that root's direct children).
  - **`--package P`** = all placeable classes in P (lifts the depth-1 default).
  - **`--all`** = every class flat (abstract + non-Actor); composes with `--subclass-of` (all descendants) and
    `--package`.
  - **Placeable is a PROXY, documented as such.** UE1 has no `CLASS_Placeable` flag (that's UE2+), so
    "non-abstract Actor descendant" is the best offline signal — but it over-lists classes nobody
    hand-places (weapons, ammo, projectiles, particles, inventory, AI pawns are all non-abstract
    Actors). The help text + docs say the list is "classes technically instantiable as actors," not
    "classes sensible to place." Curated placeability is the deferred annotated-catalog's job
    (below). *(Flagged to Andrzej in the review; kept as the proxy — no better offline signal exists.)*
- **`class show <Package.Class> [--all]`** — a header line (class, Super chain, `abstract`/
  `placeable`), then the class's EDITABLE properties grouped by editor CATEGORY (UnrealEd's property-
  browser view). Each prop: `name: kind` (`[N]` when `array_dim>1`), enum values for a local-enum
  `ByteProperty`. A prop's `Prop.category` is decoded from the `.u` (RE'd 2026-07-18): explicit
  `var(Group)` → a cross-class category, `var()` → the declaring class name (per-class group), plain
  non-editable `var` → NO category, **hidden**. DEFAULT lists only the class's OWN props by category;
  inherited props of an own category collapse to `(+N inherited, from M superclasses)`, and entirely-
  inherited categories fold to one tail `(+TOTAL inherited, in K more categories: …)`; own sections
  capped at a **~60-line budget**. **`--all` EXPANDS** (own + inherited per category; own untagged,
  inherited tagged `← Package.Class` FQCN); **`--depth N`** limits superclass hops, default auto-fit
  ~60 lines (never empty), noting deeper levels omitted.
  A missing class → clean exit-2 naming it. *(Andrzej: 2026-07-17 hide superclass → 60-line budget;
  2026-07-18 group by category UnrealEd-style, hide uncategorized internals, then own-only-by-default
  + collapsed inherited counts. Earlier "DX has no var(Category)" was a decode bug — categories are
  real: 633 Engine, 534 DeusEx.)*

## Part 2 — Qualify-and-validate classes on ingest (stored T3D FQCN going forward)
**Andrzej's directive:** validate at BOTH the generators AND the write boundaries — "include all t3d
input AND output, stash, prefabs, etc.", done DRYly; and **stored T3D is fully qualified
(`Package.Name`)**. Externally ingested T3D (`MAP EXPORT` / hand-authored) uses BARE names
(`Class=Light` — verified in prefabs + fixtures), and `resolve_class_properties` REQUIRES a FQCN
(raises on a bare name). So ingest must **qualify** bare→FQCN, not merely validate.

**Premise correction (review fix — NOT already-true today).** `actor add` performs NO qualification
today (`dispatch.py`), so a bare-class point actor is currently STORED bare — `verify.py`'s own
comment documents that `expected` "may still carry a bare class from any creation path that doesn't
qualify at construction (e.g. `actor add <file.t3d>`)". Only the brush generators
(`make_brush_actor`) store FQCN today. So this establishes the invariant **going forward**, not a
present fact; **existing committed trunks keep their bare classes and are NOT migrated** — they still
materialize correctly because `verify.py` live-qualifies legacy bare classes at H3 (see the H3 note
below). "Stored T3D is FQCN" means "every NEW ingest stores FQCN"; the trunk may be mixed.

**The shared helper (mirrors, does NOT literally reuse, `qualify_level_classes`).**
`classindex.qualify_and_validate_classes(actors: list[Actor], index) -> None` (mutates in place). It
**mirrors** `qualify.qualify_level_classes`'s zero/2+ decision logic against the OFFLINE index but is
its own function: it takes an actor LIST (not a `Level.order`), adds a qualified-existence branch
`qualify_level_classes` lacks, and — critically — raises **`_SelectionExit`** with the user-facing
wording below, NOT `qualify_level_classes`'s bare `ValueError` (which `dispatch()` does NOT catch →
would traceback; review fix). The live `qualify_level_classes` stays as-is for materialize.
- **Bare `cls`** (no `.`): qualify to its `Package.Class`. **0 candidates → exit-2 "unknown class:
  `Light` (not found in any package on the path)". 2+ candidates → see the ambiguity policy below.**
- **Qualified `cls`** (`Package.Class`): **validate existence** — the named package is on the path
  and defines that class (`uprops.class_export_index`, a cheap per-package lookup — NOT the full
  `resolve_class_properties` ancestry union, which would false-report a real class with a missing
  *ancestor* package as "unknown class"; review fix). Missing → exit-2 naming it.

**Ambiguity policy — offline is STRICTER than live, so don't hard-reject (review fix).** The offline
index enumerates EVERY class in EVERY `.u` on the path; the live editor's `OBJ LIST` map lists only
LOADED classes. So a bare name defined in two on-disk packages is offline-ambiguous even when
materialize would load only one and qualify it cleanly — a naive hard-reject would block legitimate,
materializable content at author time. Policy (as built): on a 2+ offline collision, **do NOT
reject** — prefer a single **Engine, then Core** candidate (the overwhelming real case — a bare
`Class=Light` from a `MAP EXPORT` is `Engine.Light`); a collision **among game packages only** (no
Engine/Core winner) is **left BARE** for materialize's live `qualify_live_level` to bind (the trunk
then holds a bare class for that one actor — the legacy-bare case `verify.py` handles). No hard
"qualify explicitly" error is raised for an ambiguity. *(Deliberately simpler than a full composed-
path-order tiebreak: the offline `bare_to_fqcn` is a `set`, and an offline order-pick could store a
package the live editor never binds — leaving it bare is strictly safer and keeps ingest from ever
being stricter/wronger than the build.)*

**Ordering constraint (review fix — load-bearing).** The helper must run **strictly AFTER**
`is_builder_brush` filtering, never before. `is_builder_brush`/`_is_levelinfo` special-casing keys on
the EXACT bare string `"Brush"` (`normalize.py`); qualifying `Brush`→`Engine.Brush` before the filter
would make the transient red builder brush escape the filter and be stored as level content. Today
both ingest sites filter builder brushes at parse time before any qualification — the spec preserves
that: qualify the surviving actor list, after the filter.

**Cost (review fix — a real per-ingest tax).** Qualification + existence need only a package's
**name/import/export tables**, NOT `uprops.load_package`'s full per-property decode (the `class show`/
`--subclass-of` ancestry path needs that; ingest does not). The index build for ingest uses a **header-only
scan** (`iter_classes` + `class_export_index` over the tables) and is **built once per invocation** and
**deduped over the distinct class set** before lookups — so a 100-actor `prefab apply` parses each
`.u` once, not per-actor. Even so, every mutating ingest verb now pays one composed-path table scan
(previously an instant pure-model write); acceptable for a correctness gate, noted honestly.

**Where it runs (all ingest seams; one helper called from each — NOT folded into `LevelSource.save`).**
Qualification is an INGEST concern (must run before storage) and `save()` also fires on pure-edit
verbs (`actor move`, `brush clip`) that introduce no new class — folding it into `save` would
re-scan the index on every trivial no-op mutation. So the helper is called at the ingest verbs that
actually introduce actors:
- `actor add` — qualify/validate every incoming actor's `cls` **before the first write**
  (all-or-nothing; the loop already iterates for name allocation + `validate_brush`), AFTER the
  builder-brush filter. Covers `--target stash/prefab` (same handler).
- `stash capture --from-t3d` — external T3D into a stash.
- `stash apply` / `prefab apply` (`dispatch._apply_set`) — a captured set into the trunk (a cheap
  existence re-check; the set is usually already FQCN, so belt-and-suspenders + covers a hand-edited box).
- `stash promote` — stash→prefab (needs an actor parse it doesn't do today; pure belt-and-suspenders
  since a validated stash is already FQCN — may be dropped as redundant if the parse isn't worth it).
- **Generators** `actor build <Package.Class>` / `brush build --mover-class <Package.Class>` —
  existence-validate at emit (FQCN by construction). *(Consequence, owned honestly: the generators
  become **project-dependent** and are no longer stateless context-free producers — Andrzej chose
  generators-AND-boundaries knowing this. The generator check is REDUNDANT with the `actor add`
  boundary for the common `build | add` pipe; its only unique effect is failing a `build > file` used
  OUTSIDE any project. Existing project-free generator tests must be migrated to supply a project/
  index — called out in the test list.)*

Existing downstream consumers already tolerate both forms (`normalize` uses `cls.rsplit(".",1)[-1]`;
`materialize._short_class` handles bare OR qualified), so a mixed trunk is safe.

### H3 interaction (review fix — my earlier rationale was mechanically WRONG)
I originally claimed "H3 still compares FQCN-vs-FQCN because materialize re-qualifies via
`qualify_live_level`". That is false and would mislead the implementer. What `verify.py` actually
does: it qualifies `got` (the re-exported actual, which UnrealEd emits **bare**) LIVE, and qualifies
`expected` via `qualify_level_classes` — which **SKIPS any class already containing a `.`**. So today,
with a bare trunk, BOTH sides get live-qualified against the SAME loaded set and always agree. Once
ingest stores `expected` as FQCN, `qualify_level_classes` becomes a **no-op on it**, and `expected`
now carries the **offline** pick while `got` carries the **live** pick. If those ever differ (the
editor binds a same-named class from a package the offline disk scan didn't see, or an ambiguity the
two resolve differently), H3 **fails where it silently passed before**.

**Required fix at build (part of this work, not downstream):** at verify, keep reconciling `expected`
even when it is already FQCN — re-qualify it by SHORT name against the live loaded set and assert the
live pick agrees (or canonicalize both sides to the live pick before comparing), so H3 stays
**live-vs-live**, not offline-vs-live. Update `verify.py` + the `qualify_level_classes` skip-on-dotted
accordingly, and update `verify.py`'s legacy-bare comment (it stays the backstop for legacy bare
actors, and becomes a no-op only after the live reconciliation confirms the FQCN pick).

**Load-bearing assumption to assert:** the offline index's package set == the set materialize loads —
both derive from `config.composed_search_files`, so this holds by construction, but the build must
keep them sourced from the same function so the offline pick and the live pick can't drift.

## Part 3 — Texture ref validation (mirror the class site policy)
Andrzej: **mirror the class decision** for textures. So texture-ref validation runs at the same class
of sites — the `--texture` mutation (`brush poly set --texture`) AND the generator
(`brush build --texture`) — plus, per "all t3d input", any brush ingested via `actor add` /
stash / prefab (scan its polys' `Texture=` refs).

**Existence, NOT decodability** (a review fix — `utexture.TextureResolver.resolve()` is a pixel
decoder that returns `None` on a *real* texture it can't decode: non-P8 format, imported palette,
missing mip — hard-failing those would block a legitimate, materializable ref with no escape hatch,
violating the codebase's own "no false reject" principle). The check: a `Texture`-classed export of
that name exists in the resolved package. Note `utexture.textures(pkg)` returns export **indices**
(`list[int]`), so match by mapping each to `pkg.names[...]` and filtering to the `Texture` class — not
a ready name list. A 3-part `Package.Group.Name` matches on the final name (group ignored per
`qualify._strip_group`). A **bare** texture ref → "a Texture of this name exists in ANY package on the
path" (existence tolerates ambiguity — we're not qualifying for storage). Unresolvable → exit-2 naming
the ref. **Skip polys with no `Texture=`** (builders default `texture=None` and `emit` only writes a
`Texture=` when set, so a plain `brush build cube | actor add -` carries no ref — the scan must treat
an absent ref as valid/nothing-to-check, never false-reject it).

**No offline texture QUALIFICATION.** Unlike classes, texture bare→FQCN qualification stays LIVE at
materialize (`qualify_level_textures` — it content-matches against the editor's `OBJ DEPENDENCIES`
dump and has no offline analogue; building one is out of scope). Ingest only *validates existence*;
the stored texture ref keeps whatever form it had (the trunk's textures are qualified at materialize
as today). This asymmetry with classes is deliberate and noted.

## Part 4 — Error surfacing (a review fix: `dispatch()` does NOT catch `SchemaError`)
`dispatch()`'s try/except catches `_SelectionExit`/`_ProjectError`/`LevelSelectionError`/
`ConfigError`/`GeometryError`/editor errors — **not `SchemaError`** (`actor prop` only stays clean
because `_plan_prop_edit` catches it *locally*). So:
- Every new handler (`class list/show`, the ingest validators) raises `_SelectionExit` with a clear
  message for the user-facing "unknown/ambiguous class", "texture not found", "unknown --subclass-of" cases
  (already caught → exit 2, no traceback).
- Add a `SchemaError` clause to `dispatch()`'s except tuple (→ a clean "schema error: …" exit 2) as
  the backstop for an unexpected layout desync in a package on the path, so a corrupt `.u` never
  tracebacks. Covered by a regression test.

**No-project / no-search-path** is a clean up-front exit-2 with a pinned message BEFORE any validator
runs (a review fix — `schema_resolver(None)` and `composed_search_files(None)` take *different* code
paths and messages, so relying on the downstream `SchemaError`/`ConfigError` gives inconsistent
wording and can't distinguish "no project" from "Engine.u absent"). The class/texture ingest
validators share one "cannot validate: no package search path (need a project + games config)"
pre-check.

## Abstract detection (single offline mechanism: ScriptText source)
`class_is_abstract(pkg, name) -> bool | None` parses the class's shipped `.uc` **source** for the
`abstract` modifier. Every class ships a `TextBuffer` (verified 89/89 Engine, 1158/1158 DeusEx, 5/5
DeusExDeco), so ONE path covers all classes — the earlier plan's dual ClassFlags-for-script-free path
is DROPPED (a review fix: the UStruct/UState prefix before `ClassFlags` is variable-length compact
fields, so a constant offset is only coincidentally right for low-index classes; and since source is
universal, the second path is pure surface). Mechanism, verified end-to-end this session:
- Resolve UStruct `ScriptText` → the TextBuffer export; decode its FString. **Body layout (pinned
  live):** `[UObject empty property-list `None` terminator: 1 compact] + Pos:u32 + Top:u32 +
  Text:FString`. The leading `None` terminator is easy to miss — decode from `Pos` directly and you
  land 1 byte short (garbage); with it, the FString length ends EXACTLY at `soff+ssize` (a free
  integrity check). Decoded with the codebase's own `dxpkg._read_compact_index`.
- Strip `//` and `/* */` comments FIRST, then match `\bclass\b(.*?);` with DOTALL (declarations are
  routinely multi-line: `class Pawn extends Actor\n\tabstract\n\tnative;`) and test `\babstract\b`
  (word-boundary — a class/parent whose NAME contains "abstract" must not false-match).
- Confirmed correct across every Engine abstract base (`Actor`/`Pawn`/`Info`/`Keypoint`/`Decoration`/
  `Inventory`/`Weapon`) and concrete (`Mover`/`Light`/`Brush`/`PlayerStart`/`Spotlight`/`ZoneInfo`).
- `None` (neither source nor a usable signal — a future source-stripped substrate) → the placeable
  filter includes it (**fail-open**: better to list a maybe-unplaceable class than hide a placeable
  one; `class show` prints `abstract=unknown`). DX always ships source, so this is forward-compat only.
- **Abstract is per-class-declared, NOT inherited** (`Actor` abstract, its concrete subclass `Light`
  not) — both the source parse and any flag read the class's OWN declaration, so an "abstract via an
  abstract Super" failure mode does not exist. (Noted so a future reader doesn't re-litigate it.)

New UnrealEd facts → `dev/docs/unrealed/` (the TextBuffer body layout incl. the `None` prefix; the
ScriptSize≠on-disk-bytecode-length gotcha that rules out a front-seek to ClassFlags), dated +
evidenced + confidence-tagged 🔬/✅.

## Performance (a review fix — the default path is the costly one)
- `class list` default (placeable) parses EVERY `.u` on the path (Engine, Core, DeusEx, mission/UI
  packages…) + walks Super ancestry + decodes ScriptText per class. That is seconds, not the "<1 s"
  a single-package parse suggested — the "<1 s" claim is removed. `--all --package P` is the cheap
  path. Acceptable for a discovery verb; no cache (schema is cheap+exact — the no-catalog decision).
- Ingest validators build the class index ONCE per invocation and **dedup the distinct class set**
  before lookups (a 100-actor prefab paste must not reload multi-MB `.u` files 100×); one shared
  package cache across the batch. `class_export_index` (existence) not the full ancestry union.

## Robustness: one unparseable `.u` / missing ancestor must not abort everything (review fixes)
`uprops.load_package` raises `SchemaError` on any cursor-to-EOF desync, so a single foreign/quirky
`.u` on the path would crash `class list` and all class validation. Policy: the index build
**skips an unparseable package with a stderr note** (naming it) rather than aborting; validation then
proceeds over the packages that parsed. (A validation MISS caused by a skipped package is
indistinguishable from a genuine miss — acceptable, and the note tells the user which package to fix.)

The `--subclass-of` / placeable Super-walk uses `_super_fqcn` / `resolve_class_properties`, which **raise
`SchemaError` when an ancestor's package is absent from the path** (`uprops.py`). A legitimately
present class with an absent ancestor would abort or mis-filter the discovery verb. Same policy:
during the ancestry walk, a missing-ancestor package is skipped-with-note — the class is kept in the
listing with its ancestry truncated (so `--subclass-of` can still match on the resolvable prefix), never a
hard abort.

## No class catalog (derived verbs only) — annotated catalog is a separate follow-up
Class schema is cheap/exact/deterministic from the `.u` at query time, so a tracked cache buys only
staleness. `class list`/`show` read raw `.u` each call — no `class-catalog/`, no `class sync`. A
separately worthwhile **annotated** catalog (curated description/category/scale/"commonly-used" +
CURATED placeability, which the placeable proxy above only approximates) is knowledge NOT in the
`.u`; it overlaps the audit's `[docs] p2` "no class catalog" item and is boarded as its own follow-up,
to sit ON TOP of these derived verbs. *(Andrzej: derived verbs now, annotated catalog as a separate
follow-up.)*

## Backward-compatibility (a review note)
Making ingest + generators hard-fail changes the exit status of workflows that previously succeeded
by silent-accept: an `actor build`/`brush build --texture`/`actor add` run **without a games config**,
or against a class/texture whose package isn't on the current composed path, now exits 2 where it
silently passed. This is the intended "no-fallback" contract (the same honest cost `actor prop` pays),
but it IS a behavior change — called out here + boarded so it's a deliberate, visible break.

## Suggested build phasing (review recommendation — sequence, don't cut)
The pieces have very different risk. Andrzej directed generators-AND-boundaries, so nothing here is
cut — but landing it in reviewable phases keeps the low-risk gap-closer off the critical path of the
invasive parts:
- **Phase A (low risk, closes the p1 gap):** the offline class index (header-only) + `class list
  --all`/`--subclass-of`/`--package` + `class show`. No abstract detection yet (the placeable default falls
  back to `--all`-style listing until Phase B). Pure read-only, no ingest changes.
- **Phase B:** abstract detection (the ScriptText RE) + the placeable default for `class list`.
- **Phase C (invasive — also the backward-compat break + the H3 `verify.py` change):** qualify-and-
  validate on ingest (Part 2) + texture existence validation (Part 3). This is the part that touches
  many verbs, changes generator statelessness, and must ship WITH the `verify.py` H3 reconciliation
  fix — so it is its own reviewable landing, not smuggled in with the discovery verbs.

## Non-goals
- Class-default (CDO) property VALUES (`uprops` carries types only; a CDO reader enriches `class show`
  later — also wanted for N-4 light participation + the materialize default-omission gap).
- Prop-value validation on `actor build` (existence only; `actor prop` validates values).
- Offline texture QUALIFICATION (stays live at materialize; ingest only validates texture existence).
- A ranked `class search` verb (`class list --package/--subclass-of` + shell `grep` suffices; revisit with the
  annotated catalog).

## Tests / verify
Offline (mock the class index / a fixture `.u` slice, as the schema tests do):
- **Discovery:** `class list` default lists known placeable DX classes and EXCLUDES abstract bases
  (`Engine.Decoration`/`Info`/`Keypoint`) + non-`Actor` classes; `--subclass-of Engine.Mover` movers-only;
  `--subclass-of Engine.Mover --all` includes an abstract mover base; `--package DeusExDeco` narrows;
  `--subclass-of Foo.Bogus` → exit-2. `class show Engine.Light` header shows the Super chain + `placeable`
  and an inherited `(from Engine.Actor)` prop + a `ByteProperty` with enum values;
  `class show Foo.Bogus` → exit-2; no-project → exit-2 pinned message.
- **Abstract unit:** correct for script-free abstract (`Info`), script-free concrete (`Light`),
  script-bearing abstract (`Actor`/`Pawn`), script-bearing concrete (`Mover`); `None` on a synthetic
  source-stripped fixture; the TextBuffer FString length lands at `soff+ssize`; a multi-line +
  comment-bearing declaration parses; a class named `*Abstract*` does not false-match.
- **Class ingest (the HIGH-RISK paths get explicit tests):** `actor add` of genuine editor-style
  **BARE-class** T3D (`Class=Light`) QUALIFIES to `Engine.Light` in the stored trunk (not a false
  reject — the R1 blocker); a **red builder brush** (`Class=Brush`) in the same T3D is still filtered
  out, NOT stored (the ordering constraint — qualify runs after `is_builder_brush`); a bare class
  defined in 2+ on-disk packages resolves by package-precedence (Engine/Core/game) and, if truly tied
  among peer packages, is left bare for live qualification — NOT hard-rejected (offline-stricter-than-
  live fix); a bare/FQCN **unknown** class → **exit 2 (not a traceback — the `ValueError`→
  `_SelectionExit` translation)** naming it, trunk untouched (all-or-nothing across a 14-actor batch).
  Same coverage for `stash capture --from-t3d`, `stash apply`/`prefab apply`, `stash promote`,
  `actor build Foo.Bogus`, `brush build --mover-class Foo.Bogus`.
- **Generator statelessness migration:** the existing generator tests that dispatch `actor build`/
  `brush build` with **no project fixture** must be updated to supply a project/index (they now resolve
  one); assert a valid class still emits and `Foo.Bogus` exits 2.
- **H3 reconciliation (the `verify.py` fix):** a trunk with a NEWLY-qualified `Engine.Light` still
  passes H3 (verify re-qualifies `expected` by short name against the live loaded set, so it compares
  live-vs-live); a legacy **bare** trunk still passes (the backstop path); a synthetic offline-pick ≠
  live-pick case is caught by the reconciliation rather than silently mismatching.
- **Texture:** `brush poly set --texture Bogus.Tex` / `brush build --texture Bogus.Tex` exit-2 naming
  the ref; a real ref passes; a **non-P8 / imported-palette** real texture ref PASSES (existence, not
  decode — the R2 false-reject test); bare-texture existence resolves; no-project → exit-2 pinned.
- **Error surfacing:** a corrupt `.u` on the path → `class list` skips-with-note (not abort); a
  handler `SchemaError` → clean exit-2 via the new `dispatch()` clause (no traceback).

Live: `class list` on real DX returns a sane placeable set (spot-check `StatueLion`/`Vase1`/
`WHFireplaceLog`); `class show DeusEx.<realdeco>` prints real props; `actor build` of a real class
still materializes; an `actor add` of a real bare-class exported T3D round-trips to FQCN and
materializes with H3 passing.

## Docs to update on build (per tool CLAUDE.md)
- `architecture.md` — the `class` namespace + a "Class discovery & ingest qualification" subsection
  near the class-property-schema section; the offline class index; the DRY ingest seam + its call
  sites; the generators' new project-dependence (update the "session-free / no validation" wording);
  the texture existence-check-not-decode note.
- `unrealed/` — the abstract-detection facts (TextBuffer body layout incl. `None` prefix; ScriptSize
  ≠ on-disk length), dated + evidenced + confidence-tagged.
- `decisions.md` — the 2026-07-17 entry this spec links to (namespace; placeable proxy; qualify-and-
  validate-on-ingest reusing `qualify_level_classes` offline; generators-and-boundaries; texture
  existence-not-decode + no offline texture qualification; single source-parse abstract path;
  no-catalog + follow-up).
- `board/` — move the `[implement] p1` class-discovery item to the build queue; add the annotated-
  class-catalog follow-up + the backward-compat behavior-change note to `inbox.md`.

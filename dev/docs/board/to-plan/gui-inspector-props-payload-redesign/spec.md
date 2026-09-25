# GUI Inspector: `/scene` props payload redesign

Follow-up to `gui-inspector-effective-props-search-show-all` (done). That plan's final whole-branch
review found `/scene` ships every selected actor's **full** resolved property tree — including a
fully-resolved `default_value` string for every prop the actor never states — even though most of that
text is identical across every actor of the same class. Measured on real content
(`dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/golden/subset/`, 59 actors): ~40 KB/actor,
2.36 MB for that subset alone. Extrapolated to a full retail level (UNATCO ~1700 actors) that's
~32-68 MB of JSON per Load.

This is v17, after an architecture pivot and four same-day fix rounds (see "What changed, v16 → v17"
and the four "v17 … fix round" sections near the bottom). Every JSON worked example in this document — and, as of the v8 pass, every factual claim about
the real corpus ANYWHERE in the document, prose included — is generated/verified from a script actually
run against
the real corpus (`.venv/bin/python3`, `uned/UED22/*.u`) in the pass that wrote it — not hand-typed —
after the same bug class (a fabricated/wrong detail in a hand-transcribed example) recurred three times
running in earlier revisions. v1's per-leaf `stored_value`/`effective_value` split didn't compose (a design review found
real structural gaps). v2 reframed around normalizing shape everywhere but got the TYPE-identity keying
wrong in one direction (structs) while over-correcting it in another (enums) — both caught by a second,
clean-context review plus the owner's own direct corpus-verification request; v3 fixed the keying
directions but left the struct scheme's own collision risk as an open question needing the owner's
sign-off. v4 closed that (the owner named `outer`-scoping, the same pattern this codebase already ships
for texture identity) but its own corpus verification was contaminated by a real tool-use bug (resolving
a raw name-table index through the function meant for signed object references) — v5 redid that
verification correctly (§1's "Struct/enum type normalization" carries the corrected evidence:
`Vector`/`Rotator`/etc. DO resolve, the real duplicate-name list, the refined omission rule). v5 in turn
had its OWN real gaps, this time in the wire shape itself, not the evidence: it put `default_value` on
the shared, normalized `types` entry (wrong — defaults are per-class, not type-intrinsic; proven below
with `Core.Rotator`'s real, genuinely different defaults on `DeusEx.Karkian` vs `DeusEx.Rat`), had no
wire shape for a static array of plain scalars/enums, had no home in `/scene`'s sparse map for a
STATED `Location`/`MainScale`/`PostScale`, wrongly claimed `uedcli_native` was unavailable to verify
member shapes (it works fine — this venv just needs `.venv/bin/python3`, not the system interpreter),
and its own worked example was wrong (`AlliancesEx`/`AllianceInfoEx` is INHERITED from
`DeusEx.ScriptedPawn`, not locally declared on `Karkian` as v5 claimed). v6 fixed all five — but its
OWN worked example had the identical failure mode on an adjacent property in the same JSON block
(`InitialAlliances`), plus a self-contradiction on whether `types` carries `category`, a missing
exclusion-filter rule for `types` shape, a `null`-category regression, an inconsistent array-default
encoding, and an undefined nested-struct default shape — v7 fixed all six with every JSON block
script-generated, but a review of v7 found the SAME failure mode recurred once more (one array still
1-of-16 entries, no elision marker) plus a `null`-for-the-string-`"None"` encoding bug (17 sites) and a
false PROSE claim (not inside a JSON block, so v7's own methodology never caught it) that `ESheerAxis`
has no real package definition — it does, and that meant two different code paths could key the SAME
real enum two different ways. v8 fixes all three and extends the verification rule to cover every
corpus claim in the document, not just JSON fences (see below). v9 fixes the last four Important,
purely prose-level findings a review of v8 found — no Critical issues, no design changes, the core
mechanism (identity scheme, wire shapes, defaults-per-class split, caching, frontend walk) was already
confirmed correct. v10 fixes 3 further Important findings from a review of v9 (an over-claimed
enum-resolver reachability, folded into the already-known struct-resolver bug as one shared root cause;
a size estimate that named the wrong worst-case package; a missing wire shape for a struct member that's
itself a static array) plus stale line citations — again no Critical issues, no design change. v11 fixes
4 further Important findings from a review of v10, none a design change: the enum-resolver-bug scope
count (29/31, not 30/32); the `SheerAxis` default-canonicalization and key-derivation claims (both
described as free "by construction" when each needs real, new implementation work); a self-contradiction
on whether a member array of enums needs a `types` reference; and one worked example (`iconInfo`) that
elided 6 of 7 identical entries against this document's own established full-list practice. v12 fixes a
real process failure the owner caught directly: the `ETag` design's formula was missing the version
component `schema_cache.cache_key` (the mechanism it explicitly mirrors) already includes, leaving it
genuinely incomplete relative to its own stated precedent — the exact gap an earlier review flagged as
"no version-drift protection" — and the surrounding prose described the formula informally enough
("a sha1 of the same tuples...") to read, to a reader who hadn't traced it against `cache_key`'s own real
code, as a bare stat-tuple rather than the real hash it already was — not what the owner's original
"etag with checksum of .u" instruction called for. Fixed: the exact formula is now spelled out
unambiguously (a real `hashlib.sha1(...)` call, matching `cache_key`'s own code line for line, extended
from one package's stat tuple to every package on the composed search path), with `SCHEMA_CACHE_VERSION`
folded in so a resolver code change invalidates the `ETag` too, not just a `.u` file edit. Also fixed:
§2's `/scene` worked example wrongly restructured `payload.actors` from its real array shape into a
name-keyed object — nothing else in this design proposes that, and every real consumer
(`app.py`/`api.ts`/`App.tsx`/`OrgPanel.tsx`) still expects an array; and §2's `Location=(X=100)` worked
example wrongly said the unstated `Y`/`Z` axes are filled from `types["Core.Vector"]`'s own default —
contradicting the C1 fix `types` entries carry no default at all — corrected to say they're filled from
`Location`'s own class-entry `default_value`, same as every other leaf.

## Current state (what this changes)

`uedcli/effective_props.py`'s `EffectiveProp` union (`ScalarProp`/`EnumProp`/`StructProp`/`ArrayProp`)
carries, on every leaf, both `stored_value: str | None` and `default_value: str` (always resolved via
`propedit.effective_value`, post the Critical-1 struct-member fix). `resolve_actor_props(actor, ctx)`
walks the WHOLE class schema (`ctx.schema()`) unconditionally, for every actor, and returns every
property whether stated or not. `uedcli/serve/scene.py::_build_actors` calls this once per actor and
threads the full tree into `SceneActor.props`, shipped by `/api/session/{session_id}/scene`.

Two frontend behaviors this redesign must not silently regress, confirmed by reading the current code:

- `web/src/panels/effectiveProps.ts::filterOverridesOnly` filters the TOP-LEVEL `props` array only
  (`props.filter(isExplicit)`); `isExplicit` recurses (`members.some(isExplicit)`), so a struct/array
  with AT LEAST ONE explicit member survives the filter — but `Inspector.tsx`'s `PropRow` then renders
  ALL of that struct's members, explicit and defaulted alike (the defaulted ones get the `[data-default]`
  dimming + "default" tag). **So today, the DEFAULT (overrides-only) view already shows unstated struct
  members inline with their real class-default values, for any struct the actor partially states** —
  this is not a "show all"-only behavior. `RotationRate=(Yaw=1234)` shows `Pitch`/`Roll` with real
  default text (`4096`/`3072`) right now, without toggling anything.
- Non-struct/array kinds render a bare `stored_value ?? default_value` (`shownValue`,
  `effectiveProps.ts`).

## Goals

- No resolved shape or default text is sent over the network more than once per class, ever — not
  per actor, not repeated across multiple actors of the same class, not re-fetched across a session.
- The frontend never re-derives a canonicalized display value itself (enum ordinal→name, quote
  stripping) — every value it renders is already in final display form once the shared resolver has
  produced it, regardless of which side (client or server) ran that resolver.
- **The Inspector never shows a spinner for connectivity reasons.** Resolving any class's shape and
  defaults, once the level's referenced packages have loaded, must be synchronous and require no
  network call — the owner's explicit requirement, and the reason v17 moves resolution client-side
  (see "What changed, v16 → v17").
- **One implementation of the resolution algorithm, scoped to the Inspector-props path this spec
  owns** (owner ruling, 2026-09-24): `effective_props.py`'s walk (used by `/scene` today) is
  superseded by the shared core — never a second, separately-maintained port of THAT logic. Other
  class-default consumers already in this codebase (the viewport's radii/`bHiddenEd`/`bDirectional`
  overlays, the CLI's own class-display, the write path's validation) use separate, narrower code
  today and are deliberately OUT of scope here — matching the existing Non-goal below that already
  excludes actor metadata. The owner's stated intent is that these eventually migrate too, once the
  shared core is proven out by this feature — tracked, not committed to, at
  `dev/docs/board/inbox/migrate-radii-bhiddened-bdirectional-and-cli/`. See
  `dev/docs/board/to-spec/shared-rust-core-for-class-schema-resolution/` for this pass's real scope.
- **No regression in which rows appear, how they're grouped, or their explicit/defaulted status.** The
  default (overrides-only) view keeps showing a partially-stated struct/array's unstated members inline
  with real defaults, exactly as it does today. A minor VALUE-FORMATTING correction (see §2 — dequoting
  a raw quoted string) is an intentional, named side effect of moving canonicalization fully into the
  shared resolver (the goal above this one), not something this redesign avoids — stated plainly, not
  hidden as a side effect of something else.
- Struct AND enum type shape is normalized (defined once, referenced by key) — by ONE mechanism, not two:
  both are keyed on the TYPE'S OWN export record (`package.outer.name`, `outer` omitted when absent or
  the trivial `Object` root), never on the referencing PROPERTY's declaring class — verified against the
  real corpus below, no disambiguation fallback needed for either.

## Non-goals

- Not touching `polys`/`geometry_pinned`/actor metadata (folder, labels, sprite, radii) — those aren't
  class-constant, this redesign doesn't apply to them.
- **Not migrating radii/`bHiddenEd`/`bDirectional` (`uedcli/serve/scene.py`'s own, separate
  class-default resolvers) or the CLI/write path onto the shared core** — confirmed explicitly
  (owner, 2026-09-24, same ruling as Goal 4 above): this pass's "one implementation" covers only
  the Inspector-props path `effective_props.py` already owned. TODO, tracked not committed:
  `dev/docs/board/inbox/migrate-radii-bhiddened-bdirectional-and-cli/`.
- Not building the "reset to default" editing action (`dev/docs/board/someday/
  gui-inspector-editing-write-back-for-props/`) — this spec's shared resolver is reusable by that
  future work, but designing the editing flow itself is out of scope here.
- Not adopting msgpack (investigated — see "Transport" below).
- **Not extracting a package to its class-relevant subset server-side** — every requested package
  downloads in full, raw, even an asset-heavy one where only a handful of its classes matter (§0's
  Non-goal). An accepted cost, not an oversight.
- **Not building a persistent (IndexedDB) client-side cache of raw package bytes** — this pass relies
  on ETag/HTTP caching only ("for now," the owner's own phrasing); a persistent store surviving a
  hard refresh with zero network at all stays a later hardening pass, not built here.

## Design

**v17 is an architecture pivot, not a v16 refinement (2026-09-24).** Everything below — every
corpus fact, the `(package, outer, name)` struct/enum identity scheme, the per-class-not-per-type
defaults proof, the canonicalization rules, the `TYPED_FIELDS` handling — stays true and is reused
as-is. What changes is WHO computes it and WHERE (full reasoning: "What changed, v16 → v17" at the
bottom). v16 had the backend resolve every class in a package (Super-chain merge, default decode,
canonicalization) and ship already-resolved JSON. Measured directly, not estimated: that resolution
is real, unavoidable per-class work, not a caching bug — ~25-31ms/class with the existing
persistent props cache warm, ~183ms/class cold — and a real level only uses a small fraction of a
package's classes (28 of `DeusEx.u`'s 1166, in the one real subset measured), so resolving the
WHOLE package eagerly on every request is genuine overwork regardless of caching. The owner's own
reference point settled it: **UnrealEd itself doesn't do this** — it loads a package's raw bytes
fast (parse + link, no resolution) and resolves one class's property grid lazily, only when an
actor of that class is actually inspected, entirely in-process, with nothing to wait on over a
network. **v17 reproduces that architecture**: the backend serves raw `.u` package bytes,
unresolved, ETag-cached (§0); the frontend parses them and resolves one class at a time, lazily, on
first inspection, entirely client-side — synchronously, with no network call, so the Inspector can
never show a spinner for connectivity reasons (the owner's explicit requirement). Doing this
without duplicating the resolution algorithm in two languages needs ONE implementation usable both
server-side (`/scene`'s own route, natively — §1/§2; the CLI and write path keep their existing,
separate code in THIS pass, an explicit scope call, see Goals/Non-goals) and client-side (the
browser can't run Python) — split out as its own item,
`dev/docs/board/to-spec/shared-rust-core-for-class-schema-resolution/`, since it's substantial,
reusable infrastructure this spec depends on rather than owns.

### 0. The raw-file endpoint — the only NEW backend surface this feature adds

`GET /api/package/{package_name}/raw` (route param matching the project's existing `{level_name}`
convention) serves the resolved backing `.u` file's bytes **verbatim** — `Content-Type:
application/octet-stream`, no parsing, no resolution, no JSON.

**Name resolution, stated precisely, not left to guesswork.** `config.composed_search_files`
returns `list[(host_file, provenance)]`, deduped by CASE-FOLDED stem across all five package
extensions it scans (`.u`/`.dx`/`.utx`/`.uax`/`.umx`) — it is a LIST, not a name→path map, and this
route's job is a LOOKUP against that list, never a path join (a join would be a traversal hole;
`t3dtree.check_safe_segment`'s existing convention is the reason this project treats that as a real
concern elsewhere, and this route needs the same discipline). `{package_name}` matches
case-insensitively (`Core`/`Engine`/`DeusEx` in an import table vs. `core.u`/`engine.u`/`DeusEx.u`
on disk — real-corpus casing differs, confirmed by this doc's own `sUserInfo`/`SUserInfo`
case-insensitive-FName precedent). **Only a `.u`-kind match is servable — a name resolving to a
`.dx`/`.utx`/`.uax`/`.umx` file is a clean 404 naming the value**, not served as if this were a
generic package-file endpoint; this route is `.u` bytes for resolution, nothing else, and the
project's own no-silent-half-answers convention means a wrong-kind name fails loudly, not quietly.
A name not on the search path at all is the same clean 404. **This conditional-GET/ETag/304
handling is new code — nothing in `uedcli/serve/` implements it today** (Starlette's own
`FileResponse` already computes a stat-derived ETag and answers `If-None-Match` with a `304` for
free; this route still needs its own real-content-hash `ETag`, per the owner's ruling above, rather
than that default).

**`ETag` is a real content hash, per the owner's explicit instruction — "etag with checksum of
.u," reaffirmed when asked directly whether a cheap stat-tuple would do.** `sha1` of the resolved
file's own bytes (the same bytes the response body sends), NOT a stat-tuple proxy, hex-encoded,
double-quoted per RFC 7232 (`ETag: "<40 hex chars>"`) — a STRONG validator (no `W/` prefix), correct
here since the bytes served are byte-identical whenever the hash matches, not merely
semantically-equivalent. Once `GZipMiddleware` (Transport, below) compresses the response body, the
SAME `ETag` would otherwise label two different byte streams (identity vs. gzip) as equal — pair it
with `Vary: Accept-Encoding` so a cache correctly treats the two encodings as distinct resources,
not a correctness bug this spec leaves implicit. **Genuinely
cheap to keep cheap, not a per-request tax**: computed once per `(realpath, size, mtime_ns)` and
cached in-process (the same `_LOAD_CACHE`-by-stat pattern `upackage.load_package` already uses,
`upackage.py:199-243`) — a request against an unchanged file reuses the cached hash; only a real
content change (a different stat tuple) triggers a re-hash. This is a deliberately different
tradeoff from `schema_cache.cache_key`'s own stat-only key: `cache_key` avoids hashing because its
own docstring argues the hash would cost "about as much as the parse it saves" for a RESOLUTION
cache — but this route does no resolution to save, and the owner wants the `ETag` to be a real
checksum here specifically, not a proxy. `Cache-Control: no-cache` (always revalidate via a
conditional GET, reusing the cached body on a `304`) — the validator is cheap once warm (a
dict lookup, not a re-hash), so "always revalidate" costs a header-only round trip on every repeat
visit, not a re-fetch. **Scoped honestly**: this guarantees freshness ACROSS page reloads/new
sessions — it does NOT mean a class resolved once stays fresh for the rest of a single running
session; §4's own in-memory per-class cache holds whatever it resolved at fetch time for that
session's whole life, by design (re-resolving on every render would defeat the "resolve once,
cache" mechanism the "never a spinner" requirement depends on). A `.u` edit mid-session is not
picked up until the next reload — the same tradeoff v16's own design already had, not a new one
this pivot introduces. No `SCHEMA_CACHE_VERSION` component is needed here (unlike v16's
ETag) — a resolver CODE change no longer affects what this endpoint serves at all, since it serves
raw bytes unconditionally; only a `.u` file edit does, and a real content hash catches that
directly (it also makes moot a separate concern the review raised — a project-overlay swap
changing WHICH file backs a name without its stat necessarily changing: a content hash catches
that unconditionally, no realpath component needed to cover it).

**gzip transport, real measured numbers** (superseding the "70-90%" estimate in the old Transport
section — this is compressing raw binary package data, not JSON, so the ratio is worse but still
substantial): `DeusEx.u` 1.92 MB → 0.38 MB (80% reduction), `Engine.u` 1.24 MB → 0.40 MB (68%),
`Core.u` 0.06 MB → 0.02 MB. §4's real, CODE-filtered fetch closure (the 8 packages a class/struct/
enum-only import walk actually needs, not the 3-package under-count an earlier draft of this
section gave) totals **4.73 MB raw / 1.20 MB gzipped** — a genuinely reasonable one-time-per-session
download. The large,
asset-heavy packages compress far less (`DeusExCharacters.u` 19.2 MB → 13.4 MB, `DeusExSounds.u`
17.6 MB → 15.9 MB — mostly already-packed binary mesh/sound/texture payload, not text) — see
Non-goals below for the accepted cost this creates.

**Non-goal, stated plainly, not smoothed over**: no backend-side extraction of a package to its
class-relevant subset. A level whose actors reference even one class from an asset-heavy package
(e.g. `DeusExCharacters.u`, 4 classes in 19.2 MB) downloads that package's FULL raw bytes to
resolve those classes — an accepted cost for now, per the owner's explicit call ("I'm fine to
download all necessary `.u` fully to the FE"), not an oversight. `Cache-Control: no-cache` means
this is paid once per session per package (not once per class, not once per Level Load after the
first), same amortization argument v16's own ETag design already made for its JSON payload.

### 1. The shared resolver's output contract — struct/enum identity, per-class defaults

This is the data shape the shared Rust core (native + WASM, see the item above) produces for ONE
class — **not** an HTTP response shape (there is no longer a resolved-JSON endpoint; §0 above
serves raw bytes only). One real entry point, not a whole-package batch (an earlier draft of this
spec described a whole-package `resolve_package` call and was corrected — the whole-package-eager
shape is exactly the v16 cost this redesign eliminates; nothing about the shared core requires or
benefits from resolving more than one class at a time):

```
resolve_class(fqcn, parsed_packages) -> {
  "class": {...},                          # this class's own top-level prop list (§3's shape)
  "types": {"<type_key>": {...}, ...}      # every struct/enum type this class's shape references,
}                                           # keyed once even if several members share one type
```

`parsed_packages` is whatever in-memory handle the caller already holds over the packages it
parsed (§4 for the frontend's own fetch-then-parse sequence; `resolve_actor_props`'s own call into
this, below, for `/scene`'s native use — see §2 for how that path gets its packages) — the core
does not re-fetch or re-parse anything itself. **NOT called by the CLI or the write path in this
pass** (Goal 4/Non-goals: that migration is explicitly out of scope, tracked separately at
`dev/docs/board/inbox/migrate-radii-bhiddened-bdirectional-and-cli/`) — an earlier draft of this
section said otherwise in three places and was wrong; this pass's only production native caller is
`resolve_actor_props`, below. An unresolvable class is a caller-visible error (the SAME degrade
convention `resolve_actor_props`
already uses at the per-actor level today, `effective_props.py:208-224`, `_build_actors`'s
notes-collected-then-printed-once pattern — not silently skipped with no signal at all), not a
missing dict key to guess at.

**This same shared core is also `/scene`'s OWN implementation now, not a second one — and the two
entry points are not independent, `resolve_actor_props` is built ON `resolve_class`.**
§2 covers the caching mechanics in full; the contract:

```
resolve_actor_props(actor, parsed_packages) -> (sparse_map, notes)
```

Internally, `resolve_actor_props` calls `resolve_class(actor.cls, parsed_packages)` (the SAME
cached call the frontend also makes, §4) for that class's shape+defaults, then does its own
actor-specific work on top — reading `actor.props`' raw stored text, keeping only the paths
present, canonicalizing each. This is what makes "one implementation" true in substance, not just
in name: the EXPENSIVE half (Super-chain walk, default decode) is shared code, cached once per
distinct class regardless of which entry point asks for it first; only the CHEAP half (which paths
this one actor states) is genuinely per-actor work. `resolve_class` runs BOTH natively (called by
`resolve_actor_props`, for `/scene`) and via WASM (called directly by the frontend, lazily, §4);
`resolve_actor_props` itself runs ONLY natively, by `/scene`'s own route handler — the frontend
never calls it directly (an actor's own stated values arrive already resolved, via `/scene`'s
JSON), so there is no reason to expose it to WASM. `notes` mirrors `resolve_actor_props`'s existing
third return value (`effective_props.py`'s current `resolve_actor_props`, which this design
supersedes) — a whole-class failure note, not a per-leaf one (§2 has the full degrade discussion).
`uedcli/effective_props.py`'s existing Python walk is SUPERSEDED by this, not kept
alongside it — `/scene`'s route stops calling it once this lands.

**`types` is SHAPE ONLY — never `default_value`.** v5 put `default_value` inside `types[type_key]
["members"]`, the entry SHARED across every class/property that references it. This is wrong: defaults
are keyed `(class, property_name, array_index)` — `propedit.edit.effective_value`'s own resolution reads
`ctx.defaults().get((prop_name.casefold(), index))`, always per-CLASS, never per-type. Proof, freshly
verified against the real corpus (`uprops.resolve_class_defaults`, `uned/UED22/DeusEx.u`):

```
DeusEx.Karkian.RotationRate default = (Pitch=4096,Yaw=30000,Roll=3072)
DeusEx.Rat.RotationRate     default = (Pitch=4096,Yaw=65530,Roll=3072)
```

Both are `Core.Rotator`-typed (§ below) — the SAME shared type, genuinely DIFFERENT Yaw defaults. A
`default_value` living on the shared `types["Core.Rotator"]` entry cannot represent both; whichever class
happened to populate it last would silently leak its own default onto every other class using the same
type. §3's worked example below shows the fix: `types` carries shape ONLY — member `name`/`kind`, and —
for a nested struct member — its OWN `"struct_type"` ref (or `"enum_type"` for a nested enum member —
never `category`, see below) — and each CLASS entry's own struct leaf
carries `"struct_type": "<type_key>"` (for shape) **plus its own per-member `default_value`s**, keyed by the
same member names `types[type_key]` names but populated fresh per class. This is genuinely more verbose
than a single shared blob per type would be (one class's own default TEXT is never shared across
classes, by construction — only the SHAPE is) but is exactly what the real data requires; the size
estimate below already only ever counted per-class defaults toward the "still real work, still large"
figure, not toward the part actually eliminated (the reason the whole redesign started: identical
default TEXT and SHAPE repeated per ACTOR of the same class, not per class).

**A `types` entry's member list is filtered through the SAME `_is_excluded_kind` predicate
`_resolve_one` already applies to a class's own top-level walk (`effective_props.py:304`) — never the
unfiltered raw struct shape.** Without this, a shared shape definition could include an
`ObjectProperty`/`ClassProperty`/`PointerProperty`/dynamic-`ArrayProperty` member the Inspector never
renders today, and the frontend (told to walk `types` for shape, §4) would newly render a row for it.
Real, reachable case (script-verified, `uprops.struct_members` against `uned/UED22/Engine.u`):
`Engine.Pawn.FootRegion` (and its sibling `HeadRegion`) is a `PointRegion`-typed property, genuinely
reachable — **`Engine.Actor.Region` is NOT a valid example here and an earlier draft's use of it was
wrong**: `Region` is a COMPUTED key (`normalize._INGEST_NAMES`, `is_computed_key('region') == True`),
so the top-level walk (`effective_props.py:241`) skips it before the struct-shape/exclusion question is
ever reached — `types["Engine.Actor.PointRegion"]` could never actually be emitted FROM `Region`.
`FootRegion`/`HeadRegion` are NOT computed keys (script-verified: `is_computed_key('footregion') ==
False`) and reference the SAME `PointRegion` struct type, same shape, same exclusion. Real, unfiltered
struct shape: `Zone:ObjectProperty, iLeaf:IntProperty, ZoneNumber:ByteProperty` — `Zone` is excluded, so
`types["Engine.Actor.PointRegion"]["members"]` carries only `iLeaf`/`ZoneNumber`:

```json
"Engine.Actor.PointRegion": {
  "kind": "struct",
  "members": [
    { "kind": "int", "name": "iLeaf" },
    { "kind": "byte", "name": "ZoneNumber" }
  ]
}
```

(`PointRegion`'s own struct export has `outer=Actor`, i.e. `Engine.Actor` — the key follows the same
`package.outer.name` rule as every other struct; the key is the same regardless of whether it's reached
via `FootRegion`, `HeadRegion`, or the unreachable `Region`, since all three name the SAME struct type —
only the property used to DEMONSTRATE the filter needed to change.) **33 real property declarations**
have a struct shape containing at least one excluded-kind member — script-verified precisely: deduped by
`(owner, name)`, walking every class's own resolved (own + inherited) property list across every class
declared in `Engine.u`+`DeusEx.u`, counting only declarations that are actually REACHABLE (i.e. not
already filtered by `HARD_REJECT`/`TYPED_FIELDS`/`is_computed_key` before the struct-shape question even
arises — the same reason `Region` itself doesn't count). This filter applies to all 33.

**A nested struct member's own `default_value` mirrors the SAME nesting `types` uses for shape — a
dict-of-dicts, not a flat dict, once a member is itself struct-typed.** Real case, script-verified:
`Core.Scale` (the shape `MainScale`/`PostScale` reference) has a member, `Scale`, that is itself
`Core.Vector`-typed:

```json
"Core.Scale": {
  "kind": "struct",
  "members": [
    { "kind": "struct", "name": "Scale", "struct_type": "Core.Vector" },
    { "kind": "float", "name": "SheerRate" },
    { "kind": "enum", "name": "SheerAxis", "enum_type": "Core.Scale.ESheerAxis" }
  ]
}
```

**Correction from an earlier draft**: `SheerAxis` is `"kind": "enum"`, not `"byte"`. `ClassCtx.enums`
short-circuits to the enum branch whenever a `ByteProperty`'s own `enum_value_names` is populated
(`propedit/base.py:111-112`) — script-verified directly on `Core.Scale`'s real member: `SheerAxis
ByteProperty type_ref=47 type_name=ESheerAxis`, i.e. a `ByteProperty` carrying a real enum type, which
`_resolve_one` always resolves to `EnumProp`/`kind: "enum"`, never a bare `"byte"` leaf — the SAME rule
this design already applies everywhere else (e.g. `sUserInfo.accessLevel`, a structurally identical
enum-typed struct member, resolves the same way). A `types` entry for an ENUM (as opposed to a struct)
carries `"kind": "enum"` and an ordered `"values"` list — the same value-name list `ScenePayload.enums`
used to hold, now normalized the same way struct shape is:

```json
"Core.Scale.ESheerAxis": {
  "kind": "enum",
  "values": ["SHEER_None", "SHEER_XY", "SHEER_XZ", "SHEER_YX", "SHEER_YZ", "SHEER_ZX", "SHEER_ZY"]
}
```

(`Core.u` export #47, real values, script-verified — matches `typedprops.ESHEER_AXIS` byte-for-byte.)
**Field name, per-kind, not a shared generic `"type"`** — matching the ALREADY-SHIPPED `EffectiveProp`
convention this redesign builds on (`uedcli/effective_props.py`'s `EnumProp.enum_type: str`, already
real code, already in `web/src/api.ts`, unaffected by anything else this spec changes): an enum-typed
member or leaf carries `"kind": "enum"` plus `"enum_type": "<enum type key>"`; a struct-typed member or
leaf carries `"kind": "struct"` plus `"struct_type": "<struct type key>"` — the SAME per-kind naming
principle applied to struct that the codebase already applies to enum, not a new invented generic field
(an earlier draft of this design used one shared `"type"` field for both — rejected: it broke the
existing `enum_type` precedent for no real gain, and the discriminant `"kind"` already tells a reader
which specific field name to expect, so there's no ambiguity a shared name would resolve that separate
per-kind names don't already resolve just as well).

**`ESheerAxis` demonstrates the struct-MEMBER-nested case — a top-level, standalone enum leaf (the far
more common shape in real content) needs its own worked example, added here (an earlier draft never
showed one, despite stating the rule in prose).** `Engine.Light.LightType` — real, script-verified
against `uned/UED22/Engine.u`: `kind=ByteProperty`, `type_ref=2663`, `type_name=ELightType`,
`owner=Engine.Actor` (declared on `Actor`, inherited by every `Light`), `category='Lighting'`, real
class default `'LT_Steady'`. `ELightType`'s own type key, resolved the SAME `(package, outer_or_none,
name)` way as every other type in this document — `Engine.u` export #2663, `cls=Enum`, `outer=Actor`
(a Class, resolved via `pkg.name_of_ref`, not a raw name-table lookup on the `outer` field — the exact
bug an earlier investigation in this project's history had to catch and fix) — gives `Engine.Actor.
ELightType`. Full real value list (10 entries, script-verified, matching the ordinals this document's
`/scene` example already uses elsewhere — `1` is `LT_Steady`, `3` is `LT_Blink`):

```json
"Engine.Actor.ELightType": {
  "kind": "enum",
  "values": [
    "LT_None", "LT_Steady", "LT_Pulse", "LT_Blink", "LT_Flicker", "LT_Strobe",
    "LT_BackdropLight", "LT_SubtlePulse", "LT_TexturePaletteOnce", "LT_TexturePaletteLoop"
  ]
}
```

`Engine.Light`'s own class entry for `LightType` — a plain top-level leaf, NOT nested inside any
struct/array. **`default_value` is the ONE field name for a leaf's resolved default, at every kind, with
no exception** — a scalar/enum leaf's `default_value` is a plain string, a struct leaf's is a dict (keyed
by member name), an array leaf's is a list (one entry per index), and the nested combinations already
specified above compose the same way (a dict-of-dicts, a list-of-dicts, etc.) — the KEY never changes,
only the JSON VALUE TYPE varies by what kind of leaf it's describing. (An earlier draft used two field
names, singular `default_value` for scalar/enum and plural `default_values` for struct/array — rejected:
uniformity, a struct's or array's resolved default is still just "the value," the same concept as a
scalar's, so it gets the same field name.) For `LightType`, a plain scalar-shaped enum value:

```json
{
  "kind": "enum", "name": "LightType", "category": "Lighting",
  "enum_type": "Engine.Actor.ELightType",
  "default_value": "LT_Steady"
}
```

`Engine.Brush`'s real `MainScale` default (`uprops.resolve_class_defaults('Engine.Brush', ...)`) is
`(Scale=(X=1,Y=1,Z=1),SheerRate=0,SheerAxis=0)`. **This is a real, NEW visible-value change this
redesign introduces, not something that falls out for free — say so plainly, per the Goals section's own
commitment to name every intentional value-formatting correction (it already names the dequote case).**
Script-verified directly (run `_resolve_typed_fields` today against a real `Engine.Brush`-descended
actor): `MainScale.SheerAxis`'s `default_value` is the RAW ordinal text `"0"` TODAY, not the canonicalized
name — `_resolve_typed_fields` calls `_member_default(whole_defaults_text, "SheerAxis",
DEFAULT_SHEER_AXIS)` directly and never calls `_canonicalize_enum_text`, unlike `_resolve_one`'s own enum
branch (which canonicalizes both `stored_value` and `default_value`). So today, an actor with a partially-
stated `MainScale` that leaves `SheerAxis` unstated shows the literal text `"0"` in the Inspector; under
this redesign (which requires every enum value to arrive already-canonicalized, per Goal 2) it would show
`"SHEER_None"` — an intentional, named correction, not a side effect of something else. **The
class-schema-only variant of `_resolve_typed_fields` therefore needs an explicit NEW step here** (calling
`_canonicalize_enum_text` on the `SheerAxis` default, ordinal `0` → `"SHEER_None"` via
`uedcli/typedprops.py`'s `ESHEER_AXIS` tuple, index 0) — real implementation work this variant adds, not
a subtraction of existing logic. `Engine.Brush`'s class entry for `MainScale` therefore carries (after
this new canonicalization step, not before it):

```json
{
  "kind": "struct", "name": "MainScale", "category": "Brush", "struct_type": "Core.Scale",
  "default_value": {
    "Scale": { "X": "1", "Y": "1", "Z": "1" },
    "SheerRate": "0",
    "SheerAxis": "SHEER_None"
  }
}
```

— `default_value["Scale"]` is itself a dict, keyed by `types["Core.Vector"]["members"]`'s own member
names, exactly mirroring the shape tree's own recursion.

**A struct MEMBER that is itself a static array — a real, reachable case with no wire shape until now.**
`_resolve_one`'s `array_dim > 1` check runs BEFORE the struct-member walk specifically to handle this
("a member's own array", `effective_props.py:306-312`) — it already resolves correctly today, but the
new `types`/`default_value` shape above only ever showed a member that's a PLAIN scalar or a nested
STRUCT, never a member that's itself an ARRAY. Real case, script-verified (`uned/UED22/DeusEx.u`):
`DeusEx.DamageHUDDisplay.iconInfo` (`sIconInfo[7]`, `outer=DamageHUDDisplay`) has a member `DamageType`
that's a `Name[3]` — an array of plain scalars — alongside a nested-struct member (`Color`, itself
`Core.Color`-typed, `outer=Object` → omitted → key `Core.Color`) and an excluded member (`Icon`,
`ObjectProperty`, dropped by the same filter §1 already applies):

```
export #662 sIconInfo, outer=DamageHUDDisplay, real members:
  DamageType: NameProperty, array_dim=3
  Icon:       ObjectProperty (excluded, dropped from types)
  bActive:    BoolProperty
  initTime:   FloatProperty
  hitDir:     FloatProperty
  bHitCenter: BoolProperty
  Color:      StructProperty, type Color (Core.u #536, outer=Object -> Core.Color)
```

**Fix**: a `types` member entry can carry its own `array_dim` (mirroring how a top-level array leaf
already does), and — if the array's own element type is itself a struct — its own `element_type` ref,
the same way a top-level array-of-struct leaf's `element_type` already works. **A member array of plain
SCALARS (int/float/bool/byte/name/string — no shared type-shape to normalize) needs only `array_dim` +
`kind`, no type reference at all — but a member array of ENUMS still needs `element_type` (a reference
into `types`), exactly like a top-level array-of-enum leaf already requires, because an enum's value
list IS type-intrinsic shape worth normalizing, unlike a bare scalar.** (An earlier draft of this
paragraph wrongly lumped "scalar/enum elements" together as needing no type ref at all — that directly
contradicted the enum-always-carries-a-type-ref rule established elsewhere in this document; the correct
split is scalar-no-ref / enum-yes-ref, not scalar-and-enum-no-ref.) The class entry's `default_value`
nesting extends the same way regardless of element kind: a member that is itself an array (whether its
elements are struct, enum, or scalar) becomes a LIST in `default_value` (one entry per its own
`array_dim`, the SAME full-list-no-collapsing rule as everywhere else in this document), not a flat
value or a nested dict.

```json
"DeusEx.DamageHUDDisplay.sIconInfo": {
  "kind": "struct",
  "members": [
    { "kind": "name", "name": "DamageType", "array_dim": 3 },
    { "kind": "bool", "name": "bActive" },
    { "kind": "float", "name": "initTime" },
    { "kind": "float", "name": "hitDir" },
    { "kind": "bool", "name": "bHitCenter" },
    { "kind": "struct", "name": "Color", "struct_type": "Core.Color" }
  ]
}
```

(`Icon` is genuinely absent — `ObjectProperty`, filtered by the same `_is_excluded_kind` rule §1
already applies.) `DeusEx.DamageHUDDisplay`'s own class entry for `iconInfo` (real defaults,
script-verified — all 7 array slots share this same all-defaulted default text):

```json
{
  "kind": "array", "name": "iconInfo", "category": "Uncategorized",
  "element_type": "DeusEx.DamageHUDDisplay.sIconInfo", "array_dim": 7,
  "default_value": [
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } },
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } },
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } },
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } },
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } },
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } },
    { "DamageType": ["None", "None", "None"], "bActive": "False", "initTime": "0",
      "hitDir": "0", "bHitCenter": "False", "Color": { "R": "0", "G": "0", "B": "0", "A": "0" } }
  ]
}
```

(all 7 of `iconInfo`'s indices are real, script-verified, and genuinely identical in this class — all 7
listed in full, no elision, matching this document's own established practice everywhere else — an
earlier draft of this example elided 6 of the 7 with no real justifying convention, which this document
does not otherwise have; every other array example, including a longer 16-entry identical list
[`AlliancesEx` above] and a 50-entry list [`WeaponPriority` below], is already shown in full, per the
same no-run-length-collapsing rule stated below.) `default_value[i]["DamageType"]` is itself a
3-element list (`DamageType`'s own `array_dim`),
and `default_value[i]["Color"]` is a dict keyed by `types["Core.Color"]["members"]`'s own names — both
nesting rules composing at once, exactly as the shape tree itself does.

This closes the WIRE-SHAPE gap an earlier draft
left open for `MainScale`/`PostScale` specifically (§'s typed-fields paragraph below) — it does NOT make
`TempScale` itself resolvable; that's a separate, still-open RESOLVER bug (Open Questions), unrelated to
whether a wire shape exists for the data once resolved. `MainScale`/`PostScale` reach `Core.Scale` via
the `TYPED_FIELDS` special-case path (`_resolve_typed_fields`), which never hits that bug at all;
`TempScale` reaches the SAME struct type via the generic `ctx.schema()` walk, which does.

Each class entry is therefore the class's own top-level prop list. **Its ORDER is normative, not
incidental — a review found this unstated and flagged it as a real regression risk.** The frontend
derives the Inspector's category-group order from first occurrence in this array
(`web/src/panels/groupByCategory.ts`'s own comment: "preserving first-occurrence category order";
`Inspector.tsx`'s `groupByCategory(visibleProps)` over `actor.props` in array order) — and TODAY the
three typed-field leaves (`Location`/`MainScale`/`PostScale`) are unconditionally FIRST
(`effective_props.py:237`, `out: list[EffectiveProp] = _resolve_typed_fields(...)`, BEFORE the
`ctx.schema()` walk starts at `:238`), so `Movement` is always the first group, `Brush` the second. The
class entry's `props` array MUST preserve this exact order — typed-field leaves first, then
`ctx.schema()` walk order — not whatever order an implementer's two separate emitter functions happen
to run in; appending the typed-field variant's output AFTER the generic walk (a natural reading of this
section's own "a second small, contained function" framing below) would silently reorder every actor's
category groups, exactly the regression Goal 3 commits against.

A SCALAR leaf (int/float/bool/byte/
name/string) keeps the familiar `name`/`category`/`kind`/`default_value` shape (no `stored_value`,
nothing here is actor-specific, and no type-reference field at all — a plain scalar genuinely has no
shared shape to normalize). An ENUM leaf is NOT a scalar for this purpose — it carries `"kind": "enum"`
PLUS `"enum_type": "<enum type key>"` (a reference into `types`, using the SAME field name this
codebase's already-shipped `EnumProp.enum_type` already uses, not a newly-invented generic name)
alongside its own `name`/`category`/`default_value` — the enum's VALUE LIST is exactly the type-intrinsic
shape being normalized, the whole reason an enum `types` entry exists at all; treating it like a plain
scalar (no type-reference field) would contradict that. A struct-typed leaf carries `"struct_type":
"<type_key>"` (shape, from `types`, the parallel per-kind field name — see the `Core.Scale` example
above for why this design uses per-kind field names rather than one shared `"type"`) plus its own
per-member `default_value`s (this class's own defaults, never shared); an array-of-struct leaf carries
`"element_type"` (shape, from `types`) plus its own per-INDEX member defaults (§3); an array-of-ENUM
leaf likewise carries `"element_type"` (the enum's own `types` key) plus a plain per-index
`default_value` list (no static array of enums was found in the real corpus scanned so far — the shape
is specified for completeness, not because a real worked example exists yet). **Correction from an
earlier draft**: neither array-of-struct nor array-of-enum carries an `element_kind` sibling field — that
field exists ONLY on the array-of-plain-SCALAR leaf (below), where there's no `types` entry to ask
instead. An `element_type`-bearing array has NO on-leaf discriminator for whether its elements are
struct or enum; the frontend must resolve it indirectly via `types[element_type]["kind"]` (`"struct"` or
`"enum"`) — stated explicitly in §4's walk, not left implicit. An array-of-plain-SCALAR leaf (no shared
type at all — see the sub-bullet below) carries `element_kind` plus a plain list of per-index
`default_value`s. This is a REAL structural change from today's `EffectiveProp`'s
`StructProp`/`ArrayProp` shapes (an earlier draft said "the same shape minus `stored_value`," which was
inaccurate) — struct/array shape moves to `types`, but per-class DEFAULT VALUES stay on the class entry
itself, never shared. `category` also does NOT live on a `types` entry (a struct type's own members have
no single category — `Core.Vector` is referenced by `Engine.Actor.Location`/`Velocity` at category
`"Movement"` AND by `Acceleration`/`PrePivot`/`ColLocation` at `Uncategorized`, same class, same shared
type, different top-level property categories (`OldLocation` is ALSO a `Core.Vector` reference on this
class, but it's a computed key — `is_computed_key('oldlocation') == True` — so it's unreachable, same
reason `Region` doesn't count above, and dropped from this list) — `_resolve_one` threads the TOP-LEVEL prop's
own category down to every member uniformly, `effective_props.py:331`/`:336`/`:353`); `category` stays on each
CLASS entry's own leaf only, matching where it's actually resolved today.

**Static array of plain SCALARS — a real wire shape this spec previously never defined.** No shared
`types` entry applies here (a plain scalar — int/float/bool/byte/name/string — genuinely has no shape
worth normalizing, only its VALUE varies; an array of ENUMS is a DIFFERENT case, see the leaf-shape
paragraph above — it DOES reference a shared `types` entry, the same as a scalar enum leaf does).
Verified real example, `DeusEx.DeusExPlayer.WeaponPriority` (a `Name[50]` array, real per-index class
defaults, freshly decoded):

```
[0] Airblast2   [1] hellsaw   [2] MediGun   [3] Translocator   [4] SuperShockRifle   ...
[37] WarheadLauncher   [38..49] None (12 entries, real, not filler)
```

Wire shape (script-verified against the real property, `.venv/bin/python3`,
`uprops.resolve_class_properties('DeusEx.DeusExPlayer', ...)`: `WeaponPriority`'s real `category` is
`None`, which renders as the string `"Uncategorized"` on the wire — never JSON `null`, matching
`_category_for`'s own real fallback and closing the "category: null breaks grouping" gap found in
review, below):

```json
{"kind": "array", "name": "WeaponPriority", "category": "Uncategorized", "element_kind": "name",
 "array_dim": 50, "default_value": ["Airblast2", "hellsaw", "MediGun", "Translocator",
 "SuperShockRifle", "python", "ChainSaw", "ImpactHammer", "CompoundBow", "Flamer2", "Tomahawk",
 "Pipebomb", "GoldenGun", "Shrinker", "G4eWgreen", "M16", "enforcer", "Zapper2", "U4eShotgun",
 "G4eWgold", "G4eWNailbomb", "XDisc", "QuickSilver", "PlasmaCannon", "Freezer", "doubleenforcer",
 "Phasor", "ShockRifle", "ut_biorifle", "Railgun2", "FleshBombRifle", "PulseGun", "SniperRifle",
 "ripper", "minigun2", "UT_FlakCannon", "UT_Eightball", "WarheadLauncher", "None", "None", "None",
 "None", "None", "None", "None", "None", "None", "None", "None", "None"]}
```

50 real entries, none elided — indices 38-49 are genuinely `"None"` (not filler), matching the same
per-class default resolution as every other leaf.

`element_kind` matches today's `ArrayProp.element_kind` field (`effective_props.py`), `default_value`
a plain list, index = list position (the class-schema tree's own array description is never sparse —
only `/scene`'s per-actor overlay is, § below). **`category` is never JSON `null` anywhere on the wire,
in any leaf, from either resolver entry point** — a `None`-categorized property renders the literal string
`"Uncategorized"`, exactly matching what `_category_for` already returns today and what
`groupByCategory.ts`'s non-nullable `category: string` field on `EffectivePropBase` already requires
(review finding I2: a raw `null` would form its own group and silently diverge from today's grouping).

**Where this walk is implemented — pointer, not detail, per this spec's v17 scope split.** The
existing Python walk (`resolve_actor_props`/`_resolve_one`, `effective_props.py`) is the reference
implementation this behavior must match exactly (its `actor`-consuming leaf calls simply don't run
for a class-only resolve — `_resolve_one` already threads `actor` only into two leaf calls, nothing
structural above them depends on it). But the walk that actually SHIPS for this feature is the
shared Rust core's port of that logic (native + WASM, `dev/docs/board/to-spec/
shared-rust-core-for-class-schema-resolution/`), not a new Python sibling function — a Python-only
`resolve_class_schema` would still leave the browser with nothing to call. The Python loader
contract's existing gap (`ClassCtx`'s `load_members`/`load_enums` return shape only, never the
resolved type IDENTITY `uedcli/serve/scene.py`'s `_struct_members_via` already computes and
discards) is real implementation surface, but it belongs to the port, not to this spec — recorded
there, not re-derived here.

**`Location`/`MainScale`/`PostScale` are a real special case, not covered by the generic walk above —
say so plainly, don't imply otherwise.** `_resolve_typed_fields` (`effective_props.py:115-178`) builds
these three from `model.Actor` fields directly via `propedit.TYPED_FIELDS`, never from `ctx.schema()`.
Their TRUE class defaults, though, come from `ctx.defaults()` alone (`_member_default`,
`loc_defaults_text = ctx.defaults().get(("location", 0))` etc.) — no actor state needed for that half.
The shared resolver emits these three via a class-schema-only variant of `_resolve_typed_fields`
that skips `_stated_axes`/`tf.get(tok, actor.location)` (the actor-touching calls) and keeps only the
`ctx.defaults()`-derived member defaults — a second small, contained function, not something the generic
struct walk can absorb. `Location`'s own struct SHAPE is not a private copy: it references the SAME
`Core.Vector`-keyed `types` entry any other real `Vector`-typed schema property in the response would
use (`Rotator`'s own sibling in `Core.u`, not `Engine.u` — corrected from an earlier draft's
`Engine.Vector`, § below) — one shape, one definition, referenced from both places; `Location`'s own
CLASS-entry leaf carries its own `default_value` per axis, same C1 fix as every other struct leaf.
`MainScale`/`PostScale`'s `SheerAxis` member references `types["Core.Scale.ESheerAxis"]` (defined
above) — the SAME real, package-derived key any other `Core.Scale`-typed property's own `SheerAxis`
member would resolve to. **Correction from an earlier draft, which claimed `ESheerAxis` "is not a
package export, it's a hardcoded Python constant" — false, script-verified**: `ESheerAxis` genuinely IS
a real `Enum` export, `Core.u` #47, `outer=Scale`, values `('SHEER_None','SHEER_XY','SHEER_XZ',
'SHEER_YX','SHEER_YZ','SHEER_ZX','SHEER_ZY')` — matching `typedprops.ESHEER_AXIS` exactly. What IS true:
`_resolve_typed_fields` (the code path that resolves `MainScale`/`PostScale`) reaches this same real
data via the hardcoded Python constant instead of resolving it from the package — two paths reaching
the same real data, not one real path and one fake one.

This matters because a naive hardcoded key (`"typedprops.ESheerAxis"`) would give the SAME real enum a
DIFFERENT `types` key than the generic schema walk would produce for it — two entries in `types` for
one real enum, breaking the "defined once" goal. Resolved not by special-casing `ESheerAxis`, but by
fixing the general enum-keying rule itself — see below: enums key on their OWN export's `outer`, the
SAME mechanism structs already use, never on the referencing property's owner. Under that rule
`ESheerAxis` gives `Core.Scale.ESheerAxis` (`ESheerAxis`'s own `outer` is `Scale`; `Scale`'s own outer
resolves to `Object`, omitted) — **this key is correct as DESIGN, but does NOT fall out "by
construction" for the `_resolve_typed_fields` path, and the spec should say so honestly rather than
implying it's free.** Script-verified: `_resolve_typed_fields` never calls `ctx.enums()`/
`resolve_type_export` at all — it reads `typedprops.ESHEER_AXIS` (a hardcoded Python tuple) directly and
calls `ctx_by_type.setdefault("typedprops.ESheerAxis", list(ESHEER_AXIS))` (`effective_props.py:133`), so
it cannot "resolve the same real export" the generic walk does; it resolves no export at all. The
class-schema-only variant of `_resolve_typed_fields` needs to be CHANGED to emit `Core.Scale.ESheerAxis`
INSTEAD OF the current hardcoded `"typedprops.ESheerAxis"` string — a real, explicit code change this
path needs (mirroring exactly how the `EHAlign` case just above is honestly framed as a real gap, not
something already working), not something that already happens today.

**Struct/enum type normalization — ONE mechanism for both, keyed on the type's OWN export record,
verified against the real corpus, one open risk flagged (not silently resolved):**

- **Enums — corrected from an earlier draft, which keyed on `f"{prop.owner}.{prop.type_name}"` (the
  DECLARING PROPERTY's owner) rather than the enum's own export.** That scheme happens to give the
  correct answer for the dominant real case — a top-level class property with a locally-declared enum,
  where the enum's own `outer` and the property's own `owner` are the SAME class by construction
  (script-verified: `DeusEx.AlarmLight.SkinColor`'s enum `ESkinColor` has its own `outer` = `AlarmLight`,
  identical to `prop.owner`) — but is WRONG for an enum reached as a STRUCT MEMBER, where `prop.owner`
  is the bare, unqualified STRUCT name, not a package-qualified class. Script-verified against the real
  corpus (`Engine.u`+`DeusEx.u`+`Core.u`): **9 real enum-typed struct members exist**, and for 8 of them
  the enum's OWN `outer` is a CLASS different from the struct itself (only 1, `ESheerAxis`, has a
  STRUCT outer) — e.g. `DeusEx.BarkInfo.barkMode`'s enum `EBarkModes` has its own `outer` = `BarkManager`
  (a class), not `BarkInfo` (the struct declaring the member); `DeusEx.sUserInfo.accessLevel`'s enum
  `EAccessLevel` has its own `outer` = `Computers`. Under the field-owner scheme these would key as bare
  `BarkInfo.EBarkModes`/`sUserInfo.EAccessLevel` — not package-qualified, and a real latent collision
  risk the struct scheme's own `outer`-qualification was introduced specifically to prevent. **Fixed
  rule: an enum is keyed exactly the same way a struct is — `package.outer.name`, `outer` read directly
  off the ENUM'S OWN export record (never the referencing property's `owner`), omitted when absent or
  resolving to `Object`.** This is a genuine simplification (one rule, not a general rule plus a
  special case), not a new mechanism — it produces the identical, already-verified-correct key for the
  dominant top-level case (confirmed above) and the correct, package-qualified key for all 9 real
  struct-member cases (three confirmed directly: `DeusEx.BarkInfo.barkMode` → `DeusEx.BarkManager.
  EBarkModes`; `DeusEx.sUserInfo.accessLevel` → `DeusEx.Computers.EAccessLevel`;
  `DeusEx.S_ActionButtonDefault.Align` → `Extension.ExtensionObject.EHAlign`, `EHAlign`'s own export
  confirmed at `Extension.u` #9, `outer=ExtensionObject`).

  **Correction: the `EHAlign` key is right as DESIGN, but NOT reachable through the real resolution
  path today — a genuine, separate implementation bug, not something this fix already solves.**
  `S_ActionButtonDefault.Align`/`S_BarButton.Align`/`S_KeyDisplayItem.inputKey` are all IMPORTED enum
  members (`type_ref < 0`, so `prop.enum_value_names` is empty and `ClassCtx.enums()` falls through to
  `serve/scene.py::_enum_names_via`, script-verified line-for-line) — and `_enum_names_via` has the
  IDENTICAL bug already named below for `_struct_members_via`: `owner_pkg_name =
  prop.owner.split(".", 1)[0]` treats the bare STRUCT name (`'S_ActionButtonDefault'`) as if it were a
  package name. Run for real, on `S_ActionButtonDefault.Align`'s own decoded `Prop`:
  `_enum_names_via` raises `SchemaError("package 'S_ActionButtonDefault' not found on the schema
  search path")`, exactly the same failure shape as the struct case. This is genuinely REACHABLE, and broader than a handful of
  properties: **every real class with an `S_ActionButtonDefault`-, `S_BarButton`-, or
  `S_KeyDisplayItem`-typed property hits it** — script-verified precisely across the whole corpus (two
  independent methods agreeing: counting real `(class, property, type)` triples, and independently
  walking the inheritance tree from each struct type's one real declaring class): `actionButtons:
  S_ActionButtonDefault` is declared ONCE, on `DeusEx.MenuUIWindow`, and inherited unchanged by **29**
  real classes (`MenuUIWindow` itself plus 28 `DeusEx.u` descendants — `MenuMain`,
  `MenuScreenCustomizeKeys`, `MenuUIMenuWindow`, ... — none of which override it); `S_BarButton` is
  declared once, on `DeusEx.MenuUIActionButtonBarWindow` (1 class, NOT a `MenuUIWindow` descendant, so
  this doesn't overlap the 29); `S_KeyDisplayItem` is declared once, on
  `DeusEx.MenuScreenCustomizeKeys`'s own `keyDisplayNames` (1 class — already counted among the 29 via
  its OWN, different `actionButtons` property, so this is a genuinely distinct property on an
  already-counted class, not a 31st class). **31 real `(class, property)` pairs total** (29 + 1 + 1),
  across **30 distinct classes** (`MenuScreenCustomizeKeys` is the one class hit twice, by two different
  properties) — every one of these properties' `Align`/`inputKey` members degrading to a plain
  `ScalarProp(kind='byte')` today, with no `types` entry to reference at all. This is listed as a known
  implementation-surface gap below, not fixed here — it's the SAME root cause as the already-named
  struct-member resolver bug, just manifesting in the enum helper instead of the struct one.

  Verified against the real corpus for the general (non-struct-member) case too
  (`uned/UED22/DeusEx.u`+`Engine.u`, every enum-typed property decoded directly): `ESkinColor` alone is
  independently declared **28 times** across different classes with **21 genuinely different value
  lists** (`DeusEx.AlarmLight`'s own `SC_Red/SC_Green/SC_Blue/SC_Amber` vs `DeusEx.Bushes3`'s own
  `SC_Bushes1..SC_Bushes4`, etc.) — the unified `outer`-based scheme keeps these correctly distinct (each
  enum's own `outer` is its own distinct declaring class, exactly matching the old field-owner answer
  for this locally-declared case); a package-only scheme (v2's original proposal, keying on
  resolved-identity WITHOUT the owning-class component) would have WRONGLY collapsed all 28 into one
  shared, incorrect definition. **Honest caveat, not swept under the "every enum is local" claim an
  earlier draft made**: of 10,150 real enum-typed properties scanned, 101 (~1%) are genuinely IMPORTED
  at the TOP level (`type_ref < 0`) — e.g. `DeusEx.HUDBaseWindow.borderDrawStyle : EDrawStyle`. The
  unified `outer`-based scheme handles these correctly too (an imported enum's own `outer`, resolved
  cross-package exactly like a struct's, still gives its one true owning class) — this is in fact BETTER
  than the old field-owner scheme for imports, which (like the struct-member case above) could give a
  key relative to the wrong package. Not a new regression either way — today's `ScenePayload.enums` has
  the field-owner imprecision this fix improves on, not one this redesign introduces.

- **Structs**: `f"{package}.{struct_name}"`, or `f"{package}.{outer_class}.{struct_name}"` when the
  struct's own `outer` export field names an OWNING CLASS that isn't the package's own trivial root
  (see the refined omission rule below) — the SAME pattern this codebase already ships for real texture
  identity (`TextureResolver`'s `Package.Group.Name`, group omitted when absent).

  **Confirmed directly against the real corpus — this section replaces v4's evidence, which was
  contaminated by a real tool-use bug** (`Package.name_of_ref` resolves a SIGNED OBJECT REFERENCE, not
  a raw name-table index; calling it on a `Struct` export's own `e['nm']` field — a raw, unsigned index
  — silently returned the wrong string, e.g. reading export #2's `ObjectClass` name for what is
  genuinely a "Rotator" export. The correct resolution is `pkg.names[e['nm']]` directly, or
  `uprops.ufield._safe_name(pkg, e['nm'])`. `name_of_ref` IS correct for `e['cls']`/`e['outer']`, both
  genuinely signed refs — the bug was specific to `e['nm']`.) Redone with the correct function
  (`uned/UED22`, every `Struct`-classed export's own name/outer decoded via plain `uprops.load_package`
  + a walk over `pkg.exports`, no native extension needed for this part): the real duplicate-name list
  in `DeusEx.u`'s own export table is `S_MenuUIBorderButtonTextures` (2: `outer=PersonaBorderButtonWindow`
  vs `outer=MenuUIBorderButtonWindow`), `InitialAllianceInfo` (2: `outer=ScriptedPawn` vs
  `outer=AllianceTrigger`), `sUserInfo` (2: `outer=ATM` vs `outer=Computers`), and `XAIParams` (**9**
  separate exports, each with a DIFFERENT `outer` — `DeusExPlayer`, `ScriptedPawn`, `GeneratorScout`,
  `DeusExMover`, `DeusExCarcass`, `DeusExDecoration`, `DeusExFragment`, `ExplosionLight`,
  `BarkManager`). (v4's cited example, `CarcassName` ×9 with this same owner list, does not actually
  exist under that name — it was this session's own fabricated evidence from the same bug; `XAIParams`
  is the real 9-way case.) Every one of these resolves to a distinct, correct key under
  `package.outer.name` with no runtime collision-detection needed — `outer` is read directly off each
  struct's own export record, not derived or guessed. **This closes v3's open question**: the
  export-index-suffix fallback v3 proposed is not needed; the engine's own scoping disambiguates every
  real case found.

  **`SUserInfo` — the specific case v3 cited — IS reproduced, correctly, once the bug above is fixed.**
  It's spelled `sUserInfo` in the real export table (case-different from v3's citation — UE1 `FName`s
  are case-insensitive/case-preserving, so this is the same name, not a different one). Two exports,
  `outer=ATM` vs `outer=Computers` — resolved cleanly by `outer`, same as every other collision found.
  v4's claim that it "could not be reproduced" was itself a product of the `name_of_ref` bug (the scan
  that reported zero matches was comparing against names resolved the WRONG way). No case was found, in
  this corpus, of two structs sharing BOTH the same name AND the same (or absent) `outer` — if one
  surfaces later, `package.outer.name` would still need a fallback; not expected, not found.

  **`Vector`/`Rotator`/`Scale`/`Plane`/`Color` DO resolve — v4's claim that they couldn't be found was
  the SAME bug, not a real architectural gap.** Verified directly: `Engine.Actor.RotationRate`'s
  `type_ref` (`-11`, relative to `Engine.u`'s own import table since `RotationRate` is declared on
  `Engine.Actor`) resolves via `uprops.resolve_type_export(engine_pkg, -11, 'Struct', ...)` to `Core.u`
  export #2 — whose real name, read correctly, is `Rotator`. **One genuine correction to the owner's own
  worked example**: `Rotator` lives in `Core.u`, not `Engine.u` — the key is `Core.Rotator` (or, see
  below, possibly `Core.Object.Rotator` before the refined omission rule), not `Engine.Rotator`. And a
  second, more important finding: **every genuinely-global struct in `Core.u` has a NONZERO `outer`.**
  Scanned all 9 `Struct` exports in `Core.u`: `Vector`, `Rotator`, `Plane`, `BoundingBox`,
  `BoundingVolume`, `Color`, `Scale`, `Coords`, `Guid` — every single one has `outer` pointing at
  `Object` (export #3, the universal root every UE1 class ultimately descends from), never literally
  `0`. **The "omit `OuterClass` exactly when `outer == 0`" rule as v4 stated it would therefore NEVER
  fire for the flagship case it was designed for** — it would produce `Core.Object.Rotator` for every
  one of these, not the clean `Core.Rotator` the owner's own example wanted.

  **Refined omission rule, to actually match the owner's intent**: omit `OuterClass` from the key when
  `outer` is absent (0) **or** resolves to `Object` (the trivial universal-root scope every top-level
  definition in a package with no meaningful custom owner apparently gets, at least in `Core.u` — this
  generalization is based on `Core.u`'s own 9 structs alone; it should be spot-checked against another
  package's own top-level structs, if any exist, at plan time rather than assumed universal from one
  package's data). Under this rule: `Rotator` → `Core.Rotator` (outer resolves to `Object`, treated as
  "no meaningful scope," omitted); `sUserInfo`(`ATM`) → `DeusEx.ATM.sUserInfo` (outer is a real, specific
  owning class, kept). This is a small, honest refinement of the mechanism, not a re-opening of the
  design — the identity scheme (`outer`-based disambiguation, mirroring texture identity) is unchanged;
  only the precise condition for "no meaningful outer" needed correcting once verified against real
  data instead of assumed.

  **Member-shape verification: DONE in this pass, not a gap.** v5 claimed `uedcli_native` (needed by
  `uprops.struct_members`) was unavailable in every sandbox this spec has been drafted in — false; it's
  installed at `.venv/lib/python3.12/site-packages/uedcli_native/`, importable via `.venv/bin/python3`
  (the system `python3` on `PATH` resolves to a DIFFERENT interpreter with no venv site-packages —
  confirmed directly: `python3 -c "import uedcli_native"` fails, `.venv/bin/python3` succeeds). Run for
  real against `uned/UED22/DeusEx.u`:

  ```
  sUserInfo(ATM)       -> accountNumber:StrProperty, PIN:StrProperty, balance:IntProperty
  sUserInfo(Computers) -> Username:StrProperty, Password:StrProperty, accessLevel:ByteProperty
  ```

  Genuinely different member shapes sharing one name — `outer` disambiguates them correctly, AND (now
  confirmed, not just assumed) their shapes really do differ, vindicating v3's original citation. The
  `XAIParams` ×9 case is the opposite, also confirmed: all 9 exports share one IDENTICAL shape
  (`BestActor:ObjectProperty, Score/Visibility/Volume/Smell:FloatProperty`) — 9 distinct `types` keys
  for one real shape, a genuine (small, known, accepted) redundancy in the normalization the size
  estimate below accounts for, not hidden. `Core.Rotator`'s own members, also confirmed:
  `Pitch:IntProperty, Yaw:IntProperty, Roll:IntProperty` — matching §3's worked example exactly.

**Caching/compute cost — superseded by v17, kept only as a pointer.** Everything this subsection
used to say (a backend `ETag` covering the whole composed search path, a `304` short-circuit before
a resolution walk, a proposed third `schema_cache.py` blob for a persistent resolved-tree cache,
per-package byte/compute-cost accounting for an eager whole-package resolve) described v16's
backend-resolves-and-ships-JSON design and no longer applies. §0's raw-file serving replaces the
whole "resolve then ship JSON" model with a real content-hash `ETag` on the served bytes (§0's own
section, not restated here). What DOES still resolve server-side is `/scene`'s own
`resolve_actor_props` native call (§2) — a per-actor, per-request resolve, same as it always was,
just implemented in Rust now instead of Python; it is NOT the whole-package eager resolve this
paragraph is superseding, and it is genuinely no more expensive than before. The CLASS-SHAPE-plus-
DEFAULTS half specifically (`resolve_class`) IS now a client-side, per-class, resolve-once concern
— the shared core resolves one class, once, on first inspection in the browser, and holds the
result for the rest of the session; there is no "cold whole-package" cost to amortize anymore for
THAT half, because nothing ever resolves a whole package eagerly under this design. The shared
core's own performance characteristics (native and WASM, both entry points) belong to
`dev/docs/board/to-spec/shared-rust-core-for-class-schema-resolution/`, not here.

### 2. `/scene`: a flat, sparse, per-actor VALUE map — no shape at all

`SceneActor.props` is no longer a tree. It's `dict[str, str]` — every path the actor states, mapped to
its final CANONICALIZED display text (see below), keyed by the same dotted path convention
`_canonical_path` already builds (`effective_props.py:358-369`, e.g. `"RotationRate.Yaw"`,
`"AlliancesEx.2.AgitationLevel"` — the literal array index inside the path, never implicit position in
a list). A path with nothing stated anywhere beneath it is simply ABSENT from the dict — no `null`
placeholder, no empty container entry.

**How the sparse map is built, stated explicitly (an earlier draft left this implicit)**: `/scene`'s
route calls the shared Rust core's `resolve_actor_props(actor, parsed_packages)` (§1) — natively,
via the existing `uedcli_native` PyO3 extension, not Python's `effective_props.py` walk, which this
change supersedes — by RE-WALKING the class schema per actor, keeping only the paths where a raw
stored value exists, NOT by shortcutting off `actor.props`' raw T3D lines directly. The port must
faithfully reproduce every exclusion Python's walk applies today — the top-level skip
(`HARD_REJECT`/`TYPED_FIELDS`/`is_computed_key`/`_is_excluded_kind`, `effective_props.py:238-245`)
and `_resolve_one`'s own recursive `_is_excluded_kind` guard (`:304`, which is what makes the
exclusion apply to struct members and array elements too, not just top-level props) — for free, by
construction, the same way the existing Python walk already does. Shortcutting off `actor.props`
directly (in either language) would leak `Name`/`Brush`/computed keys/dynamic-array entries/object
refs into the sparse map as orphan paths with no matching class-schema node — explicitly rejected.

**The real regression this route has history with — corrected from an earlier draft of this
paragraph, which misattributed it as a within-request per-actor-vs-per-class cost.** Read
`build_scene_payload`'s own docstring in full (`scene.py:786-799`): the per-actor loop was NEVER
the bottleneck — `_is_hidden_ed`'s `ClassDefaults` memo already amortized within one call (pinned
by `test_build_scene_payload_amortizes_class_resolution_over_repeated_classes`, a DIFFERENT memo
than `effective_props`'s own `ctx_cache`, which has NO regression test today — a real, separate gap
this port should close, not inherit). **The actual ~28s WanChai-scale bug was one level UP**:
`app.py`'s `scene()` route rebuilt `defaults`/`index` from scratch, via `_scene_inputs()`, on EVERY
HTTP REQUEST — throwing away every memo `build_scene_payload` relied on and re-paying a full
package-load-plus-Super-chain-walk-plus-defaults-decode per distinct class, per distinct REQUEST,
warm trunk/geometry cache or not. Fixed (already landed, unrelated to this spec) by caching the
`(search_files, index, defaults)` tuple ITSELF across requests (`scene_inputs_ref`, `app.py:161-
174`). **Correction to an earlier draft of this paragraph**: `build_scene_payload`'s own OUTPUT is
NOT also cached — that layer (`_payload_ref`/`_get_payload`) was real once but was removed entirely
by the later persistent-GUI-sessions work (`test_serve_app.py`'s own note: "Solved-build state
… is REMOVED ENTIRELY here"); `session_scene` (`app.py:649-664`) calls `build_scene_payload` fresh
on EVERY request today. This makes cross-request persistence of the new per-FQCN cache MORE
load-bearing, not less — `resolve_actor_props` genuinely runs once per actor per request, with
nothing above it memoizing the whole payload away.

**So the design answer here is cross-request persistence, not just within-one-build sharing —
and it must NOT be tied to `ctx.generation`, corrected from an earlier draft that got the
invalidation mechanism wrong.** `resolve_actor_props` does not independently re-walk the Super
chain — it CALLS `resolve_class(actor.cls, parsed_packages)` (§1) for that class's shape+defaults,
then does its own cheap, actor-specific work on top (read `actor.props`' raw stored text, keep only
the paths present, canonicalize each). `ctx.generation` is the WRONG invalidation signal for this:
it is driven by `TrunkWatcher`, watching the level's T3D TRUNK directory (`app.py`'s
`_on_trunk_settled`), not the package search path — tying the per-FQCN cache to it would flush the
cache on every ordinary actor edit (a milder instance of the exact regression this history is
about) while never catching a real `.u` file change. **The correct answer: the per-FQCN cache
lives and dies with the `(search_files, index, defaults)` TUPLE ITSELF** — built fresh alongside it
(the `_get_trunk` bootstrap, and `/load`, the same two places that mint a new tuple today), held
for as long as that tuple is, discarded and rebuilt wholesale when a new one replaces it. This
answers the multi-package problem too: one class's resolution can touch several packages (its own,
its ancestors', a struct/enum type's declaring package), so no per-class fine-grained key is
needed — the WHOLE per-FQCN cache is scoped to one `(search_files, index, defaults)` generation of
inputs, the same multi-package-dependency boundary v16's own abandoned `package_etag` formula
already established for the identical problem (§0's history section). **Where the native call's
`parsed_packages` comes from**: NOT §0's HTTP endpoint (that's for the browser; the backend doesn't
fetch from itself) — the route passes the SAME `index`/`resolver()` mechanism `_class_ctx_for`
already builds `ClassCtx` from today, and the Rust core does its own lazy, internally-cached
package parse on first need (same lazy-resolver-callback shape as today's `ClassCtx`, just backed
by Rust instead of Python) — via a caller-HELD handle/context object the route stores alongside its
`(search_files, index, defaults)` tuple and can drop when that tuple is replaced, never a
process-global static (a process-global would outlive the tuple it needs to be scoped to). **A new
regression test is real, needed work for this port's own plan** (`ctx_cache`'s sharing guarantee
has no test today, per above) — an amortization test asserting distinct-class resolutions don't
grow with actor count, AND a cross-request test asserting a second `/scene` call against an
unchanged trunk doesn't re-walk any class at all.

**`Location`/`MainScale`/`PostScale` are NOT covered by the `ctx.schema()` walk above — they're
`TYPED_FIELDS`, explicitly skipped by it (`effective_props.py:240`), and never mirrored into
`actor.props` at all (`model.py`'s own comment on the `Actor` dataclass: "like Location — NOT mirrored
into `props`").** §1 already covers their DEFAULTS (a class-schema-only variant of
`_resolve_typed_fields`); this is the missing STATED-value half, and needs its own explicit rule, not
an implicit extension of the generic walk. Per-axis/per-member statedness for these three comes from a
DIFFERENT mechanism than `_raw_stored_text`: `normalize._stated_axes(actor)` (Location) and
`effective_props._stated_scale_members(text, current)` (MainScale/PostScale) — both already used by
`_resolve_typed_fields` today, read directly, not re-derived. The rule: for each of the three, call the
SAME statedness function `_resolve_typed_fields` already calls, and for each axis/member it reports as
stated, add a sparse-map entry at the SAME dotted-path convention as everything else (`"Location.X"`,
`"MainScale.Scale.Y"`, `"MainScale.SheerRate"`), value = the actor's own stated text for that
axis/member (via `TypedField.get`, the same call `_resolve_typed_fields` already makes) — an unstated
axis/member simply has no entry, identical treatment to every other omitted path. A partially-stated
`Location=(X=100)` actor: `_stated_axes` returns `"X"` (only), so the sparse map carries exactly
`{"Location.X": "100"}` — `Y`/`Z` absent, filled at render time (§4) from `Location`'s own CLASS-ENTRY leaf
`default_value` (§1's `Location` paragraph: `Location`'s own class entry carries its own per-axis
`default_value`, same C1 fix as every other struct leaf) — **never from `types["Core.Vector"]`**, which
carries SHAPE only and holds no default at all (an earlier draft of this sentence said "filled from
`types[...]`'s own per-class default," directly contradicting §1/§3's C1 fix — a `types` entry is SHARED
across every class referencing `Core.Vector`, so it structurally cannot hold one class's own default
without leaking it onto every other class using the same shape, exactly the bug the `Core.Rotator`/
`Karkian`/`Rat` example above exists to rule out).
The per-property degrade (`effective_props.py:246-260`, a struct member or array element that fails to
resolve) has no direct analogue in a sparse VALUE-only map — a failed leaf simply contributes no path
entry, the same as an unstated one; there is no visible "this specific leaf failed to resolve" marker in
the sparse shape (there was one in the old tree shape, an empty `StructProp`/`ArrayProp`). This is an
accepted, minor loss of diagnostic granularity — the actor-level `note`/stderr degrade convention
(§1's `resolve_actor_props(actor, parsed_packages) -> (sparse_map, notes)`, the `notes` element)
still fires for a whole-class failure, just not for a single unresolvable leaf within an
otherwise-fine class.

**One value per stated leaf, already canonical — no separate `stored_value`/`effective_value` split.**
v1's split (raw `stored_value` + conditional `effective_value`) essentially never fired as designed
(`propedit.effective_value`'s merge at a STATED leaf path returns exactly that leaf's own stored text —
partial-struct-ness affects only the UNSTATED siblings, which are omitted from `/scene` regardless)
while silently reintroducing raw-vs-canonical ambiguity for the cases that actually DO differ from raw
stored text: enum ordinal→name (`_canonicalize_enum_text`) and `_dequote` (one wrapping quote pair
stripped). **`structtext._maybe_comma_sugar` is NOT one of these** (a v2 draft wrongly listed it) — it
has exactly two call sites, both on the WRITE path (`propedit/edit.py`'s `plan_edit`/`effective_match`),
never called by `effective_value`'s read path, so it cannot produce a divergence here (the Rust port
must not introduce it either). Resolution: the sparse map's value at each path is the shared
resolver's own canonicalized text at that path — the SAME `resolve_class`/`resolve_actor_props`
internals (§1) a class entry's `default_value` already goes through for an unstated leaf — full
stop. One field, one meaning, resolved once by ONE implementation, called natively here.

**Worked example** — `DeusEx.Rat` actor `Rat3`, `RotationRate=(Yaw=1234)`. **`payload.actors` stays a
plain ARRAY, `name` an ordinary field on each element — NOT restructured into a name-keyed object.** An
earlier draft of this example showed `"actors": {"Rat3": {...}}`, which nothing else in this design
proposes: `uedcli/serve/app.py`'s real `/scene` route (`"actors": [asdict(a) for a in payload.actors]`)
and `web/src/api.ts`'s real `ScenePayload.actors: SceneActor[]` are both arrays today, every real
consumer (`App.tsx`, `OrgPanel.tsx`, `Viewport3D`) walks them positionally by `.filter`/`.map`, and this
redesign's own Non-goals section already says the rest of the actor record — everything except
`SceneActor.props`'s own shape — is untouched:

```json
{
  "actors": [
    {
      "name": "Rat3",
      "cls": "DeusEx.Rat",
      "props": { "RotationRate.Yaw": "1234" }
    }
  ]
}
```

`Pitch`/`Roll` are absent — nothing stated. An enum example, `LightType=3` on the wire (stored as an
ordinal) canonicalizing to its name — **`3` is `LT_Blink`** in the real corpus (`Engine.Actor`'s
`ELightType`: `0 LT_None, 1 LT_Steady, 2 LT_Pulse, 3 LT_Blink, ...`, decoded directly from `Engine.u`; an
earlier draft of this doc used `LT_Steady`, which is ordinal 1, not 3 — corrected here so an implementer
doesn't pin a test against the wrong value):

```json
{ "props": { "LightType": "LT_Blink" } }
```

(never `"3"` — canonicalization already happened server-side, via the shared resolver's native
call, same guarantee its `default_value` already gives.)

**`ScenePayload.enums` is REMOVED entirely** (an earlier draft left this unstated). Enum value-name
lists now live ONLY in the shared resolver's `types` data (§1, fetched/resolved client-side per
class) — `resolve_actor_props`'s existing second return value (`ctx_by_type`, today unioned into
`ScenePayload.enums` by `_build_actors`) has no successor in the new design; the per-actor
accumulation this redesign removes goes with it.

### 3. The shared resolver's `types`/class-entry worked example — corrected, real data, every number
script-generated in this pass

v6's own worked example still had a fabricated leaf: `InitialAlliances` was described as "`Engine.Actor`'s
own `AllianceInfo[8]`" with key `"Engine.Actor.AllianceInfo"` — wrong on three counts, script-verified
directly against `uned/UED22/DeusEx.u` (`uprops.resolve_class_properties`/`resolve_class_defaults`/
`struct_members`, `.venv/bin/python3`): the property is declared on `DeusEx.ScriptedPawn`, not
`Engine.Actor` (which has no such property at all); its struct type is named `InitialAllianceInfo`, not
`AllianceInfo` (no struct by that name exists anywhere in the corpus); its real category is `"Alliances"`,
not `null`. `AlliancesEx`/`AllianceInfoEx` (four members, category `Uncategorized`, `outer=ScriptedPawn`)
was already correct in v6 and is unchanged here.

`InitialAllianceInfo` is also a genuinely LIVE two-way collision — the exact case this design's
`(package, outer, name)` rule exists for — and demonstrates it properly once the example is real:

```
DeusEx.u struct exports named "InitialAllianceInfo":
  export #365  outer=ScriptedPawn      members: AllianceName:NameProperty, AllianceLevel:FloatProperty, bPermanent:BoolProperty
  export #541  outer=AllianceTrigger   members: AllianceName:NameProperty, AllianceLevel:FloatProperty, bPermanent:BoolProperty

real properties referencing them:
  DeusEx.ScriptedPawn.InitialAlliances : array_dim=8  category='Alliances'        -> key DeusEx.ScriptedPawn.InitialAllianceInfo
  DeusEx.AllianceTrigger.Alliances     : array_dim=8  category='AllianceTrigger'  -> key DeusEx.AllianceTrigger.InitialAllianceInfo

Karkian's own InitialAlliances defaults (all 8 indices, real, not deduplicated):
  [0] AllianceName=Greasel  AllianceLevel=1  bPermanent=True
  [1] AllianceName=None     AllianceLevel=0  bPermanent=False
  [2] AllianceName=None     AllianceLevel=0  bPermanent=False
  [3] AllianceName=None     AllianceLevel=0  bPermanent=False
  [4] AllianceName=None     AllianceLevel=0  bPermanent=False
  [5] AllianceName=None     AllianceLevel=0  bPermanent=False
  [6] AllianceName=None     AllianceLevel=0  bPermanent=False
  [7] AllianceName=None     AllianceLevel=0  bPermanent=False
```

Both struct exports happen to share one shape (a same-name collision doesn't require differing shapes
to matter — `sUserInfo`, §1, is the differing-shape case; this is the same-shape case, and the keying
still has to get it right, since the two properties' OWN default text is never shared regardless of
shape). `array_dim=8` and `Karkian`'s own per-index defaults (index 0 real and distinct, 1-7 identical)
are genuinely real, script-verified data — listed in FULL below, not run-length-collapsed (review
finding I3: an earlier draft deduplicated the 1-7 tail to one entry with no stated decode rule, which
is undecodable against §4's positional-lookup frontend walk; the wire format is always a full list, one
entry per real array index, list position = array index, no exceptions).

Three separate `resolve_class(fqcn, ...)` calls (§1's real per-class contract — corrected here from
an earlier draft, which wrongly showed one shared whole-package envelope; each call below is a
complete, independent return value, not a fragment of a larger response) for `DeusEx.Karkian`'s
`RotationRate` (`Core.Rotator`, real defaults DIFFERING from `DeusEx.Rat`'s own — the reason
`default_value` cannot live on the shared `types` entry, §1), `InitialAlliances` (array-of-struct,
real per-index defaults, the live collision's first side), and `AlliancesEx` (array-of-struct,
all-defaulted in this class); then `DeusEx.Rat`'s own call for the SAME `RotationRate` property,
with a genuinely different default; then `DeusEx.AllianceTrigger`'s own call, demonstrating the
collision's SECOND side (same struct name, different `outer`, correctly a different key):

`resolve_class("DeusEx.Karkian", ...)`:

```json
{
  "class": {
    "props": [
      {
        "kind": "struct", "name": "RotationRate", "category": "Movement",
        "struct_type": "Core.Rotator",
        "default_value": { "Pitch": "4096", "Yaw": "30000", "Roll": "3072" }
      },
      {
        "kind": "array", "name": "InitialAlliances", "category": "Alliances",
        "element_type": "DeusEx.ScriptedPawn.InitialAllianceInfo", "array_dim": 8,
        "default_value": [
          { "AllianceName": "Greasel", "AllianceLevel": "1", "bPermanent": "True" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" }
        ]
      },
      {
        "kind": "array", "name": "AlliancesEx", "category": "Uncategorized",
        "element_type": "DeusEx.ScriptedPawn.AllianceInfoEx", "array_dim": 16,
        "default_value": [
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "AgitationLevel": "0", "bPermanent": "False" }
        ]
      }
    ]
  },
  "types": {
    "Core.Rotator": {
      "kind": "struct",
      "members": [
        { "kind": "int", "name": "Pitch" },
        { "kind": "int", "name": "Yaw" },
        { "kind": "int", "name": "Roll" }
      ]
    },
    "DeusEx.ScriptedPawn.AllianceInfoEx": {
      "kind": "struct",
      "members": [
        { "kind": "name", "name": "AllianceName" },
        { "kind": "float", "name": "AllianceLevel" },
        { "kind": "float", "name": "AgitationLevel" },
        { "kind": "bool", "name": "bPermanent" }
      ]
    },
    "DeusEx.ScriptedPawn.InitialAllianceInfo": {
      "kind": "struct",
      "members": [
        { "kind": "name", "name": "AllianceName" },
        { "kind": "float", "name": "AllianceLevel" },
        { "kind": "bool", "name": "bPermanent" }
      ]
    }
  }
}
```

`resolve_class("DeusEx.Rat", ...)` — a SEPARATE call, own envelope, own `types` subset:

```json
{
  "class": {
    "props": [
      {
        "kind": "struct", "name": "RotationRate", "category": "Movement",
        "struct_type": "Core.Rotator",
        "default_value": { "Pitch": "4096", "Yaw": "65530", "Roll": "3072" }
      }
    ]
  },
  "types": {
    "Core.Rotator": {
      "kind": "struct",
      "members": [
        { "kind": "int", "name": "Pitch" },
        { "kind": "int", "name": "Yaw" },
        { "kind": "int", "name": "Roll" }
      ]
    }
  }
}
```

`resolve_class("DeusEx.AllianceTrigger", ...)` — the collision's second side:

```json
{
  "class": {
    "props": [
      {
        "kind": "array", "name": "Alliances", "category": "AllianceTrigger",
        "element_type": "DeusEx.AllianceTrigger.InitialAllianceInfo", "array_dim": 8,
        "default_value": [
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" },
          { "AllianceName": "None", "AllianceLevel": "0", "bPermanent": "False" }
        ]
      }
    ]
  },
  "types": {
    "DeusEx.AllianceTrigger.InitialAllianceInfo": {
      "kind": "struct",
      "members": [
        { "kind": "name", "name": "AllianceName" },
        { "kind": "float", "name": "AllianceLevel" },
        { "kind": "bool", "name": "bPermanent" }
      ]
    }
  }
}
```

**Each call's `types` is self-contained — only what THAT class's own shape references, not the
whole package's.** `DeusEx.Karkian` and `DeusEx.Rat` each carry their OWN full `"Core.Rotator"`
entry (identical shape, since it's the same real type) alongside their OWN, genuinely different
`default_value` (`Yaw: "30000"` vs `"65530"`) — this is the entire C1 fix in one worked example.
**The frontend accumulates `types` across calls into one session-wide map** (§4) — resolving both
`Karkian` and `Rat` produces two identical `Core.Rotator` entries, which simply overwrite each
other harmlessly (real shape data is deterministic per type, never per call) rather than needing
any de-duplication logic. `DeusEx.ScriptedPawn.InitialAllianceInfo` (Karkian's call) and
`DeusEx.AllianceTrigger.InitialAllianceInfo` (AllianceTrigger's call) are two DISTINCT type keys
for the same struct NAME — a real, live corpus collision, correctly disambiguated by `outer` alone,
no runtime collision-detection anywhere, and no collision in the accumulated map either, since the
keys themselves already differ. `types` entries carry no `default_value` and no `category` anywhere
at all (never present as a key, not even as `null` — both are per-class-per-occurrence, never
type-intrinsic, §1) — note every `types` member above has ONLY `kind`/`name`, and (for a nested struct
member) a `"struct_type"` ref (or `"enum_type"` for a nested enum member); no class-entry leaf above
emits `"category": null` either, always the real
resolved string. `array_dim` rides on each class entry's own array leaf (a fixed compile-time constant
from the schema — `Karkian`'s `InitialAlliances`/`AlliancesEx` really are declared `[8]`/`[16]`), NOT
derived from how many elements any actor states (§2's sparse overlay) — this is what lets the frontend
(§4) render an array's full slot count even when an actor states only some of them.

### 4. Frontend: fetch raw packages, resolve one class lazily, walk the shape

**Fetch strategy — raw `.u` bytes, the CODE-RELEVANT transitive package closure, eager at Load,
ETag-cached (§0).** A class's Super chain can cross packages (e.g. `DeusEx.Karkian extends
DeusEx.ScriptedPawn extends Engine.Pawn extends Engine.Actor extends Core.Object`), and this is
NOT knowable in advance from the scene's actor list alone — the scene only says which package each
actor's OWN class lives in, not which packages its ancestors live in. So package discovery is
itself part of the shared core's job, following each package's own import table (`RawPackage`'s
parsed imports already name every package a class references, `package_read.rs`) outward from the
packages the scene's actors directly reference, fetching each newly discovered package's raw bytes
(`GET /api/package/{name}/raw`) as it's found, repeating until the closure is exhausted.

**The walk MUST filter to imports whose class is `Class`/`Struct`/`Enum` (or a `*Property` type
reference) — never blindly follow every import.** Measured directly against the real corpus, an
unfiltered walk from `DeusEx`+`Engine`+`Core` is **16 packages, 93.7 MB** — because most of a real
package's import table is texture/mesh/sound references (`DeusEx.u` alone: 1132 `Texture` imports,
428 `LodMesh`, 232 `Sound`, vs. 83 `Class`/5 `Struct`/5 `Enum`), and following them also pulls
non-`.u` asset files, contradicting this endpoint's own "raw `.u` bytes" framing (§0). None of that
content can ever matter to resolution — `ObjectProperty`/`ClassProperty`/similar are already an
excluded kind everywhere in this design (§1's `_is_excluded_kind` filter) — so filtering the walk
to code-relevant imports only loses nothing. Filtered, the real closure is **8 packages, 4.7 MB**
(`core`, `engine`, `deusex`, `extension`, `consys`, `ipdrv`, `ubrowser`, `uwindow` — `extension.u`
is real and needed, e.g. for `EHAlign`, §1's struct-member-enum discussion), not the 3-package
estimate an earlier draft of this section gave. `Core.u`/`Engine.u` (0.06 MB / 1.24 MB raw) are the
root of nearly every real Super chain and get discovered and fetched almost immediately regardless.
Every fetch is the same ETag-cached, `GET /api/package/{name}/raw` call — no new request shape, no
per-class round trip.

**Resolution is lazy and per-class, entirely client-side, zero network.** Once the packages a
class's Super chain needs are in memory (parsed already, or parsed on first use — a package's
bytes only need parsing once per session, memoized alongside the fetch), the shared core's
`resolve_class(fqcn, parsed_packages)` call (§1's contract) runs synchronously, in-process, with no `await`, no
request — there is nothing left to wait on. The Inspector calls this the first time an actor of
class `C` is selected, caches the result client-side for the rest of the session (a plain
in-memory map, keyed by FQCN — no persistence needed; a page reload just re-resolves on next use,
which is itself instant once the raw bytes are back in memory from §0's ETag cache), and every
subsequent selection of a `C`-classed actor reads the cached result. **This is what makes the
"never a spinner for connectivity" requirement literally true**: after the one eager raw-bytes
fetch at Load, nothing the Inspector does for ANY class, ever, touches the network again.

`Inspector`'s per-actor render for class `C`: start from `C`'s own resolved class entry (§1's
`resolve_class(C, parsed_packages)`, from cache or resolved on first use as above) — its top-level prop list, each leaf already
carrying its OWN per-class `default_value` (§1/§3's C1 fix: defaults live on the CLASS
entry, never on the shared `types` entry). For a struct leaf, resolve its `"struct_type"` key; for an
enum leaf, its `"enum_type"` key; for an array-of-struct/array-of-enum leaf, its `"element_type"` key —
each against the response's `types` dict ONLY for SHAPE (member names/kinds/nesting — **an
`element_type`-bearing array leaf carries no `element_kind` sibling to say which, unlike the plain-scalar
array case below; the frontend reads `types[element_type]["kind"]` itself (`"struct"` or `"enum"`) to
decide whether each element renders as a member tree or a plain value** —
`types` entries can themselves reference other `types` entries for a nested struct-of-structs, resolved
the same way, recursively, to whatever depth the real schema has) — never for default values, which the
class entry's own leaf already carries. At each leaf, check the actor's sparse `props` map for that
leaf's dotted path (synthesizing an array element's path from its POSITION in the class entry's own
`array_dim`-sized slot range — safe because the class-schema tree's own array description is never
sparse, only `/scene`'s per-actor overlay is): **present → render that value, mark explicit; absent →
render the class entry's own `default_value` at the same path, mark defaulted.** This
IS the "show all" tree — it's what BOTH views render (no regression to today's partial-struct-shows-
inline behavior, confirmed above); the overrides-only/show-all toggle changes only whether a TOP-LEVEL
prop with NO path present anywhere beneath it is included in the walk at all (`filterOverridesOnly`'s
existing top-level-only granularity, unchanged) — never whether an INCLUDED struct/array's own
individual defaulted members render (they always do, today and after this change).

`isExplicit`'s discriminator becomes simply "does the actor's sparse map contain this leaf's path" — a
`path in actor.props` check against the actor's flat `props` object, unambiguous by construction (no
more `stored_value !== null`, which silently passes for `undefined` too under a sparse shape where
absence isn't represented as an explicit `null` at all).

**An ENUM leaf's `"enum_type"` reference resolves the SAME way a struct's `"struct_type"` does** —
`types[enum_key]["values"]`
gives the ordered value-name list, mirroring exactly how `ScenePayload.enums[enum_type]` worked before
this redesign removed it. **Stated explicitly rather than left to guesswork: nothing in the current
Inspector actually reads this list for DISPLAY.** `shownValue` (`web/src/panels/effectiveProps.ts`,
verified directly — it makes no reference to `enum_type`/`values` anywhere) already renders `stored_value
?? default_value` directly, and both are already-canonicalized NAME text by the time they reach this
code — `stored_value` from `/scene`'s JSON (resolved server-side, §2), `default_value` from the
shared resolver's own client-side WASM call (§1) — there is no ordinal to look up either way, by
the SAME shared canonicalization logic underneath both. This mirrors today's `ScenePayload.enums`
exactly (`Inspector.tsx`'s own comment already marks it "reserved for a future editing feature," unused
for display) — the wire shape and its reference mechanism are fully specified for completeness and for
that future editing work (an enum dropdown genuinely needs the value list), not because §4's own render
walk consumes it today. An implementer should not read this silence as an oversight.

**In-flight UX and fetch timing, stated honestly — this is NOT a simple "starts alongside /scene"
race (an earlier draft of this paragraph claimed it was).** Package discovery is actor-class-driven
(above), so the actor-referenced half of the closure genuinely cannot start until `/scene` itself
has returned at least the scene's actor list. Two fetches DO start immediately, with no such
dependency: `Core.u`/`Engine.u` (§4's own numbers show they're the root of nearly every real Super
chain and are cheap regardless — prefetching them unconditionally, before `/scene` resolves, costs
nothing and shrinks the dependent tail). The REST of the closure — a level's own directly-used
packages, and whatever their Super chains/struct-enum references pull in beyond `Core`/`Engine` —
starts only once `/scene`'s actor list is known, and a real actor selection requires at least one
render cycle after that anyway, so in the overwhelming common case the fetch has already landed by
the time the user reaches for the Inspector. If it hasn't (a slow initial load), a struct/array row
simply doesn't expand until the fetch resolves — an ordinary async-data race for the Load-time
closure, self-resolving within the render cycle after it completes, no loading spinner specified.

**The "never a spinner" guarantee holds for every class present in the level at Load — not
unconditionally forever, and that scope should be stated rather than implied.** Once the Load-time
closure has landed, every class within it resolves instantly, with zero network, for the rest of
the session (the lazy-resolve-then-cache mechanism above). A class introduced AFTER Load — a mid-
session trunk change surfaced via the existing `TrunkWatcher`/`changes_available` mechanism, or a
new actor from the `gui-builder-brushes` feature — could in principle belong to a package outside
that closure; the frontend degrades the same way as any newly-discovered package (fetch it, same
ETag-cached call, same async-race-not-spinner pattern above) rather than failing.

**What the Inspector actually SHOWS for an unresolvable class, stated concretely, not left
circular.** §1's degrade convention (a caller-visible error, not a silently-empty result) is a
BACKEND-side rule about what `resolve_class` itself does when the core it's built into has a
stderr/notes channel — the browser has neither. If a level references a package the composed
search path doesn't have at all, `resolve_class` throws for every class in it; the Inspector
catches this at the render boundary and shows that section as a clear, named error inline (e.g.
"can't resolve DeusEx.SomeClass: package not found" in place of the property list) — never a
silently empty props table, which the project's no-silent-half-answers convention forbids. This is
the one real new user-facing error surface this redesign adds (today's design can't hit this case
at all, since resolution always happened server-side, where a missing package fails the whole
`/scene` request instead).

### Transport: gzip, not msgpack

Investigated per owner request, for whatever JSON this design still ships (`/scene`'s own sparse
per-actor map, §2 — the large class-schema payload this investigation originally targeted no
longer exists as JSON at all; §0 covers the raw `.u` transport's own gzip numbers separately).
`msgpack` gives a realistic ~20-40% size reduction for this payload shape — it does not deduplicate
the dominant JSON cost (repeated object keys), which `/scene`'s own sparse-map shape (§2) already
minimizes structurally by only ever carrying stated leaves. Starlette's built-in `GZipMiddleware`
(one line, zero frontend change) is still worth adding regardless — realistically 70-90%+ on this
payload shape, likely still beating msgpack outright. Recommendation: add `GZipMiddleware` now (it
also covers §0's raw-file responses, where the real, measured numbers are the ones that matter —
see §0); msgpack stays a later option only if parse SPEED, not size, turns out to matter.

## What changed, v14 → v15 (controller-applied, small, no design change)

A review of v14 found zero Critical issues and two Important, both one-or-two-line fixes: **I1** the
class entry's `props` array order was never stated as normative, though the frontend derives category-
group order from it and the typed-field leaves are unconditionally first today — added one normative
paragraph pinning the order (typed-field leaves first, then `ctx.schema()` walk order), so an
implementer's two separate emitter functions can't silently reorder every actor's groups. **I2** the
document's own version self-identification (`spec.md`'s opening paragraph, `overview.md`'s summary) was
two-to-four rounds stale, describing a v10/v12 state after v13/v14 had already landed — updated both to
v14/thirteen passes accurately. No design change; both fixes applied directly by the controller (no
fork dispatch needed, given the small scope) and verified: all 12 JSON fences still parse.

## What changed, v15 → v16 (owner-directed, no design change)

The owner caught that the new design's type-reference field naming was never cross-checked against the
ALREADY-SHIPPED `EffectiveProp`'s own convention across all 15 prior rounds: `uedcli/effective_props.py`'s
`EnumProp.enum_type: str` (real, shipped code, already in `web/src/api.ts`) uses a PER-KIND field name,
not a generic one — yet this spec's struct/enum leaves both used one shared `"type"` field. Fixed: a
struct-typed leaf/member now carries `"struct_type"` (the parallel per-kind name); an enum-typed
leaf/member now carries `"enum_type"` (matching the existing shipped name exactly, rather than the
newly-invented generic `"type"` this design had drifted into). `"element_type"` (array-of-struct/
array-of-enum leaves) is UNCHANGED — it was already kind-specific by construction, since the array's own
`element_kind` sibling field already discriminates struct/enum/scalar elements, so there was no ambiguity
a rename would resolve there. No design change; every JSON worked example and every prose description of
this field renamed consistently. Verified: all 12 JSON fences still parse.

## What changed, v16 → v17 (architecture pivot, owner-directed)

The owner asked, after v16 was otherwise clean: could the same resolution logic run client-side,
synchronously, avoiding a per-class API call entirely — and could that be ONE implementation, not
a second port duplicated in TypeScript? Investigated directly rather than guessed at, across
several rounds:

1. **Why is v16's own full-package resolve so expensive?** Benchmarked for real against the actual
   corpus (`DeusEx.u`, 1166 classes): ~25-31ms/class with the existing persistent props cache warm,
   ~183ms/class cold. Sharing resolution-cache dicts across a whole package's classes in one request
   saves only ~12% on top of warm — not a fix, since most of the cost is genuine unique-per-class
   work, not redundant recomputation. So v16's own proposed third `schema_cache.py` blob would have
   amortized this to "once per package, ever" — but even warm and amortized, a full-package response
   is still tens of seconds/tens of MB for `DeusEx.u`, because a real level only uses ~28-200 of its
   1166 classes (measured on the `nyc_bar` 59-actor subset: 28 classes across 2 packages). Caching
   fixes how OFTEN you pay a cost, not how MUCH you ship.
2. **What does UnrealEd itself do, that we don't?** It loads all `EditPackages` fast (raw binary
   parse + link, the same cheap operation `upackage.load_package` already does) and resolves one
   class's property grid LAZILY, only when an actor of that class is actually inspected, entirely
   in-process — never eagerly for a whole package. v16's design did the opposite: eager, whole-
   package, server-side. Matching UnrealEd's own architecture means moving resolution client-side
   and making it lazy per class, not fixing the eager whole-package cost in place.
3. **Real file-size data settled the remaining scope question.** `Core.u`+`Engine.u`+`DeusEx.u` —
   the three packages nearly every real actor's Super chain touches — total 3.2 MB raw / 0.8 MB
   gzipped for 1288 classes combined: a fully reasonable one-time download. The large, asset-heavy
   packages (`DeusExCharacters.u` 19.2 MB for 4 classes, `DeusExUI.u` 27.4 MB for 1) are the
   exception, and the owner explicitly accepted downloading them in full anyway, for simplicity,
   rather than building server-side class-subset extraction now.
4. **"One implementation" needs one language runnable on both sides.** The backend still needs its
   own resolver (CLI, the write path) — a second TypeScript port would be real duplication, exactly
   what the owner ruled out. `uedcli-native` already has a Rust binary-parsing layer
   (`package_read.rs`); porting the missing resolution/walk logic to Rust and compiling it both
   natively (PyO3, already the codebase's existing pattern) and to WASM (new to `web/`, not
   attempted here) gives one real implementation, used both ways. Split into its own item,
   `dev/docs/board/to-spec/shared-rust-core-for-class-schema-resolution/`, since it's substantial,
   reusable infrastructure this spec depends on rather than owns.

Result: §0 (raw-file endpoint, replacing the old resolved-JSON endpoint entirely), §1 reframed as
the shared resolver's output contract rather than an HTTP response shape (content unchanged — every
corpus fact, worked example, and identity rule from v1-v16 carries over as-is), §4 rewritten around
fetch-the-transitive-package-closure-then-resolve-lazily-client-side. §2 (`/scene`'s sparse map)
keeps its WIRE SHAPE unchanged — but its RESOLUTION does move, per a fix in the first v17 review
(below): `/scene`'s route now calls the same shared core natively, superseding
`effective_props.py`'s Python walk, rather than keeping a second implementation running alongside
the new one. The caching/compute-cost machinery v9-v16 built for the old server-resolves design
(the real `ETag` formula, the proposed third `schema_cache.py` blob, the per-package compute-cost
accounting) is superseded and removed from this spec; §0's raw-file `ETag` replaces it, and the
shared core's own performance characteristics belong to its own item now, not here.

## v17 fix round (same-day review findings, owner-directed on the two genuine forks)

A review of the first v17 draft found 3 Critical and 8 Important findings — real gaps in the pivot
itself, not nits. Fixed, all same design direction, no further pivot:

- **The "backend does no resolution" claim was false** — §2's `/scene` build still walked the
  class schema and resolved stated values in Python, a second implementation alongside the new
  Rust/WASM one, violating the "one implementation" goal. Asked the owner directly: route
  `/scene`'s resolution through the SAME shared core too, called natively (§1 now documents TWO
  entry points sharing one crate: `resolve_class` for shape+defaults, called both natively and via
  WASM; `resolve_actor_props` for `/scene`'s per-actor values, called only natively) — widens the
  shared-rust-core item's scope, which its own `overview.md` now reflects.
- **§1's own API contract was self-contradictory** — it specified a whole-PACKAGE resolve
  (`resolve_package(bytes) -> {classes: every class, ...}`) while §4 called a per-CLASS entry
  point. Fixed: §1 now specifies `resolve_class(fqcn, parsed_packages)` as the one real contract,
  matching what §4 actually calls.
- **The transitive package-fetch rule over-fetched by ~20x, measured for real**: following every
  import (as originally specified) pulls in 16 packages / 93.7 MB from the real corpus, mostly
  texture/mesh/sound references that can never affect resolution (already-excluded property
  kinds). Fixed: the walk filters to `Class`/`Struct`/`Enum`-typed imports only — 8 packages /
  4.7 MB, the real number (not the earlier, uncorrected "3 packages / 3.2 MB" estimate).
- **The `ETag` was silently softened from the owner's own standing instruction.** The first v17
  draft used a stat-tuple (no content hash), justified by `schema_cache.cache_key`'s own
  reasoning — but that reasoning is about avoiding a RESOLUTION-cache cost this route no longer
  pays; asked directly, the owner confirmed the original "etag with checksum of `.u`" instruction
  still applies here specifically. Fixed: a real `sha1` of the served bytes, cached in-process by
  stat so an unchanged file isn't re-hashed on every request (same caching PATTERN as before, but
  a real content hash as the actual validator value).
- Several smaller fixes: the "fetches start alongside `/scene`" claim was impossible as stated
  (package discovery needs `/scene`'s own actor list first for anything beyond `Core`/`Engine`,
  which now prefetch unconditionally); "never a spinner" is now scoped explicitly to the Load-time
  package closure, with a stated degrade path for a class introduced later (a mid-session trunk
  change, or the `gui-builder-brushes` feature); stale "class-schema endpoint" phrasing from the
  v16 framing, left over in a few spots, corrected to describe the shared resolver instead; two
  further honest, unresolved gaps recorded in Open Questions (client-side compute cost is
  unbudgeted until real WASM benchmarks exist; cross-reload persistence assumes the browser
  actually retains large — 18-27 MB — HTTP cache entries, unverified).

All 12 JSON fences re-verified to still parse after this round.

## v17 second fix round (re-review findings)

A re-review of the first v17 fix round independently re-measured the 8-package/4.73MB closure
(exact match, from two independent seed sets) and confirmed C1/C3 genuinely fixed, but found one
more Critical and several Important gaps:

- **§3's ONLY worked example of the resolver contract was still the superseded whole-package
  shape** (a `"classes": {...}` map with three classes under one `"types"` dict), contradicting
  §1's own corrected `resolve_class(fqcn, ...)` single-class contract — an implementer copying the
  one concrete example would build exactly the eager whole-package resolve this pivot exists to
  eliminate. Fixed: §3 now shows three separate `resolve_class(...)` calls, each a complete,
  self-contained envelope, with a new paragraph explaining that `types` accumulates across calls
  into one session-wide map (harmlessly overlapping for a shared type like `Core.Rotator`).
- **Two fixed claims from the first round were still contradicted elsewhere in the same document**:
  §1's own "§0's raw-file serving is the whole backend surface" line still said "the backend does
  no resolution" (false since `/scene`'s `resolve_actor_props` is a real native resolve) and still
  described the ETag as "os.stat-based" (already fixed to a real hash in §0, just not here) — both
  corrected. §0's "never leaves the frontend holding stale class shape/defaults for an editing-
  session-length window" claim was too strong — narrowed to what's actually true (fresh across
  reloads; a resolved class stays cached, by design, for the rest of one running session).
- **Asked the owner directly**: Goal 4's "one implementation... used by both the backend (CLI, the
  write path) and the frontend" read as forcing the CLI's own class-display and the write path's
  validation onto the shared core in this same pass — a much bigger scope. Confirmed: this pass
  covers only the Inspector-props path (`effective_props.py`, superseded); radii/`bHiddenEd`/
  `bDirectional` and the CLI/write path keep their existing code for now. Logged as a tracked, not
  committed, follow-up: `dev/docs/board/inbox/migrate-radii-bhiddened-bdirectional-and-cli/`.
- Smaller fixes: `resolve_actor_props`'s native `parsed_packages` now has a stated caching answer
  (in-process, per-package, stat-keyed — the same pattern as every other cache in this document,
  not a new re-parse-per-request cost against a request path with real regression history);
  §0 now specifies case-insensitive name→file lookup against `composed_search_files`' own list
  (never a path join), rejects a non-`.u` package kind with a named 404, and notes the ETag needs
  RFC-correct quoting plus `Vary: Accept-Encoding` once gzip is added; the frontend's degrade for
  an unresolvable class now says what the Inspector actually shows (an inline named error, never a
  silently empty table); the `resolve_class` arity is now consistent everywhere it's called; the
  stale "3.2 MB / 3-package" figure is corrected to the real, independently-reproduced "4.73 MB /
  8-package" number throughout; the document's own opening self-identification ("This is v16")
  is fixed to v17.

All 14 JSON fences re-verified to still parse after this round.

## v17 third fix round (re-review findings)

A third review independently re-verified round 2's fixes (the §3 rewrite, all 14 fences, the ETag
consistency, the 8-package/4.73MB numbers — all confirmed exactly, including from an independent
re-measurement) and found the round-2 caching fix answered the wrong question, plus real leftover
contradictions from the Goal-4 scope narrowing:

- **The round-2 caching fix cached package PARSING, but the actual regression this route has
  history with was resolution work thrown away and rebuilt.** (**This round's own root-cause claim
  — "per-CLASS resolution repeated per actor, within one request" — was ITSELF corrected in the
  v17 fourth fix round below: the real history is a CROSS-REQUEST rebuild, not a within-request
  per-actor cost. Left here unedited as the accurate record of what this round actually found and
  fixed at the time; read the fourth round's entry for the corrected story.**) Fixed here:
  `resolve_actor_props` now explicitly calls `resolve_class` internally for the expensive
  Super-chain-walk-plus-defaults half, doing only cheap actor-specific work (which paths are
  stated, canonicalize) on top — this part of the fix stands. This is also what makes "one
  implementation" true in substance: the two entry points are not independent walks, one is built
  on the other.
- **Three sentences (in `spec.md` and the sibling `overview.md`) still said the CLI/write path
  natively call `resolve_class`, contradicting the Goal-4 scope ruling two rounds ago fixed
  elsewhere.** Fixed: this pass's only production native caller of `resolve_class` is
  `resolve_actor_props` (for `/scene`), stated consistently everywhere it's mentioned now.
- Smaller fixes: `resolve_actor_props`'s signature gained its missing `notes` return value
  (matching what §2 already relied on); the sibling item's port list gained the `Location`/
  `MainScale`/`PostScale` statedness helpers and the `model.Actor`-across-PyO3 question, both
  missing since the item's scope widened to cover `/scene`; the item's own overview no longer
  implies the CLI/write path are wired in this pass; the main spec's `overview.md` was rewritten —
  it still described the pre-round-1 "no resolution at all" architecture and never mentioned either
  fix round or the Goal-4 ruling.

## v17 fourth fix round (re-review findings)

A fourth review verified round 3's fixes hold (Goal-4 scope consistent everywhere, all 14 fences
valid) but found round 3's own regression-history attribution was itself wrong, plus a follow-on
design error caused by trusting that wrong history — corrected in two passes within this same
round, since the first correction attempt (below) itself needed a further fix once verified against
real source a second time:

- **Round 3 said the ~28s WanChai regression was "per-class resolution repeated per actor, within
  one request." Reading `scene.py`'s own docstring in full shows this is backwards**: the per-actor
  loop was never the bottleneck (`_is_hidden_ed`'s `ClassDefaults` memo already amortized within one
  call, pinned by a real test — a DIFFERENT memo than `effective_props`'s own `ctx_cache`, which has
  NO test today). The real bug was CROSS-REQUEST: `app.py`'s `/scene` route rebuilt `defaults`/
  `index` from scratch on every HTTP request, discarding all memoized work. Fixed here: §2's caching
  paragraph corrected, with the real citations.
- **The first fix attempt (this same round) tied the new per-FQCN cache to `ctx.generation` —
  independently re-verified against real source and found WRONG**: `ctx.generation` is driven by
  `TrunkWatcher`, watching the T3D trunk directory, not the package search path; tying the cache to
  it would flush on every ordinary actor edit (reintroducing a milder version of the same
  regression) while never catching a real `.u` change. Corrected: the cache lives and dies with the
  `(search_files, index, defaults)` tuple itself (`scene_inputs_ref`) — built alongside it, held for
  as long as it is, discarded wholesale when a new one replaces it (`_get_trunk`'s bootstrap, or
  `/load`). No generation involvement.
- **A second real error, also independently caught**: this round's own first draft said the fix
  "already landed" by caching BOTH `build_scene_payload`'s OUTPUT and its inputs tuple. The
  output-caching layer (`_payload_ref`/`_get_payload`) was real once but was REMOVED ENTIRELY by
  later work (`test_serve_app.py`'s own note) — `/scene` calls `build_scene_payload` fresh on every
  request today, which makes the new per-FQCN cache MORE load-bearing than first stated, not less.
  Corrected.
- The sibling `shared-rust-core-for-class-schema-resolution/overview.md` gained the missing
  ownership-shape requirement this design needs to actually be buildable: a caller-held context
  object the route stores alongside `scene_inputs_ref` and can drop when it's replaced — not a
  process-global static, which the earlier draft never ruled out.

## Open questions

**The struct-key collision question from v3 is CLOSED**: `package.outer.name` (`OuterClass` omitted
when `outer` is absent or resolves to `Object`, the universal-root case — refined in §1 once verified
against real data, mirroring the real texture-identity precedent `Package.Group.Name`) resolves every
real same-package name collision found in the corpus (`S_MenuUIBorderButtonTextures`,
`InitialAllianceInfo`, `sUserInfo`, `XAIParams` ×9) with no runtime collision-detection needed. No
owner sign-off needed on a fallback; there's no fallback left to choose between.

**The `Vector`/`Rotator`/etc. question from v4 is also CLOSED** — they resolve cleanly (`Core.u`, not
`Engine.u`; v4's claim they couldn't be found was a tool-use bug in that pass's own investigation, not
a real gap — see §1). **The member-shape sub-question v5 left open is ALSO now CLOSED**: v5's claim that
`uedcli_native` was unavailable in this sandbox was itself wrong (it's installed; the system `python3`
on `PATH` just isn't the venv interpreter that has it — `.venv/bin/python3` works). Run for real: the
two `sUserInfo` exports genuinely have different member shapes (vindicating v3's original citation), all
9 `XAIParams` exports share one identical shape, and `Core.Rotator`'s members match §3's worked example
exactly. No open corpus-verification questions remain from this design's identity/shape mechanism.

**Two known implementation-surface gaps, sized here honestly, not fully resolved — real work for
the shared-rust-core item's own plan stage now (§ "What changed, v16 → v17"), not a design question
this spec itself needs to answer, but recorded here since the evidence was gathered against this
spec's own investigation**:

- **One shared root cause, two manifestations — `serve/scene.py`'s cross-package resolver helpers
  assume `prop.owner`'s first dot-segment is always a real package name, which fails whenever `prop` is
  reached through a STRUCT MEMBER rather than a top-level class property (a struct member's `owner` is
  the bare, unqualified STRUCT name, never package-qualified).** Confirmed as the SAME bug, not two
  separate ones — both helpers share the identical buggy line, `owner_pkg_name =
  prop.owner.split(".", 1)[0]`:
  - `_struct_members_via` (line 580): breaks for a struct member whose type is ITSELF a struct with a
    bare `owner` — e.g. `uprops.struct_members` on `Core.Scale`'s own nested `Scale` member returns
    `owner='Scale'` (not a real package name), so the split-on-dot resolves nothing.
    `Engine.Brush.TempScale` (type `Scale`, NOT one of the `TYPED_FIELDS`-skipped names, so a real,
    walked schema property on every brush actor) is one of at least 7 real struct-nested-in-struct
    cases found across `Engine.u`+`DeusEx.u`; `effective_props.py:246-260`'s per-property degrade
    already silently absorbs it today, independent of this redesign.
  - `_enum_names_via` (line 593): the identical bug, for an IMPORTED enum reached as a struct member
    (`type_ref < 0`, so `ClassCtx.enums()` falls through past the local `enum_value_names` short-circuit
    into this resolver). Script-verified real, reachable scope: `S_ActionButtonDefault.Align`,
    `S_BarButton.Align`, `S_KeyDisplayItem.inputKey` — hit by 31 real `(class, property)` pairs across
    30 distinct classes in `DeusEx.u` (29 classes reaching `S_ActionButtonDefault` via one shared
    declaration on `MenuUIWindow`, 1 declaring `S_BarButton`, 1 declaring `S_KeyDisplayItem`), every one
    degrading to a plain `ScalarProp(kind='byte')` today, with no `types` entry to reference (§1's
    enum-keying section above).

  The shared-rust-core Rust port touches exactly this resolver pattern anyway (to also surface the
  resolved TYPE IDENTITY, not just member/enum shape) — both manifestations are worth fixing in the
  SAME pass, likely with one shared fix (resolve the containing STRUCT's own true package first, via
  the struct's own export record — the same `outer`-based mechanism this whole redesign already uses
  for struct/enum identity — rather than guessing a package name from `prop.owner`'s first dot-segment),
  not deferred again, but genuinely sized at that item's own plan time, not asserted here as free.
- `propedit.effective_value` (not just `_resolve_one`) needs an actor-optional variant for the
  shared resolver's own default resolution — its FIRST statement is `_stored_map(actor)`, and
  `actor` threads through the rest of its body (the drill-down loop, `full_struct_text`'s merge), not
  isolable the way `_resolve_one`'s two leaf calls are. A synthetic empty-props actor, or a new
  actor-less entry point into `propedit.edit`, are both plausible — pick one at plan time with real
  code in front of you, not asserted here.

**Two more real gaps, sized here honestly rather than asserted as free — real work for the plan
stage, surfaced by v17's own review, not fully resolved by this design**:

- **Client-side compute cost, once resolution moves off the server, is unbudgeted.** Because
  resolution must be synchronous (§4's own requirement — a worker thread would reintroduce an
  async wait), `parse_package` over a 1.9-27 MB file and each cold per-class resolve both run on
  the browser's main thread. This document's only real timing data is the Python benchmark
  (25-183ms/class) — there is no WASM equivalent yet, no answer for whether a cold resolve on a
  complex class (well past `DeusEx.u`'s per-class average) could visibly freeze the UI for one
  frame, and no decision on whether parsing happens at fetch time or lazily on first class-use
  (§4 currently allows either). A freeze is not literally "a spinner," but it is the same kind of
  stall the owner's requirement exists to prevent — real WASM benchmarks belong at plan time, once
  the port exists to measure.
- **Cross-reload persistence relies on an unverified browser assumption.** §4/Non-goals rely on
  `Cache-Control: no-cache` plus the browser's own HTTP cache to make a reload's package fetches
  cheap (a `304`, not a re-download) without building the IndexedDB persistence layer this pass
  explicitly defers. Browsers are known to refuse or evict very large single cache entries, and
  the packages this design explicitly accepts downloading in full (§0's Non-goal) run to 18-27 MB
  — if the browser doesn't actually retain those, every reload re-downloads tens of MB instead of
  taking a cheap conditional hit. Not measured here; worth a real check before relying on it.

Everything else the prior review passes raised is resolved above by real investigation of the actual
resolution code, not left as a judgment call.

## Related

- `dev/docs/board/inbox/effective-props-resolution-15-47-slower-per/` — a ~15-47%/actor perf cost from
  the Critical-1 struct-member fix. This redesign's own restructuring (splitting the actor-scoped walk
  out, §1) is a natural place to also address the `_stored_map(actor)` re-fetch-per-leaf inefficiency
  that item names — not required by this spec, but touches the same code, worth doing in the same pass
  at plan time.
- `dev/docs/board/someday/gui-inspector-editing-write-back-for-props/` — the deferred editing item
  whose own "reset to default... already available at no extra cost" claim was already flagged as
  inaccurate. This spec's shared resolver IS that real class-independent default resolution — worth
  a follow-up correction to that item once this lands.
- `dev/docs/board/to-spec/shared-rust-core-for-class-schema-resolution/` — this spec DEPENDS ON it
  (see `overview.md`'s `depends-on`): ALL resolution/walk logic (Super-chain merge, default decode,
  canonicalization, struct/enum shape) is designed and built there, native + WASM, called from BOTH
  entry points this spec relies on (`resolve_class` for shape+defaults, `resolve_actor_props` for
  `/scene`'s own per-actor values — the v17 fix round widened that item's scope to cover the
  second one too, closing the two-implementations gap the first review found). This spec owns the
  raw-file endpoint (§0), `/scene`'s wire SHAPE (§2 — its resolution is the dependency's job now),
  and the frontend's fetch/render integration around that core (§4). See "What changed, v16 → v17"
  and the "v17 fix round" entry for the full split rationale.
- `dev/docs/board/to-plan/gui-builder-brushes/` (a sibling worktree branch, not yet on master) —
  reconciled 2026-09-24: no design conflict. That spec exposes UED22's builder brush as one ordinary
  `SceneActor` by reusing `_build_actors`/`scene.py:571` as an opaque per-actor serializer — it never
  reads or depends on `props`' internal shape, and keeps Location/Rotation as `SceneActor`'s dedicated
  fields, same as this spec's own `TYPED_FIELDS` handling. Both specs substantially rewrite
  `_build_actors` for different reasons (this one for the sparse leaf-path map; that one to synthesize
  a one-actor overlay from a `_LoadedTrunk`), so whichever plan/build lands SECOND on master will hit a
  real merge conflict there and must re-read the first's actual landed code, not plan against a stale
  signature.

## What changed, v1 → v2 → v3 → v4 → v5 → v6 → v7 → v8 → v9 → v10 → v11 → v12 → v13 → v14

**v13 → v14**: field-naming uniformity, directed by the owner directly — "always `default_value`. A
struct value is still a value. Uniformity." v13 (and every round before it) used TWO field names for a
leaf's resolved default: singular `default_value` for a scalar/enum leaf, plural `default_values` for a
struct or array leaf. Rejected: one field name, `default_value`, at every kind, no exception — a struct's
default is a dict, an array's is a list, a scalar's/enum's is a string, but the KEY never changes, only
the JSON value's TYPE does. Renamed every occurrence in the live design (§1-§4, `Design` section) from
`default_values` to `default_value` — 27 occurrences across every JSON worked example and every prose
reference, including the two-field-name justification paragraph itself (§1's `LightType` example, now
rewritten to state the uniform rule instead of the split it originally existed to explain). `stored_value`
(an unrelated `/scene`-only field, never part of this naming question) is untouched. All 12 JSON fences in
the document still parse. This changelog's own prior entries (v1 through v13, below) are left as accurate
history of what each round actually shipped at the time — not retroactively rewritten.


**v12 → v13**: small, targeted addition, caught by the owner directly ("where's enums?"). §1 stated the
rule that a top-level enum leaf (a class's own direct property) carries `"kind": "enum"` + `"type"` +
its own `default_value` — but the only concrete worked example anywhere in the document
(`Core.Scale.ESheerAxis`) is a struct-MEMBER-nested enum, never the far more common standalone
top-level case. Added a real, script-verified example: `Engine.Light.LightType` (`owner=Engine.Actor`,
`category='Lighting'`, real default `'LT_Steady'`), its type key `Engine.Actor.ELightType` (resolved
the same `(package, outer, name)` way as everything else — `Engine.u` export #2663, `outer=Actor`,
correctly resolved via `pkg.name_of_ref` not a raw name-table lookup, the same bug class this
document's history already caught once), and its real 10-value list. Also confirmed the correct field
name for this leaf: singular `"default_value"` (the plural `"default_values"` is reserved for a struct
leaf's per-member dict or an array leaf's per-index list, never a plain scalar/enum leaf with one
value) — flagged directly by the owner before this fix landed.

**v11 → v12**: a real process failure, caught by the owner directly rather than a review pass. Early in
this spec's design the owner gave an explicit instruction — "etag with checksum of .u" — a real checksum/
hash. The `ETag` formula that landed already computed a genuine `sha1` over per-package stat tuples (not
raw `.u` content, for the real cost/multi-file-dependency reasons stated in that section), but two things
were wrong: (1) it was missing the version component `schema_cache.cache_key` — the exact mechanism it
claims to mirror — already includes, a real, concrete completeness gap (confirmed directly against
`schema_cache.py:284-291`'s own code: `cache_key`'s real key string is `f"{SCHEMA_CACHE_VERSION}
\0{realpath}\0{size}\0{mtime_ns}"`, four components; the `ETag` recipe's own prose only ever named three),
and (2) the formula was described informally enough in prose that it could be read — and was read — as a
bare stat-tuple label rather than the real hash it already was, which is not what "checksum" was ever
supposed to leave ambiguous. Fixed: the exact formula is now spelled out as real, runnable code
(`hashlib.sha1(...)`, matching `cache_key`'s own real code line for line, extended from one package's stat
tuple to every package on the composed search path), with `SCHEMA_CACHE_VERSION` folded in so a resolver
CODE change (not just a `.u` file edit) also invalidates the `ETag` — closing the version-drift gap a
review had already found and this draft's fix for it never actually landed in the formula itself. Also
fixed, from the same read-through: §2's worked example wrongly restructured `/scene`'s real `payload.actors`
array into a name-keyed object (nothing else in this design proposes that, and every real consumer still
expects an array); and §2's `Location=(X=100)` example wrongly said the unstated `Y`/`Z` axes fill from
`types["Core.Vector"]`'s own default — `types` entries carry no default at all (the C1 fix, stated
elsewhere in this same document) — corrected to `Location`'s own class-entry `default_values`, the same
mechanism every other leaf already uses.

**v10 → v11**: a review of v10 found no Critical issues, confirmed all of v10's four specific fixes hold
(independently re-derived, all matched), and found 4 further Important items, all fixed here with real
verification, none a design change. **Fix 1** the enum-resolver-bug scope numbers ("30 real classes"/
"~32 real properties," three sites: §1's evidence paragraph, the Open Questions gap-list entry, the
v9→v10 changelog entry) didn't reproduce — measured precisely, two independent methods agreeing exactly:
`actionButtons: S_ActionButtonDefault` is declared ONCE, on `DeusEx.MenuUIWindow`, and inherited
unchanged by **29** real classes (`MenuUIWindow` itself plus 28 `DeusEx.u` descendants, none of which
override it); `S_BarButton` and `S_KeyDisplayItem` are each declared on exactly 1 class. **31 real
`(class, property)` pairs total**, across **30 distinct classes** (`MenuScreenCustomizeKeys` is hit
twice, by two different properties — which is why the class count and property count diverge). All 3
sites corrected. **Fix 2** the class-schema-only variant of `_resolve_typed_fields` was described as a
pure subtraction (skip the actor-touching calls, keep the rest) but this is wrong in two real ways:
(a) `MainScale.SheerAxis`'s `default_value` is the RAW ordinal `"0"` TODAY, not the canonicalized name
`"SHEER_None"` the worked example showed — script-verified directly by running `_resolve_typed_fields`
against a real `Engine.Brush`-descended actor; `_resolve_typed_fields` never calls
`_canonicalize_enum_text`, unlike `_resolve_one`'s own enum branch. Fixed: stated as a real, NEW,
INTENTIONALLY-NAMED visible-value change (per the Goals section's own commitment to name every one, same
as the dequote case) that the class-schema variant needs an explicit new canonicalization step to
produce, not something free. (b) the `Core.Scale.ESheerAxis` key was claimed to fall out "by
construction, since both paths ultimately resolve the same real export" — false; `_resolve_typed_fields`
resolves no export at all, it reads the hardcoded `typedprops.ESHEER_AXIS` tuple directly. Fixed: framed
as a real, explicit code change this path needs (emit `Core.Scale.ESheerAxis` instead of the current
hardcoded `"typedprops.ESheerAxis"` string), mirroring how the adjacent `EHAlign` case is already
honestly framed. **Fix 3** one sentence said "a plain member array (scalar/enum elements) needs only
`array_dim` + `kind`, no `type`/`element_type` at all" — directly contradicting the already-settled rule,
stated twice elsewhere in the same section, that an array-of-ENUM leaf DOES carry `element_type`. Fixed:
split into two correctly-scoped statements — a member array of plain SCALARS needs no type reference; a
member array of ENUMS still needs `element_type`, exactly like a top-level array-of-enum leaf. **Fix 4**
the `iconInfo` worked example (`array_dim: 7`) showed only 1 of 7 real `default_values` entries, eliding
the other 6 with a justification ("matching this document's own elision convention") that doesn't
actually describe any convention present elsewhere in the document — every other array example
(including a LONGER, equally-identical 16-entry list for `AlliancesEx`) is shown in full. Script-verified
all 7 real entries are genuinely identical; fixed by listing all 7 in full, removing the elision and its
inaccurate justification.

**v9 → v10**: a review of v9 found no Critical issues, confirmed all of v9's four specific fixes hold
(independently re-derived, all matched), and found 3 further Important items, all fixed here with real
verification, none a design change. **Fix 1** §1's enum-keying evidence over-claimed that
`S_ActionButtonDefault.Align` → `Extension.ExtensionObject.EHAlign` resolves through the real production
path today — the KEY is right (confirmed: `EHAlign` really is `Extension.u` #9, `outer=ExtensionObject`),
but the path to it isn't: `S_ActionButtonDefault.Align`/`S_BarButton.Align`/`S_KeyDisplayItem.inputKey`
are all IMPORTED enum members, and `serve/scene.py::_enum_names_via` has the IDENTICAL bare-owner bug
already named for `_struct_members_via` (`prop.owner.split(".", 1)[0]` treats a bare struct name as a
package name) — confirmed with a real `SchemaError`. Scope is broader than the 3 named properties:
script-verified 31 real `(class, property)` pairs across 30 distinct classes in `DeusEx.u` hit this (29
classes reaching `S_ActionButtonDefault` via one shared declaration on `MenuUIWindow`, not just the 2
originally cited). Folded into Open Questions as the SAME root
cause as the already-known struct-member resolver bug (both helpers share the identical buggy line), not
a new, separate gap. **Fix 2** the size-estimate section named `DeusExUI.u`/`DeusExCharacters.u` as the
worst-case package for this endpoint's cost, reasoning from `.u` FILE SIZE (27.4/19.2 MB) — but the
response scales with CLASS COUNT, and those two files are almost entirely non-class content:
script-verified `DeusExUI.u` has exactly 1 class, `DeusExCharacters.u` has 4, while `DeusEx.u` — the
SMALLEST of the three as a file (1.9 MB) — has 1166, three orders of magnitude more. Fixed to name
`DeusEx`/1166 classes as the real worst case the caching design needs to handle well. **Fix 3** no wire
shape existed for a struct MEMBER that is itself a static array (only a plain scalar member and a nested
struct member were covered) — real, reachable case, script-verified: `DeusEx.DamageHUDDisplay.iconInfo`
(`sIconInfo[7]`)'s member `DamageType` is itself a `Name[3]`. Fixed: a `types` member entry can carry its
own `array_dim` (+ `element_type` if the array's own elements are struct-typed), and the class entry's
`default_values` nesting extends to a LIST for such a member (same full-list rule as everywhere else) —
real worked example added, also demonstrating the exclusion filter (`Icon`, an `ObjectProperty` member of
the same struct, correctly dropped) and nested-struct default composing at once (`Color`, `Core.u` #536,
`outer=Object` → `Core.Color`). Also fixed: 4 stale line citations (`propedit/base.py:113-115` →
`:111-112`, pointing at the wrong branch; `effective_props.py:337` → `:331`/`:336`/`:353`;
`app.py:248-275` → `:248-272`; `serve/scene.py`'s `_struct_members_via` "line ~589" → the real line 580)
and `overview.md`'s outer-keying summary, which described only 2 cases (owning class / universal `Object`
root) — added the 3rd (an owning STRUCT, `ESheerAxis`'s own real case) already correctly stated in the
spec body.

**v8 → v9**: a review found no Critical issues — the core design (identity scheme, wire shapes,
defaults-per-class split, caching, frontend walk) is confirmed sound, every re-checked number held. Four
Important, purely prose-level corrections remained, all fixed here with real script verification, none
requiring a design change. **I1** the "34 real properties" exclusion-filter count didn't reproduce under
any interpretation two separate reviews tried — measured precisely this pass: **33**, defined exactly as
"real property declarations, deduped by `(owner, name)`, reachable past `HARD_REJECT`/`TYPED_FIELDS`/
`is_computed_key`, walking every class's own resolved (own + inherited) property list across every class
declared in `Engine.u`+`DeusEx.u`, whose struct type's shape contains at least one excluded-kind member."
**I2** the sole worked example for the `types` exclusion filter, `Engine.Actor.Region`, is itself a
COMPUTED key (`is_computed_key('region') == True`) — skipped by the top-level walk before the
struct-shape question is ever reached, so it could never actually demonstrate what it claimed to.
Swapped to `Engine.Pawn.FootRegion` (script-verified: not computed, same `PointRegion` shape, same
`Zone:ObjectProperty` exclusion — the key is unchanged, `Engine.Actor.PointRegion`, only which property
anchors the example changed). Also dropped `OldLocation` from a nearby `Core.Vector`-category list for
the identical reason (also a computed key). **I3** the enum-keying rule (`f"{prop.owner}.{prop.type_name}"`)
was correct for the dominant real case but wrong for an enum reached as a struct member, where
`prop.owner` is a bare, unqualified struct name rather than a package-qualified class — script-verified
9 real enum-typed struct members exist in the corpus, 8 of which have this exact problem (only
`ESheerAxis`, the one case already special-cased, doesn't). Fixed by unifying the rule: an enum is keyed
exactly the way a struct already is — off its OWN export's `outer` field, never the referencing
property's `owner` — which gives the identical, already-correct answer for the dominant top-level case
(script-verified: `DeusEx.AlarmLight`'s `ESkinColor` has enum-own-`outer` == `prop.owner`, both
`AlarmLight`) AND the correct, package-qualified answer for all 9 struct-member cases (3 confirmed
directly: `DeusEx.BarkInfo.barkMode` → `DeusEx.BarkManager.EBarkModes`, `DeusEx.sUserInfo.accessLevel` →
`DeusEx.Computers.EAccessLevel`, `DeusEx.S_ActionButtonDefault.Align` → `Extension.ExtensionObject.EHAlign`,
the last one a genuinely cross-package import) — removing `ESheerAxis`'s special-case framing entirely,
since it's now just one instance of the one general rule. **I4** the enum wire shape was described three
contradictory ways: one place said an enum leaf keeps the "familiar" scalar shape (no `"type"` ref),
another correctly required one; one place said scalars/enums both have "no shape worth normalizing,"
directly contradicting the enum `types` entry's own reason to exist; §4 (frontend rendering) never
mentioned how an enum leaf's `"type"` ref gets consumed at all. Settled to one consistent statement: a
plain SCALAR leaf has no `"type"` ref (genuinely nothing to normalize); an ENUM leaf DOES, the same
mechanism a struct-typed leaf already uses; §4 now states explicitly how an enum `"type"` ref resolves
(`types[key]["values"]`, mirroring old `ScenePayload.enums`) AND that nothing in the current Inspector
actually reads it for display today (verified directly: `shownValue` never references `enum_type`/
`values`, already prints canonicalized name text) — present for completeness and future editing work,
not an oversight that §4 stays silent on it.

**v7 → v8**: a review of v7 found the same worked-example bug class recurred a FOURTH time, plus two
more real issues, and named a real gap in v7's own methodology. **C1** `AlliancesEx`'s worked example
showed only 1 of 16 real `default_values` entries, no elision marker, in the SAME JSON block as the
`InitialAlliances` example v7 had just expanded to its own full 8 entries — script-verified all 16 real
per-index defaults for `DeusEx.Karkian.AlliancesEx` (all 16 genuinely identical: `AllianceName="None"`,
everything else zeroed) and listed all 16, closing the gap for real this time; `WeaponPriority`'s own
`"..."` elision (flagged as indistinguishable from a real value) is also now the full 50-entry real list.
**C2** 17 sites encoded the real string value `"None"` (UnrealScript's textual none/unset-reference
convention — `AllianceName=None` is a stated, resolvable default, not an absence) as JSON `null` —
script-verified `effective_value` genuinely returns the 4-character string `'None'`, never `None`/
`null`, at every one of these leaves; fixed everywhere (`InitialAlliances`, `AlliancesEx`,
`AllianceTrigger.Alliances`). **C3** the spec claimed `ESheerAxis` "is not a package export, it's a
hardcoded Python constant" — false; script-verified it's a real `Enum` export, `Core.u` #47,
`outer=Scale`, real values matching `typedprops.ESHEER_AXIS` exactly. This wasn't cosmetic: under the
false premise, two different code paths (the `TYPED_FIELDS` special case vs. the generic schema walk)
would have keyed the SAME real enum two DIFFERENT ways in `types`. Resolved by keying `ESheerAxis` the
same way a struct is keyed — via its own export's `outer` field, since it's struct-nested (inside `Core.
Scale`) rather than class-nested — giving one real key, `Core.Scale.ESheerAxis`, for both paths. **I1/
I2** (entangled with C3): no wire shape existed anywhere for an ENUM `types` entry, despite the Goals
section requiring "Struct AND enum type shape is normalized... by one mechanism," and one worked example
(`Core.Scale`'s own `SheerAxis` member) mislabeled a real enum-typed struct member as plain `"kind":
"byte"` — `ClassCtx.enums` genuinely resolves it to the enum branch (script-verified), same as every
other enum-typed struct member this design already handles correctly (`sUserInfo.accessLevel`). Fixed:
an enum `types` entry is `{"kind": "enum", "values": [...]}` (the ordered value-name list
`ScenePayload.enums` used to hold), referenced by a member/leaf the SAME way a struct-typed one already
is (`"kind": "enum"` + `"type": "<key>"`) — real worked example added, `Core.Scale.ESheerAxis`'s own
7 real values. Also fixed, a smaller leftover: one sentence implied defining `MainScale`'s nested
`default_values` shape also makes `TempScale` resolvable — it doesn't; that's a separate, still-open
RESOLVER bug (Open Questions), unrelated to whether a wire shape exists for the data once resolved —
reworded so the two aren't conflated. **Methodology gap, named and closed**: v7's rule ("every JSON
block is script-generated") only covered JSON fences — C3 was a false claim sitting in plain PROSE,
which the rule never touched, and is exactly where the review said the next recurrence would live. The
rule is now stated to cover every corpus claim in the document, fenced or not (see the opening
paragraph above).

**v6 → v7**: the SAME bug class (a hand-transcribed worked example with a wrong/fabricated detail) had
recurred three revisions running, each time in the exact JSON block just "fixed" the round before —
v5's `AlliancesEx` example, then v6's own adjacent `InitialAlliances` example in the same JSON block.
Methodology change for this pass, per the owner's own direction: every JSON worked example claiming to
show real data is generated from a script actually run against the real corpus (`.venv/bin/python3`,
`uned/UED22/*.u`), its real printed output copied verbatim, never hand-typed from memory of a prior
round. A review of v6 found 2 Critical + 4 Important problems, all fixed here: **C1** `InitialAlliances`
was fabricated three ways (wrong package `Engine.Actor`→real `DeusEx.ScriptedPawn`; wrong struct name
`AllianceInfo`→real `InitialAllianceInfo`, which doesn't exist under the old name anywhere in the
corpus; wrong category `null`→real `"Alliances"`) — replaced with real, script-verified data, and
upgraded into a genuine worked example of the LIVE two-way `InitialAllianceInfo` collision
(`DeusEx.ScriptedPawn.InitialAllianceInfo` vs `DeusEx.AllianceTrigger.InitialAllianceInfo`, same struct
name, different `outer`, correctly different keys) rather than a single non-colliding property. **C2**
the spec contradicted itself on whether `types` entries carry `category` (said twice they don't, once
that they do, and the JSON had it) — settled to ONE rule, `types` never carries `category`, fixed
everywhere including the one leftover sentence that still listed it. **I1** excluded property kinds
(`ObjectProperty`/`ClassProperty`/`PointerProperty`/dynamic-`ArrayProperty`) were never explicitly
filtered out of a `types` entry's shape — now stated explicitly and shown with a real case,
`Engine.Actor.Region`'s `PointRegion` shape (present on every actor), whose real unfiltered member list
includes an `ObjectProperty` (`Zone`) alongside two non-excluded members. **I2** `"category": null` on
the wire would have broken the frontend's non-nullable `category: string` grouping key — fixed by
always emitting the real resolved category string (`"Uncategorized"` for a `None`-categorized property,
matching `_category_for`'s own real fallback), never JSON `null`, verified with zero remaining
occurrences. **I3** the array-default encoding was inconsistent (a scalar array said "index = list
position," a struct array's example instead run-length-collapsed with no stated decode rule) — settled
to ONE encoding, a full explicit list, one entry per real array index, matching what the frontend's
positional-lookup walk already assumes; `InitialAlliances`'s real 8-entry list (not collapsed) now
demonstrates it. **I4** no wire shape was defined for a nested struct's own `default_values` (e.g.
`MainScale.Scale.X`, three levels deep) — specified explicitly (mirrors the shape tree's own nesting,
a dict-of-dicts) and grounded with a real worked example, `Engine.Brush.MainScale`'s real default
`(Scale=(X=1,Y=1,Z=1),SheerRate=0,SheerAxis=0)` against `Core.Scale`'s real nested-`Vector` shape.

**v5 → v6**: a review found v5's WIRE SHAPE had 5 real structural gaps — not evidence fabrication this
time (v5's corpus grounding was actually good), genuine design gaps. Fixed: (1) `default_value` cannot
live on the shared `types` entry — defaults are per-class, not type-intrinsic; proven with
`Core.Rotator`'s real, genuinely different `RotationRate` defaults on `Karkian` (`Yaw=30000`) vs `Rat`
(`Yaw=65530`) — `types` now carries SHAPE only, each class entry carries its own `default_value`s
alongside a `"type"` shape-reference. (2) no wire shape existed for a static array of plain
scalars/enums — added, worked example `DeusExPlayer.WeaponPriority` (`Name[50]`, real distinct
per-index defaults). (3) nothing specified where an actor's STATED `Location`/`MainScale`/`PostScale`
go in `/scene`'s sparse map (only their DEFAULTS were covered, in §1) — these three bypass the generic
`ctx.schema()` walk entirely (`TYPED_FIELDS`, never mirrored into `actor.props`), so they need their own
explicit sparse-map rule reusing `_stated_axes`/`_stated_scale_members`, now added. (4) v5's claim that
`uedcli_native` was unavailable in this sandbox, blocking member-shape verification, was itself wrong —
it's installed, just needs `.venv/bin/python3` rather than the system interpreter; run for real, closing
the one open question v5 left (the two `sUserInfo` shapes genuinely differ; `XAIParams`'s 9 don't). (5)
the worked example taught the wrong keying rule — `AlliancesEx`/`AllianceInfoEx` is INHERITED from
`DeusEx.ScriptedPawn`, not locally declared on `Karkian` as v5 claimed; real key
`DeusEx.ScriptedPawn.AllianceInfoEx`, real 4-member list (not 3), real `Uncategorized` category (not
`"AI"`), real `None` default (not `""`) — all re-verified directly in this pass, not copied from any
prior draft. Also fixed: a leftover `Engine.Vector` citation after §1 had already corrected to
`Core.Vector` elsewhere; §4's frontend-walk description updated to match the corrected shape (defaults
read from the class entry, `types` consulted for shape only). Two smaller, honestly-sized
implementation-surface gaps are now named in Open Questions rather than silently absorbed: a real
pre-existing resolver bug in nested-struct-within-struct member resolution (`Engine.Brush.TempScale` and
6 other real cases), and `propedit.effective_value` needing more than `_resolve_one` alone to become
actor-optional.

## What changed, v1 → v2 → v3 → v4 → v5 (superseded by the entry above; kept for history)

**v4 → v5**: v4's own corpus re-verification was contaminated by a real tool-use bug — resolving a
`Struct` export's own name via `Package.name_of_ref(e['nm'])`, which resolves a SIGNED OBJECT REFERENCE
(0/export/import), not `e['nm']`'s actual raw, unsigned name-table index; the correct call is
`pkg.names[e['nm']]`. This produced two wrong conclusions in v4, both corrected in §1: the cited
same-package collision example (v4 said `CarcassName` ×9; the real name is `XAIParams`, same 9-owner
shape, `CarcassName` doesn't exist under that name in the corpus) and the claim that `Vector`/`Rotator`/
`Scale`/`Plane`/`Color` couldn't be resolved at all (they resolve cleanly once the bug is fixed — `Core.u`,
not `Engine.u` as the owner's own worked example assumed). Fixing the evidence surfaced one genuine new
refinement the wrong data had hidden: every one of `Core.u`'s 9 real structs has `outer` pointing at
`Object` (the universal root class), never literally `0` — so v4's literal "omit outer when `outer == 0`"
rule would never have fired for the exact global-struct case it was written for. Refined to "omit when
absent or resolves to `Object`," which now correctly produces `Core.Rotator` (not `Core.Object.Rotator`)
for the flagship worked example. `sUserInfo` (v3's original cited collision, spelled slightly differently
by case — same `FName`) is also confirmed resolved by `outer` (`ATM` vs `Computers`), closing that thread
for real this time. Member-shape verification (do the two `sUserInfo` exports, or `Rotator`, actually
have the member lists this design assumes) remains unverified — needs `uedcli_native`, unavailable in
every sandbox this spec has been drafted in so far; flagged honestly rather than assumed, though it
doesn't affect the identity mechanism's own correctness. No other section of v4's design was touched.

## What changed, v1 → v2 → v3 → v4 (superseded by the entry above; kept for history)

**v3 → v4**: the owner named the exact fix for v3's open struct-collision question — key structs on
`(package, outer, name)`, the engine's own scoping mechanism (a struct export's own `outer` field
names its owning class when it's locally-declared, `0` when it's genuinely global), framed explicitly
as the same pattern this codebase already ships for texture identity (`Package.Group.Name`). Verified
directly: every real same-package struct-name collision found in the corpus (`CarcassName` ×9 across 9
different owning classes, plus three more two-way collisions) is cleanly resolved by `outer` with no
collision-detection fallback needed — v3's proposed export-index-suffix fallback is no longer required
and is removed. The specific case v3 cited as motivating this (`SUserInfo`) could not be reproduced in
this pass — a targeted corpus search found no `Struct` export by that name anywhere in `uned/UED22` —
reported as a likely citation error rather than silently dropped, since the underlying collision RISK
is independently reconfirmed by the cases that WERE found. One new, real gap surfaced while verifying
this: `Vector`/`Rotator`/`Scale`/`Plane`/`Color` — the structs this design's own worked examples are
built around — could not be confirmed to resolve through `resolve_type_export` at all in this sandbox
(two independent attempts hit unrelated exports; the full production decode path needs `uedcli_native`,
not available here). Flagged as a new open question rather than assumed away, since the whole
struct-identity mechanism hinges on it working for exactly these types.

## What changed, v1 → v2 → v3 (superseded by the entry above; kept for history)

**v1 → v2**: a design review found v1's per-leaf `stored_value`/`effective_value` split didn't
structurally hold together — the frontend's "show all" needed a real tree union the draft only gestured
at; array element identity broke once unstated elements were omitted from an otherwise position-indexed
list; the `effective_value`-differs-from-`stored_value` trigger essentially never fired as specified;
the default view's existing partial-struct-shows-defaults-inline behavior would have silently regressed;
`isExplicit`'s `!== null` check breaks under a sparse shape; the typed Location/MainScale/PostScale
fields weren't covered by either the old `/scene` rule or the new endpoint's "same walk" claim; the
proposed single-package-content-hash `ETag` was both too expensive and unsound. v2 moved to "normalize
shape everywhere, ship only a sparse value overlay per actor," which dissolved most of those findings
rather than needing individual patches.

**v2 → v3**: a second, clean-context review plus the owner's own direct corpus-verification requests
found v2 got type-identity keying backwards in one place and unverified in another — v2 keyed BOTH
structs and enums on the same resolved-package+export-index scheme, which is wrong for enums (verified:
28 real `ESkinColor` declarations, 21 distinct value lists, would have collapsed into one incorrect
shared definition under v2's scheme — reverted to today's already-correct class-based key) and,
separately, v2's OWN "Current state" section overstated enum locality as universal (101 of 10,150 real
enum properties are actually imported — corrected without changing the keying decision). The struct
side of v2's scheme (package+export-index) was directionally right but never verified against real
same-package name collisions — this revision found one (`SUserInfo`, genuinely different shapes sharing
one name in `DeusEx.u`) and reports it as an open question rather than silently adopting the owner's
literal "package+name" request, which the same evidence shows is unsafe as stated. v2 also asserted a
new caching mechanism was needed for the class-schema endpoint's cost (C3) without checking whether one
already existed — it does, partially: `schema_cache.py`'s own docstring already scopes its future "v2"
(the source file's own version number, unrelated to this SPEC's v2/v3) as covering exactly this need,
just not yet built. v2's C2 gap (no worked example of the `types` dict) is fixed directly — §3 above —
which is also what surfaced the struct-collision risk in the first place, confirming the missing example
was the real root cause the second review named. v2's Goal 3 ("no visible regression... not what the
Inspector displays") contradicted its own §2 (dequoting IS a visible change) — narrowed to be accurate
rather than forcing an artificial zero-diff constraint that would undo a different, deliberate goal
(server-side canonicalization). The `ETag`'s 304-short-circuit-before-resolution and `Cache-Control`
gaps (I6) are both closed with concrete mechanisms rather than left implicit.

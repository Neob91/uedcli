# `actor prop set|unset|get` — subcommand grammar, dot-paths, default-value fallback

**Status: BUILT 2026-07-18** (same day; see `board/done.md` + `architecture.md` "Class-property
schema, DEFAULTS & the `actor prop` verbs"). The §9 probe RESOLVED: partial values are
member-wise onto the CLASS DEFAULT (`spikes/2026-07-18-partial-value-import-semantics/`,
`unrealed/t3d.md`); the §5.2 to-be-RE'd layout landed corpus-verified 1914/1914
(`unrealed/class-schema.md` "UClass body"); the negative fact that v68 ScriptText carries no
defaultproperties block vindicated the binary-route decision. Spec review gate passed earlier
the same day (two cold reviewers, findings folded — [`decisions.md`](../decisions.md) 2026-07-18
10:02 + 10:30 UTC). All design decisions Andrzej's. Supersedes the inbox `[spec]` item
"`actor prop --get KEY` retrieval mode" (2026-07-18) and absorbs the p3 debug item
"`actor get <name> Location` prints nothing, exits 0".

This spec is ephemeral (see `CLAUDE.md`); on landing, fold what was built into
`architecture.md` (+ any new `.u`-format facts into `unrealed/`), and keep the decision record
in `decisions.md`.

---

## 1. Goal

Replace the flag-based `actor prop <name> --set K=V --unset K` surface (and the warty
`actor get`) with three subcommands sharing one validated grammar, and give property *reads* a
real contract: a read of an unset property returns the **class default**, decoded offline from
the game's own packages — never silence.

```
uedctl actor prop set   <actor> KEY=VALUE [KEY=VALUE ...]
uedctl actor prop unset <actor> KEY [KEY ...]
uedctl actor prop get   <actor> [KEY ...] [--kv]
```

Everything stays model-side (no editor), schema-validated, atomic per invocation, and reachable
via `--target` (level / stash / prefab) exactly like today's `actor prop`.

## 2. CLI surface

### 2.1 `set <actor> KEY=VALUE ...`

- Replaces `--set`. The old `--set`/`--unset` flags are **removed outright** (pre-release tool,
  no deprecation aliases).
- One invocation = one atomic edit: every token is validated before any mutation (today's
  contract). A consequence of the subcommand split: a mixed set+unset can no longer be one
  atomic invocation — accepted (decision 10:02 §1).
- A token without `=` is a grammar error (exit 2). `KEY=` (empty value) is a legal
  empty-string value, stored verbatim.
- The **hard-reject set is unchanged and applies to all three subcommands**: `Name`, `Brush`,
  and the mover-key bookkeeping `KeyPos`/`KeyRot`/`NumKeys`/`KeyNum` → exit 2 with the existing
  message (`get Name` / `unset KeyNum` / `get KeyPos.1` all included — author mover keys with
  `mover key`).
- Value verbatim-minus-quotes as today, with two additions:
  - **Vector/Rotator comma sugar** (decision §2, scoped by review ruling R1): the comma form is
    **interpreted ONLY when the schema says the prop is a `Vector`/`Rotator` struct** — then
    `KEY=4,5,-17` canonicalizes to the T3D struct form at store (`(X=4,Y=5,Z=-17)` /
    `(Pitch=4,Yaw=5,Roll=-17)`), and wrong arity or a non-numeric component → exit 2. **On every
    other prop a comma-bearing value is plain verbatim text** — `Group=cells,ambers` (the
    documented comma-joined group membership) and comma-containing strings keep working
    unchanged.
  - **Array tuple form** `KEY=(0=V,3=W)` — whole-value replace, §3.1.

### 2.2 `unset <actor> KEY ...`

- Replaces `--unset`. `unset Location` keeps its origin-reset routing (typed field, §6).
- **Whole-key unset of a static array clears EVERY stored element line** (`unset MultiSkins`
  removes `MultiSkins(0)`…`MultiSkins(7)`). Deliberate change: today's identity-match removes
  only an unindexed line and would leave `MultiSkins(2)` stored.
- Unset of a schema-valid key (or path) that is not currently stored is a **silent success**
  (today's semantics — idempotent).

### 2.3 `get <actor> [KEY ...] [--kv]`

- **Default output: one line per requested KEY, bare value only, in argument order** (decision
  §3). A key always yields exactly one line — arrays and structs render on one line (§4).
  All requested keys are validated **before any output** (the read analogue of
  validate-before-mutate). Repeating a key in `get` is legal (it's a read; line count still
  equals key count); the overlap/duplicate conflict rule (§3.1) applies to `set`/`unset` only.
- **Keyed `get` is the EFFECTIVE view**: stored value if present, else the class-default chain
  (§5), else the type's zero — rendered canonically per §4.
- **`--kv`**: same lines but `KEY=VALUE` (canonical spelling), designed to round-trip into
  `set`. Combining `--kv` with zero keys is legal (dump-all lines are already KEY=VALUE).
- **Dump-all**: `get <actor>` with zero keys is the **STORED view** — a different contract from
  keyed get, stated explicitly:
  - prints the typed `Location` field first (always — the field is always defined; an
    unmoved actor prints the origin), then every stored prop **in stored order**;
  - **values verbatim as stored** (no effective-view re-rendering — a stored partial
    `Rotation=(Yaw=8192)` prints exactly that; a stored enum ordinal stays an ordinal);
  - keys canonicalized to dot-path spelling (`MultiSkins(3)=X` prints as `MultiSkins.3=X`) so
    every printed token round-trips into `set` — the round-trip guarantee covers the printed
    tokens (identity/geometry/mover bookkeeping are excluded by the hard-reject rule and are
    NOT captured; dump-all is not a full actor snapshot — `actor show` is);
  - a stored prop the class schema does not know → **hard error, exit 2, naming the prop**
    (review ruling R4 — "let's see if this is ever a problem in real life").
- **Default fallback** (decision round 1 + §4-zero): a requested key with no stored value
  resolves through the class-default chain (§5); if no ancestor's defaults mention it either,
  get prints the **type's zero value** in canonical form (`0`, `False`, full-member zero struct
  `(X=0,Y=0,Z=0)`, `None` for object refs AND names, empty string) — get never silently prints
  nothing-and-exits-0. An **empty-string value renders as an empty line in bare mode** (the
  one unavoidable ambiguity; scripts that must distinguish use `--kv`).
- Unknown key, unknown struct member, or out-of-bounds index → exit 2 naming the offender
  (mirrors set).

### 2.4 Schema requirement (decision §6, precise scoping per review)

The no-fallback contract (decisions.md 2026-06-26 14:10) extends to reads: **whenever any token
of any subcommand needs the class schema, its absence is a clean exit 2** naming the problem
(no v68 install / no project / no games config) — there is **no degraded stored-only read
path** for schema props. Resolution stays **lazy** (today's mechanics): tokens that never touch
the schema — hard-rejects, and **typed-field-only invocations** (`get`/`set`/`unset` touching
only `Location`, §6) — succeed without the install, exactly as `set Location=…` does today.
Typed fields carry their own type knowledge, so no output silently changes meaning.

## 3. The dot-path grammar (decision round 4)

```
TOKEN     := KEY [PATH] ( "=" VALUE )?      # "=VALUE" required for set; absent for unset/get
PATH      := ( "." SEGMENT )+
SEGMENT   := <decimal integer>              # static-array index
           | <identifier>                   # struct member name
```

Examples: `MultiSkins.2`, `Location.X`, `Rotation.Yaw`, `VectArray.0.X`.

- **Dot-path only**: the T3D/UnrealScript `KEY(N)` spelling is **rejected on the CLI** with a
  hint naming the dot form (`MultiSkins(2) → use MultiSkins.2`). This is CLI grammar only — the
  **stored T3D keeps its native `Key(N)=` spelling** (t3d.md "Indexed static-array form");
  emit/parse are unchanged.
- Segments disambiguate by shape: all-digits = index, else member name. A segment matching
  `-?\d+` with a minus (`MultiSkins.-1`) gets an **index-flavored error** (out-of-range /
  invalid index), not a misleading "unknown member". Keys, member names, and enum values are
  case-insensitive (FName semantics) and echo in the class's canonical `.u` spelling.
- Paths recurse: an array of structs takes `Arr.0.X`; a struct containing a struct takes
  `A.B.C`. Every hop is schema-validated: index against `array_dim`, member against the
  struct's own member list decoded from the `.u` (§5.3); a miss names the failing segment.
- **Dynamic arrays (`ArrayProperty`) are out of scope**: whole-value set passes on type
  (verbatim, as today); a dot-index on one → exit 2 ("not a static array", existing message);
  their defaults are not decoded (an unset dynamic array reads as the empty zero value).

### 3.1 Whole-value vs targeted edit (decision round 4, confirmed all four)

`KEY=VALUE` (no path) is **whole-value replace**:

- Scalar/struct/object props: as today — the stored line becomes exactly the given value.
  `set LightHue=(H=1)`-style partial struct values store verbatim (assignment semantics;
  unmentioned members are NOT preserved from the previous stored value). For the typed
  `Location` field see §6 (**partial struct zero-fills** — review ruling R2).
- Static array, tuple form `KEY=(0=V,3=W)`: stores exactly elements 0 and 3
  (`Key(0)=V`/`Key(3)=W` lines) and **clears every other stored element** (decision round 3:
  the tuple is a full replace; targeted element edits are the dot form). Each element value is
  validated like a scalar of the element type; an element value may itself be a struct in
  balanced parens (array-of-structs). Indices out of bounds or repeated → exit 2.
  Corners: `KEY=()` → exit 2 (use `unset KEY`); a non-tuple whole value on a static-array
  prop (`MultiSkins=Texture'X'`) → exit 2 naming the tuple/dot alternatives.

`KEY.PATH=VALUE` is a **targeted edit** — it changes only the addressed element/member:

- **Array element** (`MultiSkins.2=V`): rewrites only that element's stored line; other stored
  elements untouched; an element line is created if absent.
- **Struct member** (`Rotation.Yaw=8192`): the containing struct value is re-emitted with just
  that member changed. Base value for the re-emit: the **stored** struct if present; if the
  prop is entirely unset, the **effective default** (§5) materialized explicitly — so
  `set X.Y=v` never silently zeroes sibling members that the default had non-zero. (Store
  explicit — decision round 4 Q3: uedctl never auto-drops zero/default members on write; a
  power user prunes with `unset`. **Consequence, see §10:** targeted struct edits and `--kv`
  round-trips therefore *store explicit default-valued members*, the exact shape the two open
  H3 post-verify items trip on — those items become more urgent once this lands.)
- `unset KEY.PATH`: removes that element line / that member from the stored value. Removing
  the last member of a stored struct removes the whole prop line. Unset of a path on an
  entirely-unset prop is a silent success.

**Intra-invocation conflicts** (`set`/`unset` only): two tokens whose targets overlap (same key
twice, a whole-value and a path under it, the same path twice) → exit 2 (extends today's
duplicate-key rule).

**⚠ Semantics probe (build-gating spike, §9):** whether the engine treats members *unmentioned
in a stored struct value* (and elements unmentioned in a stored array) as **zero** or as the
**class default** decides what `get` must report for them and what `unset KEY.PATH` effectively
does. T3D import likely edits member-wise onto the default-initialized object (⇒ class default),
but this is unverified — probe live before build (needs a class whose struct/array default has a
non-zero member). The spec's get/unset wording follows the probe result; the CLI grammar and
storage forms above do not depend on it.

## 4. `get` value rendering (keyed = effective view)

One line per key, always:

| requested | default mode prints | `--kv` prints |
|---|---|---|
| scalar key | `200` | `LightBrightness=200` |
| struct key | full explicit member form `(X=4,Y=5,Z=-17)` (every member, unmentioned ones filled per §3.1 probe) | `Location=(X=4,Y=5,Z=-17)` |
| whole array key | one-line tuple, full dim, `(0=None,1=Texture'Skins.Wood',…)` (decision round 3: never one element per line — line count must equal key count) | `MultiSkins=(0=None,…)` |
| `KEY.N` / `KEY.Member` path | the single element/member, bare (`8192`) | `Rotation.Yaw=8192` |

- Struct values nest in balanced parens; object refs render `Class'Package.Name'`; bools
  `True`/`False`; a name's zero renders `None`; empty string renders an empty line (bare mode).
- **Enums render their name** — including a *stored ordinal* remapped to its name (keyed get is
  the effective view; dump-all keeps stored text verbatim, §2.3). §5.3's cross-package
  machinery is also wired into **enum resolution**, so imported enums (today un-enumerable,
  `()`) become enumerable — upgrading set-validation, get rendering, and find equivalence
  uniformly; an enum that still can't be resolved prints the ordinal.
- `--kv` output is round-trip clean: whole-key lines re-enter `set` as whole-value replaces
  reproducing the same effective state; path lines re-enter as targeted edits.

## 5. Default values from the packages (decision round 2: bytecode walker + unified core)

The schema today carries property *types* only. Default *values* live at the **tail of the
UClass body**, behind the script bytecode, which has no on-disk length — reaching them requires
a full `SerializeExpr` token walker (`unrealed/class-schema.md`: naive skipping lands in
garbage). Andrzej chose the **binary route** (exact, works even source-stripped) over parsing
the shipped `.uc` ScriptText's `defaultproperties` text (unverified for v68, and text-parsing
is a second grammar).

### 5.1 `upackage.py` — ONE low-level package core (decision: unified utilities)

`.u .dx .utx .uax .umx .unr` share one format; today the low-level parsing is duplicated:
`dxpkg.py` and `utexture.py` each own a compact-index + header + name-table copy (`uprops.py`
imports `_read_compact_index` from `dxpkg` but re-implements the header/name/export parsing).
This change extracts a single shared reader module (working name `upackage.py`):

- header (v61/68/69), name/import/export tables, FCompactIndex, FString, lazy-array skip;
- the **tagged-property-list parser** (tag name, type nibble, size code, array index, struct
  name, value bytes) — needed for the defaults block, already half-present in `utexture`;
- the object-ref helpers (`name_of_ref`, import-package resolution, **outer-chain
  qualification** for rendering full `Package[.Group].Name` refs).

**Scope (decision §7): core + `uprops` migrate now; `utexture`/`dxpkg` migrate as a follow-up
board chore** (both are validated byte-identical decoders — churning them here risks
regressions for zero feature gain).

### 5.2 The script walker + defaults decoder (new, in/next to `uprops.py` on the core)

- `SerializeExpr` token walker for the v68 opcode set (~60 opcodes), used to skip
  `UStruct.Script` and land on the `UState`/`UClass` tail. **No-fallback contract**: an
  unknown opcode or a cursor that doesn't land exactly where the layout demands raises
  `SchemaError` — never a guess. Validated in tests by walking **every class in every game
  `.u`** and asserting clean landings (the same corpus-integrity style that validated the
  UProperty decode).
- **To-be-RE'd during build (evidence → `unrealed/` docs):** the repo's format docs stop at
  "UClass(ClassFlags, …)" — the opcode set, the **post-script UState/UClass field layout**
  (ClassFlags, GUID, dependencies, package imports, config name…), the exact location/shape of
  the trailing **defaults tagged-property list**, its **sparse-diff-vs-super** semantics, and
  the **in-struct binary value encodings** (bools, name/object compacts, nested structs,
  member static arrays — variable-width) are all currently *unverified assumptions*, not
  established facts. The corpus-integrity test gates the layout; value-DECODE correctness needs
  its own oracles (below), since a wrong ref/value rendering can still land cleanly at EOF.
- Defaults block: the trailing tagged-property list of the UClass → `{(prop, index) → value}`
  with per-type **text rendering to the T3D forms** (§4). Struct defaults render member-wise
  via the struct member schema (§5.3); object refs render fully qualified via the outer chain.
- **Value oracles (test plan §11):** (a) live-confirmed editor-export facts — `Engine.Light`
  defaults `LightPeriod=32`, `LightPhase=0` (confirmed live 2026-07-14, the H3 item's
  evidence) — as pinned fixtures; (b) cross-check decoded defaults against the shipped `.uc`
  ScriptText `defaultproperties` text where present (an independent oracle even though it was
  rejected as the primary route).
- **Super-chain merge**: a class's defaults block is (assumed, verify) a sparse diff; the
  effective default of `DeusEx.Crate1.CollisionHeight` = walk root→leaf
  (`Object → … → Actor → … → Crate1`), overlaying each class's block, cross-package via the
  import table (same resolver pattern as `resolve_class_properties`). Missing everywhere ⇒ the
  type zero (§2.3).
- Cached per invocation (memo keyed by fqcn, like the schema cache).
- Side benefit (not wired in this change): the walker makes `ClassFlags` reachable, so
  abstractness could later come from the real bit instead of the source regex.

### 5.3 Struct member schemas

A struct is itself an export (class `Struct`) whose children are `UProperty` exports — the
existing UProperty *schema* decode applies unchanged (the member *value* encodings are §5.2's
RE item). New helper: resolve a `StructProperty`'s `type_ref` → the struct's ordered member
`Prop` list (cross-package; `Vector`/`Rotator` live under `Core.Object`). Used for: path
validation (§3), member-value validation (same partial stance as today — scalar kinds checked,
rich kinds pass on type), struct rendering (§4), member-wise struct default rendering (§5.2),
and cross-package enum resolution (§4).

### 5.4 Mockable seams

`_class_schema` stays; a sibling `_class_defaults(cls, project)` (and struct-member lookup)
becomes the second mockable seam so the whole verb surface tests offline. Integration-marked
tests hit the real v68 install.

## 6. Typed-field routing — a reusable seam (decision §8)

`Location` lives in a typed model field, not `props`; today `set`/`unset` route it specially
and `actor get` silently missed it. This change makes the routing a small registry instead of
an if-branch — decision: "clean and reusable if we have more than Location as a typed model
field":

```
_TYPED_FIELDS = {"location": TypedField(get=…, set=…, set_member=…, unset=…, struct="Vector")}
```

- `get Location` prints the field in struct form; `get Location.X` prints the axis bare.
- **Whole-value set ZERO-FILLS unmentioned axes** (review ruling R2 — Andrzej: "Location is
  NOT the only prop that can use a vector (think velocity/acceleration, where you only care
  about one axis)"): `set Location=(X=1)` sets `(1, 0, 0)`. This **supersedes**
  `_parse_location_value`'s strict all-three-axes contract (assignment semantics win over the
  anti-teleport guard; consistent with generic struct whole-value replace). The bare comma
  form still requires all three components (it's positional).
- Targeted edits: `set Location.X=5` bases on the **current field value** and changes one axis;
  `unset Location.X` zeroes that axis; `unset Location` resets to origin (as today).
- Dump-all iterates the registry first (Location always prints — the field always exists),
  then stored props.
- Adding a future typed field = one registry entry, no verb changes.

## 7. Adjacent verbs (decision round 5/6)

- **`actor get` is retired** (deleted, not aliased). `query.get_prop` goes with it; the p3
  "silent rc-0" inbox item closes as superseded. Doc-update scope: the **uedctl docs**
  (`docs/usage.md` etc.); the repo-level historical design docs (`DX/LUM/docs/superpowers/…`,
  2026-06-16) are dated archives and stay untouched.
- **`actor find --prop` adopts the new grammar AND effective-value matching** (decision:
  "Adopt now" + "Effective value", re-confirmed at review R3): `--prop KEY[.PATH]=VALUE`
  matches what `get` would print — defaults fall through, comparison canonicalized per type
  (bool case-insensitive, numeric `4`≡`4.0`, enum name≡ordinal, structs member-wise,
  strings/object-refs exact). **Mixed-level rule (R3):** plain `find` without `--prop` needs
  no schema (unchanged); a key not declared on a given actor's class = that actor doesn't
  match; a key declared on NO class present in the level → exit 2 (typo protection); a class
  whose schema cannot be built → exit 2 naming it (no-fallback). Schema resolved per distinct
  class, cached. **Acknowledged blast radius:** `find --prop LightPhase=0 | xargs actor
  delete` now matches every default-valued Light — effective-value semantics as chosen;
  `usage.md`'s "value exact" wording updates with the change.
- **`actor build --prop` adopts the same parse/validation**: tokens are the §3 grammar
  (whole-value + targeted paths composing onto the class-default base), validated against the
  class schema before emit (build already resolves the project for class validation). The
  emitted T3D stores the results in native spelling (explicit members — the §3.1/§10 H3
  consequence applies here too).
- `stash`/`prefab` boxes: `actor prop …` already rides `--target`; nothing new.

## 8. Errors (house rules)

No Python exception reaches the user. Named errors, all exit 2, each regression-tested: bad
token grammar (missing `=` on set; with the `(N)`→dot hint where applicable), **hard-rejected
key on any subcommand** (`Name`/`Brush`/mover bookkeeping), unknown key/member, index out of
bounds on any segment (incl. the negative-index spelling), non-struct path hop
(`LightBrightness.X`), comma-sugar arity/numeric errors on Vector/Rotator props, tuple-form
errors (out-of-bounds/repeated index, `KEY=()`, non-tuple whole value on a static array),
overlap conflicts (set/unset), dump-all's unknown-stored-prop error, `find --prop`'s
key-on-no-class and unbuildable-class errors, `SchemaError` (schema OR defaults unbuildable),
actor not found.

## 9. Build-gating spike (small, before or at build start)

Probe live (per §3.1): stored-struct unmentioned members and stored-sparse-array unmentioned
elements — **zero or class default** at load? Method sketch: find (via the new defaults decoder
itself, or `strings`) a class whose struct/array default has a non-zero member; author a T3D
storing a partial value; import + export in an ephemeral editor; read back. Result folds into
§3.1/§4 wording and the `get` implementation; record as an `unrealed/t3d.md` fact with
evidence.

## 10. Out of scope / follow-ups (board items)

- **Migrate `utexture.py` + `dxpkg.py` onto `upackage.py`** — follow-up chore (decision §7).
- **H3 "trunk prop equal to class default" post-verify failure** — stays a separate item
  (decision §11); this change ships the defaults capability it needs. **Interaction note
  (review):** store-explicit targeted struct edits (`set Rotation.Yaw=…` materializing
  `(Pitch=0,Yaw=8192,Roll=0)`) and full-dim `--kv` array round-trips *manufacture* exactly the
  explicit-default storage shapes that trip H3 post-verify (both this item and the p2
  "explicit zero FRotator fields" item) — expect their practical priority to rise the day this
  lands.
- The p2 "explicit zero FRotator fields fail H3" item **stays open** (Andrzej chose
  store-explicit; canonicalize-on-write was rejected for this change).
- `stash`/`prefab`-side `find` and any dump-all-with-defaults mode.

## 11. Test plan

- Grammar unit tests (paths, sugar scoping incl. `Group=a,b` verbatim, tuple + corners,
  conflicts, `(N)` rejection + hint, negative index, missing `=`).
- Verb tests through the mocked schema/defaults seams: set/unset/get on scalars, structs,
  arrays, paths, typed Location (zero-fill, member edits, member unset), dump-all (stored
  view, Location line, unknown-stored-prop error), `--kv` round-trip (property-based:
  `get --kv` fed to `set` reproduces the effective state), whole-array unset clearing all
  elements, hard-reject on get/unset.
- Walker corpus-integrity test (integration-marked): every class in every install `.u` walks
  clean; defaults decode lands at EOF. **Value-decode oracles**: the pinned `Engine.Light`
  `LightPeriod=32`/`LightPhase=0` fixtures + ScriptText `defaultproperties` cross-check on a
  class sample (§5.2).
- `find` effective-value matching incl. the default-match case and the R3 mixed-level rules;
  `build --prop` validation.
- Regression tests for every §8 error path.
- Offline suite via `bin/test`; one live end-to-end against the real v68 install (also closes
  the standing board item "run one real `actor prop` end-to-end against real v68 `.u`").

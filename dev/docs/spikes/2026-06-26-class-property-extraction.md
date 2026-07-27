# Spike: extracting a class's property set offline (for prop-name validation)

**Date:** 2026-06-26 · **Status:** RESOLVED — feasible, recommended approach below.
**Question (`board/to-spike/`):** Can uedcli obtain an actor class's full set of legal
properties offline, so `actor prop`/`actor build --prop` can ERROR on an invalid property name
instead of accepting unknown keys opaquely? We suspected we'd "have to read the packages."

**Answer: yes — two ways, and the better one needs no editor or wine at all.**

1. **Decompile (UCC):** `UED22 UCC.exe batchexport <pkg>.u class uc <out>` decompiles every class to
   `.uc` source carrying every `var` declaration (native props included), with types, `var(Category)`,
   array sizes, and `extends`. Needs wine/a container.
2. **Parse the `.u` ourselves (RECOMMENDED):** the property set is right there in the package's
   **export table** — no decompile, no wine, no container. A class's properties are simply the export
   records whose `Outer` is that class and whose type is a `*Property`. `dxpkg` already parses the
   header + name + import tables with the exact compact-index primitives; the export table is the one
   missing piece. **Proven below** (recovered Actor's 192 properties from `Engine.u` in pure Python,
   first try, cursor landing exactly at EOF). This is the section-5 finding and it changes the
   recommendation — see "Recommended approach".

The inheritance chain is walkable and crosses packages either way. No live editor is needed (and none
can do it anyway — no console verb dumps a class's property list).

---

## Method

Ran against the committed v69 substrate in the standing `dx-lum-uned` container, writing to the
container-local `/work` (ephemeral). The exact command is the one the stub pipeline already uses
(`stub.py:153`):

```
wine /opt/UED22/UCC.exe batchexport <pkg>.u class uc Z:\work\<out>
```

Decompiled `Engine.u` (88 classes), `core.u`, and `DeusEx.u` (1166 classes) and inspected the
output.

---

## Findings (all live-verified 2026-06-26)

### 1. Native/engine properties ARE in the decompiled output

`Engine.u` → `Actor.uc` (45 KB): `class Actor extends Object abstract native nativereplication;`
followed by **180 `var` lines** covering every native property a level author touches:

```
var(Movement) const vector Location;     // Actor's location; use Move to set.
var(Movement) const rotator Rotation;    // Rotation.
var          vector        PrePivot;     // Offset from box center for drawing.
var(Object)  name          Group;
var(Events)  name          Tag;          // Actor's tag name.
var(Display) texture       Texture;
var(Display) mesh          Mesh;
var const export model     Brush;        // Brush if DrawType=DT_Brush.
var(Advanced) bool         bHidden;
```

So an offline parse of the decompiled source yields the complete authored-property surface. (These
are C++-native vars; they appear as ordinary `var` lines in the decompile — no special handling, no
gaps. This was the load-bearing unknown and it is settled.)

### 2. Inheritance chain is present and walkable — across packages

Every header carries `class X extends Y`. Verified chains:

```
Mover  extends Brush     (Engine.u)
Brush  extends Actor     (Engine.u)
Light  extends Actor     (Engine.u)
PlayerStart extends NavigationPoint  (Engine.u)
NavigationPoint extends Actor        (Engine.u)
Actor  extends Object    (Engine.u → core.u)
DeusExDecoration extends Decoration  (DeusEx.u → Engine.u → … → core.u)
```

`Object` is the root (`core.u`, no `extends`). So a class's **full** property set =
union of own-`var`s along the chain, decompiling each ancestor's package. A `DeusExDecoration`
spans three packages (`DeusEx.u`, `Engine.u`, `core.u`); all decompile cleanly. `DeusEx.u`'s 1166
classes each export their own vars (`DeusExDecoration`: 46 own vars).

### 3. Parser complexity — the real implementation work

Extracting property **names** from a `var` line is not "last token before `;`". The decompiled
source has four shapes the extractor must handle (all seen in `Actor.uc`):

- **Modifiers:** `var`, `var(Category)`, `const`, `transient`, `native`, `export`, `private`, … —
  skip them.
- **Inline `enum`/`struct` typed vars where the NAME follows the body** (spans many lines):
  ```
  var(Movement) const enum EPhysics { PHYS_None, PHYS_Walking, … } Physics;
  ```
  The property name is `Physics`, after the `}`. (Bonus: the enum body lists the legal values —
  useful for future typed validation.)
- **Arrays:** `var(Display) texture MultiSkins[8];` → name `MultiSkins`, size 8. This is what makes
  the T3D `MultiSkins(N)` indexed form bounds-checkable (index < 8).
- **Multi-name, one line:** `var const transient int CollisionTag, LightingTag, OtherTag, ExtraTag,
  SpecialTag;` → five distinct properties.
- Plus trailing `// comments` to strip.

`uscript_rewrite.py` already has a brace/string/comment-aware `_scan_to_semicolon` and keeps each
full `var` line (`ParsedClass.variables`). The new work is a **name+type+array-size extractor** on
top of those lines — moderate, well-bounded, fully unit-testable offline.

### 4. No editor oracle needed (and none exists anyway)

A string-table scan of `Editor.dll` found no console verb that dumps a class's property list —
`OBJ LIST CLASS=` enumerates *objects* of a class, not its *properties*. But none is needed: the
package itself is authoritative. Cross-check by spot-comparing against `defaultproperties` blocks and
real `MAP EXPORT` T3D (which only ever emits real properties).

### 5. We can skip the decompiler entirely — parse the `.u` export table (PROVEN)

The decompile is **not** the only path, and not the best one. A compiled `.u` package stores each
class's properties as ordinary objects in its **export table**; a property's owning class is its
`Outer`. So a class's property *names* are recoverable with **no wine, no container, no UCC** — just
by reading the export table, which is a modest extension of `dxpkg` (it already reads the header +
name + import tables with the same compact-index primitives).

**Proof-of-concept** (`_scratch/uparse_poc.py`, pure Python reusing `dxpkg._read_compact_index`),
run live 2026-06-26:

- Export record layout (v69 + v68): `class:compact · super:compact · outer:int32 · name:compact ·
  flags:u32 · serialSize:compact · serialOffset:compact(if size>0)`. Parsing all `expcnt` records of
  `Engine.u` consumed **exactly to EOF** (`1239414 == file size`) — the same "verify against real
  files, not just plausible offsets" check `dxpkg` uses.
- A class's properties = export records where `Outer == <class export index>` and the record's type
  (its `Class` ref, resolved via the import/export table) ends in `Property`. For `Engine.u`'s
  `Actor` this recovered **192 properties** — `Location`, `Rotation`, `PrePivot`, `Group`, `Tag`,
  `MultiSkins`, the `Light*` lighting props, … — i.e. MORE granular than the 180 decompiled `var`
  *lines* (a multi-name line like `var int A, B, C;` is three separate export records, so no special
  comma-splitting parser is needed).
- **Inheritance is in the table:** each `UClass` export's `Super` ref gives the parent; `Actor`'s
  `Super` is an *import* resolving to `Core.Object` — so the chain crosses packages by resolving the
  import → opening that package → continuing. `Light` correctly has **0 own props** (UE1 puts the
  lighting props on `Actor`; its full set comes entirely through the chain).
- **v68 parses identically:** the v68 install `DeusEx.u` (18431 exports) also consumed exactly to EOF
  and yielded sane class/prop names. (v61 packages carry no classes — they're texture-only — so the
  version gap doesn't matter here.)

This is both **more robust and more offline than the decompile**: no fiddly UnrealScript text to
parse (no inline-enum-then-name, no multi-name commas, no comment stripping), no wine, no toolchain
dependency. Property NAMES need only the export table — **no `UProperty` body decoding at all**.

---

## Recommended approach (for the follow-on spec)

**Parse the `.u` ourselves — extend `dxpkg` with an export-table reader + a small class-property
catalog.** (The UCC decompile of §1–§3 becomes a fallback/cross-check oracle, not the primary path.)

1. **Export-table reader in `dxpkg`** (the missing piece): per export record, decode
   `(name, class_ref, super_ref, outer_ref, serial_size, serial_offset)` with the layout proven in
   §5. Pure Python, fully offline.
2. **Per-class own-property set:** exports whose `Outer` is the class and whose `class_ref` resolves
   to a `*Property` type → their `name`s (with the property type, for later typed validation).
3. **Resolve a class's FULL set:** walk `Super` to the root, resolving a cross-package `Super`
   (an import) to its package and recursing. Union the own-sets. Cache per package keyed by file
   sha256 (no toolchain id needed — there's no compile step). **Read the GAME's real `.u`, NOT the
   stub cache** (`decisions.md` 2026-06-26 14:10 UTC): stubs exist only so the UT-lineage UED22
   *editor* can load DeusEx packages (different `Engine.u`/`Core.u`) — we parse bytes ourselves, so we
   read the originals. The schema search path is therefore **its own** (the substrate's real game
   packages — for DeusEx, the v68 install code via `repo_paths.install_system_root()` + repo-authored
   `System/`/`LUM/`), NOT `packages.substrate_search_dirs` (which is editor-load-oriented: UT-lineage
   `UED22/` first, then the stub cache). The extraction spec pins the exact path.
4. **Validate + normalize:** `actor prop`/`actor build --prop` check each key against the resolved
   set (case-insensitive, FName) and **rewrite the key to the canonical `.u` spelling** before
   storing (see "Policy" below). For an indexed key `Foo(N)`, check `N < ArrayDim` once the deferred
   body decoding lands.

### Reliability — verified across every package (no sampling)

The user's bar is "make `.u` extraction reliable" (it is the SOLE mechanism — no fallback). Stress
tested it (`_scratch/uparse_reliability.py`) against **all 49** `.u` files in the committed substrate
(`uned/UED22/`) AND the v68 install (`uned/DeusExAssets/System/`):

- **49/49 parsed with the cursor landing EXACTLY at EOF** — zero mismatches, zero parse errors —
  spanning v68 and v69 (the name-table branch already in `dxpkg` handles both; the export layout is
  identical). Cursor-to-EOF is the integrity check: a layout error on any record would desync and
  miss EOF, so 49/49 is strong proof, not a spot sample.
- The **complete** UProperty subclass vocabulary across all packages is a finite **11 types**:
  `ArrayProperty, BoolProperty, ByteProperty, ClassProperty, FloatProperty, IntProperty,
  NameProperty, ObjectProperty, PointerProperty, StrProperty, StructProperty`. The recognizer is
  closed — there is no open-ended type risk.
- The reader must itself **enforce** these invariants at runtime (it's the no-fallback contract):
  cursor-must-equal-EOF after the export table, and every property's type must be one of the 11
  known classes — a violation is a hard error (a parser/format bug surfaced loudly), never a
  silent skip.

### Policy: no fallbacks — error, normalize (Andrzej, 2026-06-26)

- **Unknown property ⇒ hard ERROR** (exit 2, naming the prop). **No opaque-accept**, no silent
  pass-through to apply.
- **Schema unbuildable ⇒ also an ERROR.** If a class or any ancestor package can't be resolved or
  parsed, fail loudly (fix extraction/packages) — there is **no graceful degradation**.
- **No bypass.** No escape hatch — an unknown prop / unbuildable schema just errors. (A `--force`
  override was floated and **dropped for now**: pure error is simpler and the extraction is reliable
  enough not to need one; revisit only if a real need appears.)
- **Normalize key casing to the canonical `.u` spelling** (`lightbrightness` → `LightBrightness`).
  The engine is case-insensitive on names (spike Q8), so this is canonicalization for diff-stable,
  authoritative T3D — it **supersedes** `actor prop`'s earlier "preserve stored casing on replace".

### Scope for v1

- **Name validation + canonical-casing normalization** (needs only the export table — no body decode).
- **Defer array-bounds + typed/enum validation.** `ArrayDim` (for `Foo(N)` bounds), the value type,
  and a `ByteProperty`'s `Enum` value list live in the `UProperty` **serial body** (at the
  `serial_offset` we already parse) — a later upgrade, not a redesign. Until then `Foo(N)` validates
  the base name `Foo` only.

### Generic-UE1

Substrate-agnostic — it reads whatever packages the substrate provides; the UPackage export-table
format is the same for stock Unreal/UT. No DeusEx class names are hardcoded.

---

## Rejected / deferred alternatives

- **UCC `batchexport` decompile as the PRIMARY source** (§1–§3) — workable and already wired for the
  stub pipeline, but demoted to a fallback/oracle: it needs wine + a container + a toolchain-keyed
  cache, and parsing the decompiled UnrealScript text is *more* fiddly than the binary export table
  (inline-enum-then-name, multi-name commas, comments). Keep it only as a cross-check.
- **Live editor introspection** — no console verb exists (above), and it would reintroduce the
  crash-prone editor into a model-side path. Decompile is authoritative; use the editor only as an
  optional spot-check oracle.

---

## Verdict

Feasible, reliable, and best done **without** the decompiler. Both unknowns are settled — native
engine props are recoverable (YES) and read straight from the `.u` export table in pure Python — and
reliability is verified, not assumed: **49/49** substrate+install packages parse to exact EOF (v68 &
v69), the property-type set is a closed 11. The build effort is: (a) an export-table reader in
`dxpkg` (the only new parsing — modest, reusing existing primitives, enforcing cursor-to-EOF + the
known-type set as hard invariants), (b) a per-package class-property cache + ancestor-chain
resolution (cross-package via the import table), (c) the **no-fallback** policy — error on an unknown
prop or an unbuildable schema (no bypass), normalize key casing to the `.u` spelling. The
UCC decompile is a dev/test oracle only, not required at runtime. **Ready to triage → `board/to-spec/`**
(name validation + canonical-casing v1; array-bounds + typed/enum as flagged follow-ups needing
`UProperty` body decoding).

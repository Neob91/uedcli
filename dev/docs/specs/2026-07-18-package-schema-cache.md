# Persistent package-schema cache — decode `.u` schema + defaults once, reuse across cold runs

**Status: measured; design approved (stat key; phased v1-discovery / v2-defaults); spec-review-gate
PASSED (2 cold reviewers, findings folded); v1 ready to build on approval.**
The measurement (§9) is DONE and the build **is** justified: a warm hit is **2.4×–6× faster** than
a cold run (`class list` 3.6 s → ~0.5 s; `class show` 484 ms → ~200 ms), floored only by the ~150 ms
uncacheable interpreter-start-and-import cost. **The dominant cold cost is `load_package`'s
name/import/export TABLE PARSE (38–211 ms per big package), NOT the DEFAULTS bytecode walk** (a few
ms) — the draft's original hypothesis was refuted, and the design was reframed and its cache key
changed accordingly (see §4.3 + §9). Two decisions drove the shape: **the cache key is a
`(size, mtime_ns)` stat tuple, not a content hash** (hashing the bytes every run costs about as much
as the parse it would save — §4.3, §5 #3); and **the work is PHASED** — v1 caches only the
discovery-path primitives (§4.1a), v2 adds the defaults-value primitives (§4.1b).

This spec is **ephemeral** (see `CLAUDE.md`). On landing, fold what was built into
`architecture.md` (a new "Package schema cache" subsection + the cache-shape overview) and record
the design choices + rejected alternatives in the durable, append-only `dev/docs/decisions.md`. A
`decisions.md` entry **will be appended once this design is approved** — it is deliberately NOT
written yet (this spec is the proposal; the ledger records accepted choices). That entry must
capture **three** decisions: (1) the **stat-tuple key** (content-hash rejected — hashing ≈ parse
cost); (2) **per-package primitives, not cross-package compositions** (compositions rejected);
(3) the **phased v1-discovery / v2-defaults scope**.

## Review gate outcome

Two cold reviewers read the spec independently and BOTH flagged the same two HIGH blockers; both are
now resolved in this revision:

- **HIGH-1 — the render path needs `buf` / struct layouts were missing.** Rendering default *values*
  (for `actor prop get`/`find`) reaches into the live `Package.buf` today (via `struct_members` /
  `_resolve_type_export`), and the draft's bundle did not carry the per-Struct member layouts that a
  buf-less render needs. **Resolved by PHASING:** v1 (`class list`/`class show`) renders **no default
  values**, so it needs neither `buf`, the tables, nor struct layouts — it completely **sidesteps**
  HIGH-1. The full fix (struct-member primitive + enum/struct enumerator + imported-type chaining +
  buf-less render re-plumbing) is scoped into **v2** (§4.1b), which is the only phase that renders
  values.
- **HIGH-2 — the version regression test was illusory.** A "decode → serialize → deserialize → assert
  == fresh decode" round-trip runs the *current* decoder on both sides, so it can **never** catch a
  forgotten `SCHEMA_CACHE_VERSION` bump. **Resolved:** replaced with a **committed frozen golden
  bundle** — a serialized blob checked into the repo, asserted equal to a fresh decode of the golden
  `.u`. A decoder change then trips the test red, forcing *either* a golden refresh *or* a version
  bump (§4.5, §11).

The reviewers credited (kept unchanged): the per-package-primitives core, the stat-tuple key with
its honest staleness caveat, immutable/atomic/corrupt=miss storage, the `load_package_schema`
boundary, and the `config.schema_cache_root()` seam. Four MED and four LOW findings are folded
throughout (see §4.1, §4.3, §7, §9, §10, §11, §12).

> **Concurrent-edit note.** Several modules this touches (`uprops.py`, `upackage.py`,
> `classindex.py`, `config.py`, `dispatch.py`, plus `decisions.md`/`architecture.md`) are being
> edited by other sessions as this is written. This spec changes **no existing file**; the
> implementation sketch (§10) names the seams to rewire but the actual edits happen at build time,
> reconciled against whatever those modules look like then.

---

## 1. Terms (read first — no familiarity assumed)

- **Package / `.u` file.** A UnrealEngine-1 game ships its code and content in *package* files
  (`.u` for code+class definitions; `.dx/.utx/.uax/.umx/.unr` are the same binary container for
  other content). `Engine.u`, `Core.u`, `DeusEx.u` are multi-megabyte code packages. A package
  holds a **name table**, an **import table**, and an **export table**; every object (class,
  property, enum, default-values block) is an export whose bytes live at an offset recorded in the
  export table.
- **Class schema.** For a given class (e.g. `Engine.Light`), the list of its properties — each
  property's name, kind (`IntProperty`, `ByteProperty`, `StructProperty`, …), static-array size,
  flags, editor category, and — for enum-typed bytes — the enum's value names. uedctl decodes this
  **offline, straight from the game's own `.u` bytes** (never by running the editor). Code:
  `uprops.own_class_properties` (a class's OWN props) and `uprops.resolve_class_properties` (own +
  every ancestor's, unioned across packages by walking the Super chain).
- **Class defaults.** Every class body carries a *sparse* block of default property values (a diff
  against its superclass's defaults). Decoding it is expensive: the block sits at the **tail** of
  the UClass export body, *after* a variable-length script-bytecode blob that has no on-disk length
  field, so uedctl must **replay the bytecode token-by-token** (`uprops._walk_expr` /
  `_skip_script`) just to find where the defaults begin. Code: `uprops.class_default_tags` (raw
  per-class block) and `uprops.resolve_class_defaults` (every ancestor's block overlaid root→leaf,
  rendered to CLI text). This walk runs for every class touched — the DX install has ~1914 classes.
- **FQCN.** Fully-qualified class name, `Package.Class` (e.g. `Engine.Light`).
- **Content-addressed cache.** A cache whose key is a hash of the *content* being cached (here, a
  package file's bytes). Changed bytes ⇒ a different hash ⇒ a different key ⇒ a guaranteed miss, so
  a stale entry can never be served and **no explicit invalidation logic is needed**. uedctl
  already uses this shape for two caches under `~/.uedctl/cache/` (see §2).
- **Cold run.** Each `uedctl` command is a **fresh host-native process** (no daemon — see
  `direction.md`). It starts empty, does its work, and exits. Anything cached *in memory* dies with
  the process.

---

## 2. Recap of current state (there is NO persistent schema cache today)

Because every command is a cold process, **all schema decoding starts from zero on every
invocation**. The only caching that exists is **in-process memoization**, which lives and dies
inside the one process:

- `classindex.ClassIndex` memoizes per invocation: `_cache` (stem → loaded `Package`), `_cmaps`
  (stem → class-name→export-index map), `_ancestry` (fqcn → Super chain), `_abstract` (fqcn →
  abstract flag), `_children` (the inverse Super map). All are plain dict fields on the index
  object; the index is rebuilt from scratch each command.
- `uprops.resolve_class_properties` / `resolve_class_defaults` take a `_cache` / `_pkgs` dict that
  memoizes loaded `Package`s **within a single resolution call**, then is discarded.

So two back-to-back commands that both read `Engine.u` (e.g. `class show Engine.Light` then
`actor prop get someactor SomeKey`) each independently: read the multi-MB file, **parse its
name/import/export tables** (the dominant cost — 38 ms for `Engine.u`, 211 ms for `DeusEx.u`),
decode property bodies, and replay the class bytecode. Nothing survives to the next process.

Meanwhile, **two persistent, content-addressed caches already exist** under the per-user cache home
(`config.user_cache_home()` → `~/.uedctl/cache/`, or `$UEDCTL_HOME/cache`):

- `cache/textures/` (`config.texture_images_root`) — decoded texture PNGs.
- `cache/stubs/` (`config.stub_cache_root`) — built v69 stub packages + a per-package JSON sidecar
  (`stub_cache.py`), keyed so a changed input/dep/toolchain invalidates dependents. Its patterns —
  `sha256_file`, `_atomic_write` (tmp-file + `os.replace`), one sidecar-per-item written LAST,
  corrupt-entry-is-a-miss — are the template this spec follows.

**This feature adds a third sibling: `cache/schema/`.** Same derivable, never-committed, lock-free-
reader, atomic-rename-writer philosophy — but **keyed by a per-package `(size, mtime_ns)` stat
tuple, not by a content hash** (§4.3 explains why: for these ship-once game packages, re-hashing on
every run would cost about as much as the parse the cache exists to remove).

---

## 3. Goal and the one load-bearing idea

Make repeated cold `uedctl` invocations **skip re-parsing and re-decoding the same `.u` packages**
by persisting each package's decoded schema primitives to disk, keyed by a per-package
`(size, mtime_ns)` stat tuple (§4.3).

The one idea everything else follows from:

> **Cache the PER-PACKAGE decode primitives. Do NOT cache cross-package compositions.**

A *primitive* is something derivable from a **single** package's bytes alone. A *composition*
(a class's full ancestor-unioned property list, its effective rendered defaults, the global class
tree) spans **several** packages. We persist the primitives and **recompute the compositions
in-process** from them — the composition is cheap dict-merging once the per-package decode is
already done.

**The work is delivered in two phases** (review-gate decision):

- **v1 — the BUILD TARGET — a discovery-path cache.** Caches only the primitives `class list` /
  `class show` need (§4.1a). It captures the two biggest measured wins (`class list` 6×, `class
  show` 2.4×) and, by rendering **no default values**, needs neither `buf` nor struct layouts — so
  it sidesteps HIGH-1 entirely and keeps the bundle small.
- **v2 — a FOLLOW-UP, specced here as the plan, NOT built now — a defaults-value cache.** Adds the
  primitives `actor prop get` / `actor find --prop` need to render default *values* without `buf`
  (§4.1b). This is where HIGH-1's full fix lands.

Why the per-package split is the whole design: see §4.

---

## 4. Design

### 4.1a What v1 caches — the discovery-path primitive bundle (BUILD TARGET)

For each package, keyed by that package's `(size, mtime_ns)` stat tuple (§4.3), v1 persists a small
serializable bundle (call it `PackageSchema`) containing exactly the artifacts `class list` /
`class show` need — each a pure function of *that one package's bytes*:

1. **Class list** — every UClass name in the package (`uprops.iter_classes`).
2. **Class map (`cmap`)** — casefold(class name) → 1-based export index
   (`uprops.class_index_map`).
3. **Super references** — per class, its **already-qualified direct-super FQCN string** (or "root"),
   so ancestry walks need no re-decode. Produced once via `uprops.super_fqcn_by_index` (which already
   resolves imported supers to `Package.Class`) and stored as the FQCN string — the cross-package
   ancestry composition then just chases strings. Each package contributes only its own classes'
   one-hop super links.
4. **Abstract flags** — per class, `True`/`False`/`unknown` (`uprops.class_is_abstract`, which
   parses the shipped ScriptText `.uc` source — itself not free).
5. **Own-property schema** — per class, its own (not inherited) `Prop` list
   (`uprops.own_class_properties`): name, kind, array_dim, flags, category, type_ref, owner, and
   **LOCAL enum value-names already baked into each `Prop`** (`Prop.enum_value_names`, filled eagerly
   by `own_class_properties`). This is all `class show` renders — it lists property *schema*, never
   default *values*.

**v1 deliberately caches NONE of: the name/import/export tables, the raw DEFAULTS blocks, or the
per-Struct member layouts.** Discovery never renders a default *value*, so it never needs `buf`,
the tables, or struct layouts once items 1–5 are cached — which is exactly why **v1 sidesteps HIGH-1**
(the render-needs-`buf` blocker) and keeps the bundle small (no tables ⇒ the reviewers' JSON-bloat
worry is moot — see §9's JSON measurement task).

**One honest v1 gap (not a regression).** `own_class_properties` leaves an **imported** (cross-package)
enum's value-names **empty** today — only a *local* enum's names are baked into the `Prop`. That is
**unchanged existing behavior** (v1 caches exactly what `own_class_properties` already produces), not
something v1 breaks. Filling imported enum names is a v2 concern (it needs the foreign package's enum
table — §4.1b).

**Why cache items 1–5 even though they're cheap to *produce*.** The measurement (§9) showed these
decode steps are individually a few ms. They are cached not because producing them is slow, but
because **a warm hit must avoid `load_package` (the slow table parse, 38–211 ms) AND must never touch
the raw bytes `buf` at all** — and without `buf` we cannot re-derive them on a hit. The payoff is
skipping the *parse*, not the decode.

What v1 still **recomputes in-process** from these (exactly as today, just sourcing per-package inputs
from the cache instead of a fresh decode):

- **Ancestry** (`ClassIndex.ancestry`) — chase the cached super-reference strings across packages.
- **The class tree** (`ClassIndex.children_map`) — invert the cached super references.
- **Resolved property union** (`uprops.resolve_class_properties`) — merge cached own-prop lists up
  the ancestry, child-overrides-parent. (`class show` uses this for its schema listing; it renders
  no values.)

### 4.1b What v2 adds — the defaults-value primitives (FOLLOW-UP; specced, not built now)

`actor prop get` / `actor find --prop` / `actor build --prop` render class default **values**, which
the render path today extracts from the live `Package.buf` — this is HIGH-1. v2 makes that render
buf-less by adding these to the bundle and re-plumbing the renderers:

6. **Raw DEFAULTS blocks** — per class, its defaults block (`uprops.class_default_tags` →
   `list[PropertyTag]`: name, ptype, array_index, struct-name, and the **raw value byte span**).
7. **Local enum tables** — the enum value-name lists (`uprops.enum_values`) for rendering enum-typed
   defaults by name (the *local* ones; imported ones come via chaining, below).
8. **Per-Struct member schemas** — the **ordered** member `Prop` list of each `Struct` export
   (`uprops.struct_members` — the `Children` linked-list walk, declaration order, super-struct
   members first). **This is the layout HIGH-1 said was missing**; without it a struct-typed default
   value cannot be decoded, and today it is read live from `buf`.
9. **The compact name/import/export tables** — needed to render **object-reference** default values
   (`Class'Package.Name'`) offline. (Object refs need only the name+import tables, NOT `buf` — a
   lighter need than struct values; see the §9 option to *pre-render object refs to text at decode
   time*, which would drop even the tables.)

v2 also needs machinery that does not exist yet:

- **A whole-package ENUM/STRUCT enumerator.** There is no `iter_structs` / `iter_enums` today
  (only `iter_classes`). v2 must add a producer that walks the export table for exports whose class
  is `Struct` / `Enum` and decodes their member/value tables into the bundle.
- **Imported-type resolution by CHAINING.** When a class's default references an enum/struct defined
  in *another* package (e.g. `Core`'s `Vector`), v2 resolves it by calling
  `load_package_schema` on that foreign package and reading the type from **its** cached bundle —
  not by re-parsing it live. This is the buf-less replacement for today's `_resolve_type_export` /
  `_pkg_for_owner` live-`Package` walks.
- **Buf-less render re-plumbing.** `resolve_class_defaults`, `render_default_tag`, `struct_members`,
  `_resolve_type_export`, and the object-ref renderer all currently take a live `Package`; v2
  reworks them to consume the cached primitives (raw tags + struct-member schemas + enum tables +
  tables) instead. **This is the load-bearing v2 work and the full resolution of HIGH-1.**

v2's cross-package compositions stay in-process, same as v1: **effective rendered defaults**
(`resolve_class_defaults`) overlays each ancestor's cached raw DEFAULTS block root→leaf and renders
to CLI text using the cached enum tables / struct-member schemas / tables.

### 4.2 Why per-package, not cross-package (the core rationale)

- **Strong reuse.** `Engine.u` at the shared base-install path has one stat tuple across every
  project and command that references it (the games config points every project at the same base
  dirs — the normal case). Parse+decode it **once** (until its size/mtime change) and every future
  `class show`, `actor prop get`, `actor find --prop`, `class list` reuses it — the overwhelmingly
  hot packages (`Core.u`, `Engine.u`) are amortized across the tool's lifetime. *(Because the
  realpath is in the key, two distinct on-disk COPIES of byte-identical `Engine.u` at different real
  paths get separate entries — a content hash would dedup them; symlinks to one file do NOT
  duplicate, since realpath collapses them (§4.3). That cross-path dedup is knowingly traded away for
  the ~1.4 s-per-run hashing cost it would take to recover; distinct copies of the base game are not
  a real workflow.)*
- **A hash-tuple key would give poor reuse.** Keying a *composition* (a resolved union) requires a
  key over **every** package that fed it — a tuple of hashes. Then:
  - Any one package changing invalidates the whole composed entry, even for classes it didn't
    affect.
  - Each distinct class produces a distinct entry, and the shared upper chain
    (`…→Engine.Actor→Core.Object`, common to *every* Actor subclass) is re-decoded and re-stored
    per leaf class — combinatorial blow-up, the opposite of reuse.
- **Composition is cheap once primitives are cached.** The union/ancestry/render steps are dict
  merges and byte-span rendering — microseconds. The cost being avoided is the per-package
  `load_package` table parse (38–211 ms), which a warm hit skips entirely; there is no benefit to
  persisting the compositions, and real cost (invalidation surface, storage) to doing so.
- **Change detection is per-package and cheap.** The key is a per-package `(size, mtime_ns)` stat
  tuple (§4.3); a changed package produces a different tuple ⇒ a different key ⇒ a miss. No
  dependency graph, no "which compositions did this package feed" — a `class list`-scale run stats
  47 packages in ~0.25 ms total (`os.stat` ≈ 5 µs each) instead of re-hashing 342 MB (~1.4 s).

### 4.3 The cache key — a `(size, mtime_ns)` stat tuple (NOT a content hash)

**The key is a stat tuple: `(SCHEMA_CACHE_VERSION, realpath, size, st_mtime_ns)`.** Andrzej's
decision, driven by the measurement: an `os.stat` costs ~5 µs, while sha256-hashing a package's
bytes costs about as much as the parse it is meant to save (21 ms for `DeusEx.u`, 189 ms for
`TNM.u`, ~1.4 s to hash the whole 342 MB `class list` path). A content-hash key would have to read
and hash every file on **every** cold run — reintroducing ~half the very cost we're removing. Since
these are **ship-once game packages** that essentially never change under a project, a stat tuple is
a safe, effectively-free change detector.

The path component is **`os.path.realpath`** (symlinks resolved), not a bare `abspath`, so two paths
that symlink to the same file share one entry instead of duplicating it — deliberate, and consistent
with the realpath-normalized mount matching the game-preview path already uses (`architecture.md`).

Mechanism:

- On a run: `os.stat` the package (cheap). Form the little key string
  `f"{SCHEMA_CACHE_VERSION}\0{realpath}\0{size}\0{st_mtime_ns}"` and take a **short hash of that
  ~100-byte string** (sha1 of the tuple — this is hashing ~100 bytes, NOT the multi-MB file) as the
  on-disk filename: `cache/schema/v<N>/<tuple-sha1>.json`.
- Present ⇒ **hit** (deserialize the bundle, no `load_package`, no `buf`). Absent ⇒ **miss**
  (`load_package` + decode + atomic write of the bundle under that name).

**Writer-spelling note (LOW).** The cached super-reference / class FQCN strings embed `pkg.name`,
which comes from the package's file stem, and every read of them is casefolded (FName semantics, as
today in `ClassIndex`). So if two runs spell a stem differently by case, the first writer's spelling
is stored but reads are case-insensitive anyway — harmless. Normalize-on-read (casefold at load) if
it's cheap, but nothing depends on it.

**Staleness risk, and why it's acceptable.** The key trusts `(size, mtime_ns)` as a proxy for "same
bytes." It can be wrong **only** if a package's content changes while both its size *and* its
nanosecond mtime are preserved — e.g. a deliberate mtime spoof, or restoring an older file with
timestamps preserved (`cp -p`, `tar -x`, `rsync --times`) *on top of* a same-size different file.
Real edits never do this: any tool that rewrites a `.u` advances mtime, and content changes almost
always change size. This is now a property of **the key itself** (not of a shortcut over a
content-hash ground truth), so a genuine spoof serves a stale entry. Mitigations:

- **Nanosecond** mtime (`st_mtime_ns`, not whole-second `st_mtime`) makes accidental collisions
  astronomically unlikely.
- An **escape hatch** — an env/flag (e.g. `UEDCTL_SCHEMA_CACHE=off`) that bypasses the cache and
  always cold-decodes, for the paranoid or for CI determinism.
- Deleting the whole `cache/schema/` dir always recovers a fully-correct cold decode; the cache is
  pure derivable throwaway.

This matches the existing caches' posture in spirit — `texture_catalog` and `stub_cache` both
change-detect against stored metadata rather than re-hashing on the hot path — but goes further:
because game packages are immutable-in-practice, the stat tuple is the *key*, not merely a
re-hashing shortcut.

### 4.4 Storage, serialization, immutability

- **Path:** `~/.uedctl/cache/schema/v<N>/<tuple-sha1>.json` (or `.bin` — see serialization), where
  `<tuple-sha1>` is the short hash of the `(SCHEMA_CACHE_VERSION, realpath, size, st_mtime_ns)` key
  string (§4.3) — NOT a hash of the file bytes. Via a new `config.schema_cache_root()` =
  `user_cache_home() / "schema"`, sibling to `stub_cache_root` / `texture_images_root`. `v<N>` is the
  decoder version (§4.5).
- **Serialization: JSON is the default choice, but the format is decided by a measurement taken
  BEFORE the serializer is committed** (§9, MED finding). Justification for defaulting to JSON:
  - **Portability + the release binary.** uedctl ships as a Nuitka-compiled binary. `pickle` /
    `marshal` are Python-version- and layout-fragile across a rebuilt binary and a plain-file cache
    that outlives one build; JSON is stable, language-agnostic, and human-inspectable (debugging a
    bad entry by eye matters for an undocumented-format tool).
  - **Safety.** `pickle` executes arbitrary code on load; even a user-owned cache dir is a needless
    attack surface. JSON can't.
  - **Cost — measure first (the MED finding).** v1's bundle is **small** (no tables, no defaults
    blocks — §4.1a), so JSON parse should be well under the 38–211 ms parse it replaces. But this is
    NOT yet measured, and swapping the format later would burn a `SCHEMA_CACHE_VERSION`. So the
    **first v1 build task is a ~10-line spike timing `json.loads` on the ACTUAL v1 bundle shape**
    (§9); if it approaches the pickle number, pick a compact stdlib binary format up front. The
    format is locked before any entry is written.
- **Immutability ⇒ no eviction-correctness concern.** Each entry is written once and never mutated
  (a size/mtime change is a *new* file at a *new* key). Writers use the `stub_cache._atomic_write`
  pattern (tmp file in the same dir + `os.replace`), so a lock-free reader never sees a torn entry
  and concurrent writers of the same new entry are last-writer-wins-safe. A corrupt/unparseable
  entry is treated as a **miss** (re-decode), never an error — exactly `stub_cache._load_sidecar`'s
  rule.
- **`uedctl cache clear` (v1) + GC (deferred).** v1 ships a tiny **`uedctl cache clear`** verb that
  deletes `cache/schema/` — useful for the escape-hatch/paranoid case and to reclaim `v<N-1>/` dirs
  orphaned by a version bump. Automatic **LRU / size-capped GC** stays a deferred follow-up (an
  atime/size sweep), because immutability means there is no *correctness* pressure to evict — only a
  footprint one, and the footprint is small: the v1 discovery bundle is a few tens of KB per package
  (no tables/defaults), so ~47 packages × a handful of live `v<N>/` versions is on the order of a few
  MB total. (v2's defaults bundles are larger — its footprint feeds the GC-priority call.)

### 4.5 The schema/format VERSION (prominent — do not skip)

**The stat tuple detects *package* changes, not uedctl's *decode-logic* changes. Both must key the
entry.** If we improve or fix a decoder (a new property kind, a corrected UClass-tail layout, an
extra field on `Prop`, a different rendering), the *same package* (same size/mtime) must now yield a
*different* cached bundle — but the stat tuple is unchanged. Without a version dimension, a
post-upgrade uedctl would happily read a stale, wrongly-shaped entry an older build wrote.

So `SCHEMA_CACHE_VERSION` is folded into the key on **both** axes: it is part of the hashed key
string (§4.3) **and** realized as the `v<N>/` path segment (so old versions live in separate dirs,
GC-able as a unit). `SCHEMA_CACHE_VERSION` is a single integer constant in the cache module,
**bumped by hand whenever any of these change**: the `PackageSchema` bundle shape/fields, any
decoder in `uprops`/`upackage` that feeds it, the `Prop`/`PropertyTag` layout, the rendering, or
the serialization format. A bump makes every old entry simply unreachable (new dir); old `v<N-1>/`
dirs become dead files (`cache clear` / GC reclaims them).

**The version is hand-bumped, so a test must guard the human step — and the obvious test doesn't
(HIGH-2).** A "decode → serialize → deserialize → assert == fresh decode" round-trip runs the
*current* decoder on both sides, so it passes no matter how the decoder changed and can NEVER catch a
forgotten bump. The real guard is a **committed frozen golden bundle**: a serialized bundle blob for
a small golden `.u`, checked into the repo, asserted **byte-equal** to a fresh decode-and-serialize
of that golden `.u`. Any decoder/format change makes the fresh output differ from the committed blob
and trips the test **red**, forcing the author to *either* refresh the golden blob *or* bump
`SCHEMA_CACHE_VERSION` — a deliberate, reviewed choice instead of a silent drift (see §11).

### 4.6 Layering — one boundary, extended per phase

Both phases wrap the same seam: a new **`schema_cache.load_package_schema(path) → PackageSchema`**
above today's raw **`uprops.load_package(path)`** (which returns a `Package` incl. `buf`).
`load_package_schema` does `load_package` + derive-the-bundle on a miss and returns the deserialized
bundle on a hit. Consumers move from "hold a `Package`, call decode helpers on it" to "hold a
`PackageSchema`, read the already-decoded fields."

**v1 wiring — class discovery.** `classindex.ClassIndex` and `class show`'s schema listing source
their per-package inputs (class list, cmap, super refs, abstract flags, own-prop schema) from
`load_package_schema`. The v1 **producers** the cache calls on a miss are the existing pure helpers
`iter_classes`, `class_index_map`, `super_fqcn_by_index`, `class_is_abstract`, `own_class_properties`
— unchanged, still unit-tested as-is. The v1 **consumers** rewired to the cache are
`ClassIndex.ancestry` / `children_map` / `_cmap` / `is_abstract` / `_all_fqcns`, and
`resolve_class_properties` (schema union, no values).

**v2 wiring — defaults values.** The bundle grows the §4.1b fields (raw DEFAULTS blocks, local enum
tables, per-Struct member schemas, the compact tables), fed by producers `class_default_tags`,
`enum_values`, `struct_members`, and the **new** enum/struct enumerator. The render **consumers**
(`resolve_class_defaults`, `render_default_tag`, `struct_members`, `_resolve_type_export`, the
object-ref renderer) are re-plumbed to read cached primitives — resolving imported types by chaining
`load_package_schema` on the foreign package — instead of a live `Package`/`buf`. This is HIGH-1's
full fix.

---

## 5. Rejected alternatives

1. **Cache the cross-package resolved union, keyed by a hash-tuple.** Rejected: poor reuse (a
   distinct entry per class; the shared `…→Engine.Actor→Core.Object` upper chain re-decoded and
   re-stored per leaf), whole-composition invalidation on any contributing package's change, and a
   complex multi-package key. Per-package primitives + in-process composition give perfect reuse and
   free invalidation (§4.2).
2. **Cache the fully-resolved per-class effective defaults / property list.** Same failure mode as
   #1 (it *is* a cross-package composition), and additionally it bakes the rendering + version
   coupling into every class entry. The render is cheap; only the *decode* is worth persisting.
3. **Content-hash (sha256-of-bytes) key.** *This is the REJECTED one* — reversing the draft.
   Content addressing would be correct by construction (a stale entry could never be served), but
   the measurement killed it: hashing the bytes must happen on **every** cold run, and it costs
   about as much as the parse it saves (21 ms `DeusEx.u`, 189 ms `TNM.u`, ~1.4 s for the whole
   `class list` path) — reintroducing ~half the cost we're removing. For **ship-once game packages**
   that don't change under a project, a `(size, mtime_ns)` **stat tuple** (§4.3) is the accepted key:
   ~5 µs per package, a safe change detector, at the cost of the narrow spoof-staleness caveat
   (§4.3). We accept that caveat to keep the win; the escape hatch + `cache/schema/` deletion cover
   the paranoid case.
4. **In-memory-only memoization across a batch of commands.** This is what exists today, and it's
   the exact thing that fails: uedctl is per-command cold, so the memo dies at process exit and the
   *next* command pays full cost again. A persistent, on-disk cache is the whole point. (If a future
   batch/REPL mode appears, in-process memo still complements this — it's not either/or.)
5. **A SQLite index instead of plain per-key files.** Rejected: many `uedctl` processes run in
   parallel (per-command, parallel-safe by construction — `direction.md`); a single SQLite file is a
   write-lock contention point and a schema-migration burden, and adds a dependency, for **no**
   correctness or performance advantage over immutable per-key files (which are naturally lock-free
   for readers, atomic-rename for writers, and identical in philosophy to the existing
   `cache/{textures,stubs}`). The stat-tuple filename already gives O(1) lookup; we don't need a DB
   index.

---

## 6. Non-goals

- **Not a daemon / not a persistent process.** uedctl stays per-command host-native; this caches
  *decoded artifacts on disk*, it does not keep a process warm.
- **Not caching cross-package compositions** (ancestry, resolved property union, resolved rendered
  defaults, the class tree) — recomputed in-process (§4.1a/§4.1b).
- **Not caching the raw multi-MB package bytes (`Package.buf`).** The point is to store *compact
  derived primitives*, not the source bytes.
- **Not a texture-pixel or import-closure cache** — those are separate concerns (`cache/textures`,
  `dxpkg`), untouched.
- **Not an AUTOMATIC eviction/GC policy in v1** — immutable entries have no correctness pressure; v1
  ships a manual `uedctl cache clear`, and automatic LRU/size-cap GC is a flagged follow-up (§4.4).
- **Not changing any decode semantics or the no-fallback contract.** Same bytes in ⇒ same primitives
  out; a corrupt package still raises `SchemaError` on a miss-path decode exactly as today (and a
  corrupt *cache entry* is a miss, not an error).
- **Not a cross-machine or networked/shared cache** — per-user, local, derivable.
- **Not the v69 stub schema** — this is the *game's own* `.u` schema-and-defaults decode; stub
  building has its own cache (`stub_cache.py`).

---

## 7. Safety, concurrency, and failure modes

- **Parallel invocations** each read/derive/write the same entries. Immutable per-key files +
  atomic-rename writes ⇒ readers never see torn data; two processes decoding the same new package
  race harmlessly (last rename wins, both wrote identical bytes).
- **Corrupt or version-mismatched entry ⇒ miss ⇒ re-decode**, never an abort (mirrors
  `stub_cache._load_sidecar`). A schema entry that fails to deserialize, or lives under a stale
  `v<N>/`, is simply ignored.
- **No project / empty package path** behaves exactly as today (the cache is transparent; a missing
  game `.u` still yields the honest `SchemaError`, exit 2 — no fallback).
- **Escape hatch — exact semantics:** the env var **`UEDCTL_SCHEMA_CACHE=off`** disables the cache
  entirely — never read, never write, always cold-decode. **Unset (the default) or any other value
  = on.** Used for debugging, CI determinism, and the spoof-staleness paranoid case.
- **Test harness runs with the cache OFF by default (MED finding).** The offline suite exports
  `UEDCTL_SCHEMA_CACHE=off` by default, so a stale dev-written entry can NOT poison unrelated
  tests — important right now, while the `uprops`/`upackage` decoder is being refactored by a
  concurrent session and any cached bundle could be shaped by an interim decoder. Only the dedicated
  cache tests opt back in (§11).

---

## 8. What the user sees

Nothing, functionally — this is a pure performance feature. Same command surface, same outputs, same
errors (v1 touches only `class list`/`class show`; the `actor prop`/`find` defaults path is untouched
until v2). The only observable difference is **latency**: the first command that reads a given
package pays the parse+decode; subsequent cold commands that see the same package (same stat tuple)
are fast. A `~/.uedctl/cache/schema/` directory appears (derivable, safe to delete anytime, or
`uedctl cache clear`).

---

## 9. Measurement results (DONE) + the one remaining open question

The gating measurement is **complete** (host-native, median of 5–7 runs). It **justifies the build**
and **refuted the original hypothesis** (DEFAULTS decode was NOT the cost). Results:

- **Uncacheable floor:** ~150 ms interpreter-start + import (`uedctl --help`). Every warm number
  below is bounded from beneath by this.
- **End-to-end warm win (projected):**
  - `class list` (tree) **3.6 s cold → ~0.5 s warm (~6×)** — the biggest win. `--flat --all` 3.2 s.
  - `class show DeusEx.ScriptedPawn` **484 ms cold → ~200 ms warm (2.4×)**. `--all` 541 ms.
  - `actor prop get` (3 defaults) 363 ms cold.
- **In-process breakdown for `resolve_class_properties(ScriptedPawn)` — the refutation:** parsing
  the 3 chain packages = **215 ms and DOMINATES** (`DeusEx.u` alone 211 ms); own-property schema
  decode = 12 ms; `class_is_abstract`/ScriptText = 2 ms; **the DEFAULTS bytecode walk is only a few
  ms.** ⇒ The payoff is skipping `load_package`'s **table parse**, not the decode.
- **`load_package` (tables, no body decode):** `Core.u` 4 ms / `Engine.u` 38 ms / `DeusEx.u` 211 ms
  / `TNM.u` 170 ms; the whole 342 MB / 47-package path parses in **~2.3 s**.
- **Hashing cost (why the key is a stat tuple, not a content hash):** sha256-over-bytes = `Engine.u`
  5 ms, `DeusEx.u` 21 ms, `TNM.u` 189 ms, whole path **~1.4 s** — i.e. ≈ the parse it would save.
  `os.stat` = **~5 µs.** (See §4.3 / §5 #3.)
- **Warm read cost:** deserializing a cached decoded-schema **pickle** blob (`DeusEx.u`, 0.30 MB) =
  **13 ms**; a resolved-props slice (40 KB) = 1.8 ms — comfortably under the parse it replaces.

**The FIRST v1 build task (gates the serializer choice, does not block the go/no-go):**

- **Time `json.loads` on the ACTUAL v1 bundle shape (MED finding) — a ~10-line spike, done BEFORE the
  serializer is committed.** §4.4 defaults to JSON for portability/safety, and v1's bundle is small
  (no tables, no defaults blocks), so JSON should be well under the 38–211 ms parse it replaces — but
  it has NOT been timed. **If JSON parse approaches the ~13 ms pickle number (or the parse it
  replaces), pick a compact stdlib binary format up front.** Deciding this first avoids burning a
  `SCHEMA_CACHE_VERSION` on a later format swap.

**Deferred to v2 / verified during the build (not go/no-go):**

- **Object-ref bundle-shape option (v2):** does rendering object-reference defaults truly need the
  value-package name/import tables (§4.1b item 9), or can object-ref rendering be **pre-resolved to
  text at decode time** and stored, dropping the tables from the v2 bundle entirely? Pre-resolving
  would shrink the v2 bundle and remove a whole primitive — resolve it when v2 is designed.
- **Confirm parallel-write safety** empirically during the v1 build (N processes decoding the same
  cold package at once) — expected safe by atomic rename, but verify no torn read.

---

## 10. Implementation sketch (which modules change)

### v1 (build now)

**New module — `uedctl/schema_cache.py`:**

- `SCHEMA_CACHE_VERSION: int` — the decoder-version constant (§4.5).
- `@dataclass PackageSchema` — the serializable **v1 discovery** bundle (§4.1a: class list, cmap,
  super-ref FQCN strings, abstract flags, own-prop schema with local enums), with `to_bytes()` /
  `from_bytes()` (JSON+base64, or the compact binary the §9 spike selects). **No tables, no defaults,
  no struct layouts.**
- `cache_key(path) -> str` — `os.stat` the file, build the
  `(SCHEMA_CACHE_VERSION, realpath, size, st_mtime_ns)` key string, return its short sha1 (§4.3).
  Does **not** read or hash the file bytes.
- `load_package_schema(path) -> PackageSchema` — the wrapped boundary: honor `UEDCTL_SCHEMA_CACHE=off`
  → always decode; else in-process memo → on-disk `v<N>/<cache_key>` → on miss,
  `_decode(uprops.load_package(path))` + atomic write.
- `_decode(pkg) -> PackageSchema` — calls the existing v1 `uprops` producers (`iter_classes`,
  `class_index_map`, `super_fqcn_by_index` over the class map, `class_is_abstract`,
  `own_class_properties`).
- `clear()` — delete `schema_cache_root()`; backs the `cache clear` verb.
- Reuse `stub_cache._atomic_write`; consider factoring a shared `cache_util` if it's cleaner.

**`uedctl/config.py`** (edit at build time — being concurrently edited now): add
`schema_cache_root(*, create=False) -> Path` = `user_cache_home() / "schema"`, sibling to
`stub_cache_root` / `texture_images_root`.

**`uedctl/classindex.py`:** `_package`/`_cmap`/`ancestry`/`is_abstract`/`_all_fqcns`/`children_map`
source their per-package inputs from `load_package_schema` instead of re-deriving from a live
`Package`. The in-process memo fields stay (they still help within one command); they're now
populated from the cached bundle.

**`uedctl/uprops.py`:** `resolve_class_properties` (schema union only — no values) sources cached
own-props via `load_package_schema`. The pure producers stay as the miss-path decoders. (Coordinate
with the concurrent `uprops`/`upackage` refactor.)

**CLI — a new `cache` group with `uedctl cache clear`** (deletes `cache/schema/`); each command/arg
gets a real `help=` per `CLAUDE.md`.

### v2 (follow-up — specced, not built now)

- Grow `PackageSchema` with the §4.1b fields (raw DEFAULTS blocks, local enum tables, per-Struct
  member schemas, compact tables) — a `SCHEMA_CACHE_VERSION` bump.
- Add the **enum/struct enumerator** producer (walk exports whose class is `Struct`/`Enum`).
- Re-plumb the render consumers (`resolve_class_defaults`, `render_default_tag`, `struct_members`,
  `_resolve_type_export`, object-ref render) to read cached primitives + chain `load_package_schema`
  for imported types, eliminating the live-`Package`/`buf` reads (HIGH-1's full fix).

**Tests — `tests/`:** see §11. **Docs — on build:** see §12.

---

## 11. Tests

**The harness runs with the cache OFF by default** (`UEDCTL_SCHEMA_CACHE=off` exported for the suite —
§7, MED finding), so no stale dev-written entry can poison unrelated tests during the concurrent
decoder refactor. Only the cache tests below **opt back in** (set the env / point at a temp cache
root via `$UEDCTL_HOME`).

v1 tests:

- **Frozen-golden-bundle version guard (HIGH-2 — the real guard for the hand-bumped version):** a
  serialized bundle blob for a small golden `.u`, **committed to the repo**, asserted byte-equal to a
  fresh decode-and-serialize of that golden `.u`. A decoder/format change makes them differ and trips
  the test **red**, forcing a golden refresh OR a `SCHEMA_CACHE_VERSION` bump — a reviewed choice, not
  silent drift. (This replaces the illusory decode→serialize→deserialize round-trip, which runs the
  current decoder on both sides and can never catch a forgotten bump.)
- **Same-stat ⇒ hit:** unchanged `(size, mtime_ns)` reuses the entry with **no** `load_package` call
  (assert the parse is skipped — e.g. patch/spy `load_package`).
- **Stat-change ⇒ miss:** rewrite the file (new size and/or `st_mtime_ns`), assert a new key/new
  entry, no stale serve. Also cover the accepted staleness caveat: an `os.utime`-restored
  `(size, mtime_ns)` over changed bytes DOES serve the old entry (documents the known limitation),
  and `UEDCTL_SCHEMA_CACHE=off` bypasses it.
- **Version-bump ⇒ miss:** bump `SCHEMA_CACHE_VERSION`, assert old entries unreachable (both the
  hashed key string and the `v<N>/` dir change).
- **realpath keying:** two symlinked paths to one file share a single entry.
- **Corrupt entry ⇒ miss, not error;** **parallel writers** produce a valid entry (no torn read).
- **`cache clear`** removes `cache/schema/` and exits 0 (and is a no-op when absent).
- **v1 equivalence (integration):** every `class list` / `class show` output is byte-identical with
  the cache warm vs cold, across the DX corpus. *(`actor prop get` / `find` equivalence is a **v2**
  test — v1 doesn't touch the defaults path.)*
- Keep these in an engine-facts-adjacent module and back-reference this spec (per `CLAUDE.md` "pin the
  finding").

v2 tests (when built): the §4.1b render primitives decode buf-lessly; imported enum/struct chaining;
`actor prop get`/`find` warm-vs-cold equivalence over the corpus.

Run via `bin/test` (host-native venv). Corpus/equivalence checks that need the real DX `.u` files are
`-m integration`. The JSON-vs-binary format spike (§9) is a one-off timing script under
`dev/docs/spikes/`, not a suite test.

## 12. Docs to update on build

- **`architecture.md`** — a new "Package schema cache" subsection under the class-schema section,
  and add `schema` to the `~/.uedctl/cache/{textures,stubs}` cache-shape overview; document the
  `cache clear` verb.
- **`decisions.md`** — append the timestamped entry once approved, capturing the **three** decisions
  (stat-tuple key / content-hash rejected; per-package primitives / compositions rejected; phased
  v1-discovery / v2-defaults scope) + the §5 rejected alternatives. *(Not written by this spec.)*
- **`direction.md`** — reconcile **the one line** that reads `cache/{textures,stubs}` — in the
  "Projects, substrates, and the global CLI" section — to include `schema`. *(The container-isolation
  section does NOT mention the derivable cache, so it needs no change — LOW review fix to the draft's
  claim of "two lines".)*
- **`unrealed/class-schema.md`** — no new engine facts (decode unchanged), but add a note that any
  change to the documented UClass-tail / property layout **must bump `SCHEMA_CACHE_VERSION`** (and
  refresh the frozen golden bundle — §11).
- **`board/`** — advance this item; record the **v2 defaults-cache** follow-up as its own item, plus
  TODOs: (a) compact-binary serialization *iff* the §9 spike shows JSON decode is a bottleneck;
  (b) automatic LRU/size-capped GC (beyond the manual `cache clear`); (c) v2's pre-render-object-refs
  option to drop the cached tables (§9).
- No change to `CLAUDE.md` test command.

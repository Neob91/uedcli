# Spec — one Rust core for UE1 package-header reading

## Goal

Replace every hand-rolled copy of UE1 compact-index/name-table/header-table decoding with one Rust
implementation, exposed to Python via `uedcli_native`. Fixes two real problems in one pass: the
61M-call pure-Python hot loop (`port-ue1-package-primitive-decode-to-rust-61m`) and the missing
per-package cache (`upackage-load-package-has-zero-caching-3404`) — plus closes two open
duplication items that were never acted on (`migrate-utexture-py-dxpkg-py-onto-the-unified`,
`proceduraltex-py-correctness-and-duplication`). No CLI-observable change: byte-identical decode
results, same public Python API.

### Evidence (from the two superseded profiling items)

`level photo --native` on `IsvKran32.unr` (original Unreal, Vortex Rikers: 1705 brushes, 1439 mesh
actor instances, only 108 distinct meshes) took ~75s wall clock, cProfile-scoped to `build_scene`
(2026-09-11). Not yet a committed regression/benchmark harness — do that as part of this item's
build.

| Function                                               | Calls      | Cumulative | Own time |
|--------------------------------------------------------|------------|------------|---
| `read_compact_index` (upackage.py:40)                  | 61,205,527 | 19.76s     | 19.76s (leaf) |
| `read_fstring` (upackage.py:56)                        | 6,428,912  | 12.98s     | 7.04s |
| `read_name` (upackage.py:208, inside `_parse_package`) | 6,428,452  | 15.23s     | 2.25s |
| `_parse_package` (upackage.py:201)                     | 3,404      | 69.97s     | 28.90s |
| `parse_package_bytes` (upackage.py:189)                | 3,404      | 69.99s     | 0.02s |
| `load_package` (upackage.py:177)                       | 3,404      | 78.40s     | 0.59s |

3,404 calls to `load_package`/`_parse_package` for 108 distinct packages in ONE photo of ONE level
is the caching gap; the 61M `read_compact_index` calls are the per-call cost — both real,
independent wins, both closed by this item.

**Scope: read path only.** The write path (`native/codec.py`'s `write_ci`/`write_fstring`,
`native/pkg_write.py`'s encoder) and the `UModel` BSP-body codec (`model_read.rs`/`model_write.rs`
+ its deliberate Python oracle `native/umodel.py`) are untouched — different concern, not part of
this consolidation.

## Current state — 6 files, 7 duplicate decoders

| Location              | Owns                                                                                                                                                                                           | Real behavioral delta from `upackage.py` |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---
| `upackage.py`         | canonical core: compact-index, FString, header, name/import/export tables, `Package`, `PropertyTag`/`read_property_tags`                                                                       | — |
| `dxpkg.py`            | header (names+imports only)                                                                                                                                                                    | negative-length name = UTF-16LE (DX Unicode group names); `upackage` rejects negative length. Version allowlist `(61,68,69)`. |
| `utexture.py`         | full header+name+import+export                                                                                                                                                                 | DoS count-bound guard (declared table counts vs. file size) before any entry read; `upackage` has none. |
| `proceduraltex.py`    | `_compact_index` (trailing-blob slice only)                                                                                                                                                    | silently stops on buffer overrun instead of raising — a correctness bug, not a feature. |
| `uscript/gate.py` (a) | `_parse_header`/`Header` (`gate.py:41`) — full fixed-header struct: tag, version, licensee (high 16 bits), flags, and the 3 tables' raw byte `(count, offset)` pairs, plus the GUID byte range | needs raw byte OFFSETS/EXTENTS for its own purposes (GUID masking in `gate()`, region attribution in `_locate()` for diagnostics), plus the unmasked `licensee` half `upackage.Package.version` already discards (`upackage.py:206` keeps only the low 16 bits) — used in `gate()`'s VERSION-differs check and `_locate()`'s diagnostic dump. |
| `uscript/gate.py` (b) | `_name_table_raw` (`gate.py:64`) — a second, parallel name-table walk                                                                                                                          | needs the per-name flags u32 that `upackage.Package.names` (a bare `list[str]`) discards. |
| `native/pkg_write.py` | full header+name+import+export (`ParsedPackage`/`parse_package`)                                                                                                                               | none — turned out to be a 4th plain production copy, not a deliberate oracle (see below). |

Owner-confirmed via `AskUserQuestion` in the 2026-09-11 design session that produced this spec: fold
all of these into the one core (read-path scope; `native/pkg_write.py` included after the oracle
question below), and drop `dxpkg`'s version allowlist — the core reads what it can; a genuinely bad
layout still fails on structural integrity checks (bad magic, table overrun). This also answers the
parked question in `migrate-utexture-py-dxpkg-py-onto-the-unified/questions/keep-version-allowlist.md`.

### `native/pkg_write.py` is not an oracle

It looked like a deliberate independent-language safety net (the way `native/umodel.py` is for the
Model-body codec), but two of its four call sites are ordinary production reads of real files
(`native/unbuilt.py:157` texture-kind lookup, `native/pkgref.py:60,82`), unrelated to any writer
self-check. Only two ad hoc round-trip tests reparse the writer's own output with it, and
inconsistently — one already uses `upackage._parse_package` for the identical check
(`tests/test_native_roundtrip.py:199` vs `:221`). Folding it into the one core loses nothing: the
real oracle independence axis is read-vs-write (the encoder in `pkg_write.py`/`native/codec.py`
stays a separate, untouched Python implementation), not Python-vs-Rust.

## Design

### Rust core — `uedcli-native/src/package_read.rs`

Pure functions/structs, no PyO3 inside (matches the existing `light.rs`/`model_read.rs` style —
`cargo test`-able with no Python), hand-rolled (no new crate: the codebase already hand-rolls this
in `model_read.rs`/`model_write.rs`, no `byteorder`/`nom` in use):

- `read_compact_index(buf, pos) -> (i64, usize)`
- `read_name(buf, pos, version) -> (String, u32 /* flags */, usize)` — one decoder: negative
  compact-index length = UTF-16LE of `-length` code units, positive = latin-1. No per-game branch;
  the length sign is a wire fact, not a version or game guess.
- `read_fstring(buf, pos) -> (String, usize)` — the generic FString reader stays a separate function
  from `read_name` (the negative-length convention is a name-table fact, not proven true of every
  FString caller).
- `parse_package(buf) -> Result<RawPackage, PkgError>` — header + name/import/export table walk,
  with `utexture.py`'s DoS count-bound guard (every declared count checked against file size before
  the table loop) applied universally.
- `read_property_tags(buf, pos, end, names) -> Result<(Vec<RawPropertyTag>, usize), PkgError>`.

`RawPackage`/`RawPropertyTag` are plain structs (version, licensee, flags, `Vec<(String, u32)>`
names (text + per-entry flags, decoded together — see "Python shell" below for how this splits on
the Python side), `Vec<(i64,i64,i32,i64)>` imports (ClassPackage/ClassName/PackageIndex/ObjectName
— all four raw indices, matching `upackage.Package.imports`'s existing all-int tuple shape exactly;
an earlier draft of this spec wrongly wrote the 4th field as a `String`, corrected here),
`Vec<ExportEntry>` exports) — enough to
reconstruct today's `upackage.Package` one-for-one, plus the flags `gate.py` currently re-derives
by hand. It also carries the raw header layout `gate.py`'s own `Header`/`_parse_header` needs and
`upackage.Package` currently doesn't expose: `licensee` (the high 16 bits `upackage` today
discards — `upackage.py:206` keeps only `ver & 0xFFFF`), `name_offset`/`name_count`,
`import_offset`/`import_count`, `export_offset`/`export_count`, and `guid_range: Option<(usize,
usize)>` — closing `gate.py`'s second duplicate decoder (the byte-offset header struct, not just
the name-table walk) in the same PR2 pass.

### PyO3 binding

One new `#[pyfunction] fn parse_package_raw(py: Python, buf: &[u8]) -> PyResult<PyObject>` in
`lib.rs` — named distinctly from Python's `upackage.parse_package_bytes` (same name, different
signature/shape, would read confusingly in tracebacks and greps) — following the existing
`bake_radiance` shape (`lib.rs:504`: takes plain args, returns `Vec<tuple>`) — not `bake_lighting`
(`lib.rs:474`), which mutates an opaque `&mut Built` in place and returns `PyResult<()>`; nothing
here needs a resident handle, so no new opaque `pyclass` (unlike `Built`) is needed.
Errors: a new `PackageError` via `create_exception!` + the existing `map_err`-style conversion, so a
malformed package raises a normal Python exception, never a panic/traceback.

### Python shell

`upackage.py`'s public surface is frozen at the function/class level: `Package`, `load_package`,
`parse_package_bytes`, `_parse_package`, `read_property_tags`, `name_of_ref`/`object_path`/
`object_class_name`. Bodies now call `uedcli_native.parse_package_raw(buf)` and reshape the result
into the existing dataclasses, plus new fields (`licensee`/`name_offset`/`import_offset`/
`export_offset`/`guid_range`) `Package` gains for `gate.py`'s sake.

**Revised during planning (2026-09-11), replacing the original "merge into tuples" design below —
see `plan.md` for the finding that forced this:** `Package.names` stays exactly `list[str]`,
unchanged. A new frozen dataclass captures what the wire format actually pairs per name-table
entry — text plus the real engine's per-entry `EObjectFlags` bits (this project's own
reverse-engineering, `USCRIPT-COMPILER.md`, already identified two live values: `RF_Native`
0x04000000 and `RF_HighlightName` 0x400). Named `NameEntry`, not the engine's own `FNameEntry` —
this codebase already drops Epic's struct-prefix convention for decoded types (`Package`,
`PropertyTag`, not `UPackage`/`FPropertyTag`), and the real `FNameEntry` also carries a hash and
hash-bucket next-pointer that never touch disk, so a same-named type would overclaim 1:1 fidelity
with the C++ struct:

```python
@dataclass(frozen=True, kw_only=True)
class NameEntry:
    text: str
    flags: int
```

`Package.name_entries: list[NameEntry]` is added alongside the untouched `Package.names: list[str]`
— same length, same order (both come from one Rust decode call, so alignment isn't a
separately-maintained invariant to break). This is NOT the back-compat shim the review rejected
(that was two representations of the *same* data for migration convenience); the flags are
genuinely new information no current caller has, so adding them as a new field is ordinary API
growth, not a compatibility hack. Zero of the ~65 existing call sites that index/iterate `.names`
need to change — only `gate.py` (PR2) touches `name_entries`.

*(Original design, superseded: `Package.names` becomes `list[tuple[str, int]]`, migrating every
caller. Planning found the real caller surface is 20+ files / 65+ sites — not the ~15 estimated
above — several of which (`native/saveorder.py`'s dict-keyed-by-name and set-of-names
comprehensions) need real semantic rework, not a one-line unpack, since a tuple changes hashing/
equality semantics for those data structures. Not worth the risk for information most callers
never wanted.)*

`_parse_package` keeps its name and signature for the direct importers (`uscript/gate.py`,
`uscript/reorder.py`, `native/saveorder.py`, tests) — `Package.names`'s shape inside its return
value is unchanged; only the new `name_entries`/`licensee`/offset fields are additions.

### Caching

Two tiers, per `direction/packages.md`'s own "decoded package primitives are cached per-package on
disk" line:

**Resolved (investigated during planning):** `uprops/values.py:523`'s `resolve_class_defaults`
comment ("packages load once, shared with the render cache") refers to `_pkgs`, a dict threaded
through ONE call's own ancestor-chain walk (and into `render_default_tag`'s recursive calls) so a
single class's superclass chain doesn't reload a package twice. It is real and does its narrow job.
It does NOT persist across separate top-level calls: `preview_native.py:202-204` calls
`resolve_class_defaults(actor.cls, resolver=index.resolver())` once per actor instance with no
`_pkgs` argument, so every one of 1439 actor instances starts a fresh empty dict — this is the
exact mechanism behind the 3,404-call count (108 distinct packages × many actors sharing classes).
Not a bug to fix in place: the in-process memoization below sits one layer lower, inside
`load_package` itself, and fixes this pattern without touching `preview_native.py` or `_pkgs` at
all — a package loaded for actor #1's chain is already cached when actor #2's fresh chain-walk
calls `load_package` on the same path.

1. **In-process memoization** inside `load_package`, keyed by `(realpath, st_size, st_mtime_ns)`.
   This alone collapses most of the 3,404-calls-for-108-distinct-packages number within one render.
2. **On-disk tier**, reusing `schema_cache.py`'s exact proven scheme rather than inventing a new
   one: `user_cache_home()/pkg/` (sibling to the existing `schema/` cache dir), same stat-tuple key
   `(CACHE_VERSION, realpath, size, mtime_ns)`, `marshal` serialization, `_atomic_write`
   (tmp+`os.replace`), a version/stat mismatch is a silent miss, a **write failure is a loud
   `CacheWriteError` naming the directory** (never a swallowed failure — `direction/packages.md`'s
   own rule), and `sweep()`/`uedcli cache gc` integration for footprint control.

## Migration steps (incremental rollout)

**PR 1 — the core.** `package_read.rs` + PyO3 binding + `upackage.py` rewired onto it + both cache
tiers. Delivers the profiling win immediately; touches nothing else. All ~15 existing `upackage`
importers get the speed + cache for free.

**PR 2 — retire the duplicates**, now that the core exists to retire onto:
- `dxpkg.py`: drop `_read_compact_index`/`_read_name*`/`PackageHeader`/`_parse_header`; use
  `upackage.load_package`; drop the version allowlist.
- `utexture.py`: drop `_ci`/`Package`/`load_package`/`_read_props`; use `upackage.Package`/
  `load_package`/`read_property_tags` + a small decoded-value helper over `PropertyTag.raw`.
- `proceduraltex.py`: `_compact_index` calls `upackage.read_compact_index`.
- `uscript/gate.py`: drop `_name_table_raw` AND `_parse_header`/`Header` — use `upackage._parse_package`
  for both the decoded tables and the new raw-offset/`guid_range` fields `_locate()`/`gate()` need.
- `native/pkg_write.py`: drop `ParsedPackage`/`parse_package`; its 4 call sites (`unbuilt.py`,
  `pkgref.py`, `saveorder.py`, the 2 round-trip tests) use `upackage.load_package`/`_parse_package`.

Each PR follows `dev/docs/rules/building-features.md`'s runbook (worktree, verify, one subagent
review, squash-merge). PR 2's five migrations are mechanical/low-risk and land together; PR 1 is the
one that needs real scrutiny (new Rust code, FFI boundary, cache correctness).

## Tests

- `cargo test` unit tests for `package_read.rs` against known-good byte fixtures per substrate
  (v61 DX, v68, v69 UT) — the independent oracle (`direction/packages.md`: "never against a fixture
  our own encoder produced").
- A synthetic Unicode-name fixture (`20_AireGardens.dx`-style) and an absurd-declared-count header
  — both currently untested at the core level, only in `dxpkg`'s/`utexture`'s own suites.
- Existing suites stay green with zero changes needed where `Package.names` typing is preserved:
  `test_utexture_corpus*.py`, `test_utexture_blocks.py`, `test_utexture_layout.py`, `test_dxpkg.py`,
  `test_stub.py`, `test_proceduraltex*.py`, `test_native_roundtrip.py`, uscript gate/reorder tests.
- A before/after parity test over the real corpus: same `Package` output (names, imports, exports)
  from the old Python parser and the new Rust one, on every `.u`/`.utx`/`.dx`/`.unr` fixture in the
  repo — run once, delete after PR 1 merges (it's a migration guard, not a durable test).

## Follow-up (not this item)

- Once built, record the Rust-vs-Python choice, the two-tier cache design, and the
  dropped-version-allowlist call in a new `dev/docs/rationale/packages.md` (implementation
  rationale, agent-owned — no owner approval needed, unlike `direction/`).
- `direction/packages.md` needs no edit: it says "exactly one low-level reader (`upackage.py`)" and
  stays true regardless of what language backs it.

## Refs

`dev/docs/direction/packages.md` ·
`dev/docs/board/stale/upackage-load-package-has-zero-caching-3404/` ·
`dev/docs/board/stale/port-ue1-package-primitive-decode-to-rust-61m/` ·
`dev/docs/board/stale/migrate-utexture-py-dxpkg-py-onto-the-unified/` (full delta analysis in its
`spec.md`) · `dev/docs/board/inbox/proceduraltex-py-correctness-and-duplication/` (one of its four
findings) · `uedcli-native/src/lib.rs` · `uedcli/upackage.py` · `uedcli/schema_cache.py`

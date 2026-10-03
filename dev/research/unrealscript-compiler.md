# The UnrealScript compiler — purpose, fidelity target, and prior art

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** Why does uedcli contain its own UnrealScript compiler, how close is it to the
byte-parity bar it set itself, and what prior art exists for the Rust rewrite to borrow or validate
against?

## Summary

- **The motive is an editor-free pipeline, not compilation itself.** `UCC.exe` is a closed Win32
  binary needing wine-in-docker, a substrate laid out its way, `EditPackages=` injected *inside*
  `[Editor.EditorEngine]` (it rewrites the ini), and textual success detection. uedcli's compiler is
  the one path that compiles `.uc` with no docker, wine, or editor.
- **The bar is byte-identity.** Owner ruling 2026-09-05: reproduce UCC's real algorithm, never fit a
  table. Finish line 30 real packages. Exclusion set: exactly two per-compile-random fields (the
  16-byte package GUID, a `UTexture`'s `InternalTime[2]`).
- **Proven strict-byte-exact: 4 real packages**, all UED22, all single-class (`FrameBuilder`,
  `RahnemBrushBuilders`, `DavesBrushBuilders`, `UnrealShare`), plus controlled fixtures and the
  DXORIG conversation proof. **~24 further real packages pass only `perm_gate`**, which tolerates
  table order and FName case — the docs call that an open item, not a pass. Content parity is broad;
  *ordering* parity is 4/30.
- **Two residual causes, both ordering.** Every UT99 package fails strict on one known gap: UT99's
  own name pool was never extracted (`ENGINE_NAME_POOL`/`HIGHLIGHT_NAME_POOL` are
  UED22-`core.dll`-specific). `ExtendedBuilders` (UED22) fails on a name-table `qsort`-tie residual
  narrowed, after three disassembly passes and two live captures, to one unverified assumption:
  whether `FName` slot indices are ever reused.
- **The bytecode codec is the one unambiguously proven claim:** `bytecode.py` round-trips **all
  3,581** `UFunction`/`UState` scripts across all 32 stock UED22 packages byte-exact.
- **`ordering.py` is the crux.** It orders all three package tables, and order is not cosmetic:
  bodies reference names and objects *by table index*, so a permuted table changes every body.
- **`reference{,_ut99,_dxorig}.py` are not corpora** — three UCC *driver* modules, one per substrate,
  that mint goldens in an ephemeral wine container. Test-only; no shipping module imports them. Same
  for `gate.py` (545 LOC): 10 test importers, zero production.
- **`uscript compile` is the sole leaf verb**: positional `SRC-DIR` plus `-o/--out`, `--package`,
  `--deps`, `--json`. Nothing else in uedcli consumes a compiled `.u`. It is a terminal verb.
- **The Rust rewrite spec never mentions the compiler.** It scopes in "everything under the current
  `uedcli/` package" and names `uned/` as the only exclusion — 11k LOC in scope by silence, with no
  costing, sequencing, or parity-bar statement.
- External prior art is rich and MIT-friendly for *decoding*; for *compiling* it is near-absent
  (Findings 10–13).

## What we have today

`old/uedcli/uscript/` — 22 files, **11,043 LOC**. Tests: 26 `test_uscript_*.py` files, **4,201 LOC**,
**203 test functions** (several parametrized over package lists, so the campaign's "247 passed" /
"285 passed" claims are expanded counts; not re-run here). Goldens: **77 committed `.u`** and
**63 `.uc`** under `old/uedcli/tests/fixtures/uscript/` — 37 top-level `.u`, 6 `realpkg/` package
dirs, 34 `ut99/` package dirs.

| File | LOC | Purpose |
|---|---|---|
| `compile.py` | 3,299 | Declarations → object graph: class header/flags, vars, enums, structs, consts, `defaultproperties` diffing, imports, `#exec` wiring, multi-class two-pass signature graph |
| `lower.py` | 1,692 | AST → `Tok` bytecode stream with type inference, operator/native resolution, flat jump patching |
| `parser.py` | 1,078 | Recursive-descent parser for the full UED22 grammar → `ClassDecl` |
| `conimport.py` | 703 | `#exec CONVERSATION IMPORT`: `.con` binary parser + `ConSys` object graph → sibling `<Pkg>Text.u`/`<Pkg>Audio*.u` |
| `natives.py` | 627 | Operator/native catalog; reads `iNative`/`FunctionFlags` out of compiled `.u` |
| `gate.py` | 545 | Parity gate: strict `gate()` (masked byte compare) + `perm_gate()` (identity/permutation) with structural first-divergence diagnostics |
| `reorder.py` | 377 | Re-derive the true table order by decoding an already-emitted package's own `<<FName`/`<<UObject` streams |
| `bytecode.py` | 332 | Byte-exact `EExprToken` decode/encode with the dual on-disk/in-memory cursor |
| `ordering.py` | 319 | `SavePackage` table ordering: gather + instruction-exact MSVC CRT `qsort` port |
| `env.py` | 257 | Dependency symbol environment over the `.u` search path (via `upackage`/`uprops`) |
| `lexer.py` | 259 | Token stream; keywords deliberately left contextual |
| `texture_import.py` | 245 | `#exec TEXTURE IMPORT`: PCX decode → `UTexture`+`UPalette` data |
| `model.py` | 212 | The fully-linked `CompiledPackage` contract between compiler and serializer |
| `reference_ut99.py` | 201 | Drives **UT99's own** `UCC.exe` in a container |
| `serialize.py` | 191 | `CompiledPackage` → `.u` bytes (purely mechanical; reuses `native/pkg_write.py`) |
| `reference_dxorig.py` | 190 | Drives the **original Ion Storm DX** `UCC.exe` (the only build with a `CONVERSATION IMPORT` handler) |
| `global_index.py` | 157 | Runtime-dumped `GObjNames`/`GObjObjects` order + the two name-flag pools |
| `reference.py` | 154 | Drives the **UED22** `UCC.exe`; also the `batchexport` decompiler |
| `ast.py` | 152 | AST nodes, including `ClassDecl.decl_order` (true source-textual top-level order) |
| `crc.py` | 27 | `appStrCrc` — CRC-32/BZIP2 over UTF-16LE `ScriptText` |
| `tokens.py` | 25 | Token model |
| `__init__.py` | 1 | — |

Plus data: `uscript/data/gobjnames_ued22.json` (93 KB) and `gobjobjects_ued22.json` (437 KB) — the
dumped engine global index, UED22 only.

## Findings

### 1. Why not just use `UCC`?

`old/USCRIPT-COMPILER.md` never states the motive in one line, so this is assembled from
`toolchain.md`, `reference*.py`, and the CLI help (all verified in-repo).

`UCC.exe` works, and uedcli does use it — as the golden. What it cannot be is part of a pipeline:

| UCC constraint | Source | What an editor-free pipeline needs |
|---|---|---|
| Win32 binary; runs only under wine in a docker container (`ephemeral_build_container`) | `reference.py` | A native binary, no container, no wine |
| Sources must sit at `<GameRoot>/<Pkg>/Classes/*.uc`; output lands in `System/` | `toolchain.md` | Compile a directory in place to a chosen `-o` path |
| Needs `EditPackages=<Pkg>` inserted **inside** `[Editor.EditorEngine]` — appended at EOF it is silently skipped — and `make` then **rewrites the ini** | `toolchain.md`, `stub.inject_edit_package` | No mutable global config |
| Success detection is textual: exit 0 **and** `Success - 0 error(s)` on stdout **and** output > 64 bytes (a 64-byte `.u` is a failed compile that exits 0) | `toolchain.md` | A real exit code; `uscript compile` exits 2 naming the construct |
| Each engine build is its own substrate: UED22, UT99 and DXORIG `UCC.exe` produce different bytes and cannot cross-compile | `USCRIPT-COMPILER.md` | One compiler parameterised by a `--deps` search path |
| OldUnreal's rebuilt `Editor.dll` **removed** the `#exec CONVERSATION IMPORT` handler entirely (silent no-op) | `USCRIPT-COMPILER.md`, `reference_dxorig.py` | A capability no current UCC build has in one place |
| `make` rebuilds by directory timestamp and cascades into later `EditPackages` entries | `uscript-path-to-30-packages` | Deterministic, single-package compilation |

The DX conversation row is the strongest standalone argument: that importer exists in no maintained
toolchain. `conimport.py` (703 LOC) reimplements it — the one place uedcli's compiler does something
no available `UCC` can.

### 2. Implementation shape and pipeline

Verified pipeline (module docstrings + `cli/commands/uscript.py`):

```
*.uc  ─ lexer.py ─► tokens ─ parser.py ─► ClassDecl (ast.py, decl_order preserved)
                                              │
                        env.py (upackage/uprops read .u deps: supers, iNative, CRCs, types)
                                              ▼
        compile.py  pass 1 _prepass_signatures (every class's ClassSig)
                    pass 2 per class: declarations + defaults + #exec
                              │        └─ lower.py/natives.py → Tok stream → bytecode.py encode
                              │        └─ texture_import.py (PCX), conimport.py (.con siblings)
                              ▼
        serialize.py → provisional .u bytes
                              ▼
        reorder.py (decode own bodies → ref streams) + ordering.py (gather + msvc_qsort)
                              ▼
        serialize.py again, in true table order → .u        [gate.py compares vs UCC golden]
```

Two things about this shape are unusual and worth flagging for a reimplementation:

- **It serializes twice.** Table order is not computed from the AST; it is re-derived by *decoding
  the package the compiler just wrote* (`reorder.py`), then the package is re-emitted. Three of the
  ordering bugs the campaign fixed were this detour — true declaration order cannot be recovered
  from compiled bytes, because the `Children` chain bins properties and non-properties into separate
  sub-chains and loses their interleaving. The fix threaded `ast.ClassDecl.decl_order` back in,
  i.e. partially bypassed the decode path.
- **The hot path is quadratic.** `compile_package_dir` re-finalizes and re-serializes the whole
  package per class and discards `ClassGraph` memoization — O(N²) in classes, on exactly the axis
  the 30-package goal needs to grow (board item, p2).

**Refusal discipline is real and worth preserving.** 100 explicit `raise` sites (`compile.py` 51,
`lower.py` 37, `texture_import.py` 10, `conimport.py` 1, `serialize.py` 1), each naming the
construct; an adversarial review confirmed no path emits a plausible-but-wrong token.
`cli/commands/uscript.py` maps every compiler error onto exit 2, never a traceback.

### 3. Language-feature coverage

Supported = lowers/compiles; evidence column cites the in-repo mechanism or the refusal site.
Confidence: all rows **verified in-repo** (grep/read), not claims about the engine.

| Feature | Supported | Evidence |
|---|---|---|
| Class header + `extends`/`expands` | yes | `compile._build_class` |
| Class modifiers `abstract native intrinsic transient safereplace noexport perobjectconfig nativereplication` | yes | `_CLASS_MODIFIER_FLAGS`; any other modifier raises |
| Scalar `var` (all types), static arrays, object/class/struct/enum-typed vars | yes | `_resolve_var_type`; `_VAR_MODIFIER_FLAGS` |
| Dynamic arrays (`array<T>`) | partial | declared yes; unknown element type raises `LowerError("dynamic array element type unknown")` |
| `const`, `enum`, `struct` (incl. non-scalar members) | yes | `compile.py` member builders |
| `struct X extends Y` | **no** | `NotImplementedError("struct … extends … not supported yet")` |
| Dynamic-array struct member | **no** | named `NotImplementedError` |
| `defaultproperties` (own + inherited-override diff) | yes | `_super_field_order`, `_auto_emit_defaults` |
| Explicit struct / array defaults | **no** | `NotImplementedError("explicit struct default …")`, `"explicit array default …"` |
| `function`, `event` | yes | `compile.py:740` accepts only these two kinds |
| `operator`/`preoperator`/`postoperator`/`delegate` **declarations** | **no** | parsed (`_FUNC_KW`) then rejected: `"function kind … not supported yet"` |
| Function modifiers `final singular native simulated static` | yes | `_FUNC_MODIFIER_FLAGS`; others raise |
| Param modifiers `optional out coerce` | yes | `_PARAM_MODIFIER_FLAGS`; others raise |
| Array params/locals | **no** | `"array param/local … not supported yet"` |
| `if`/`while`/`for`/`switch`/`return`/`break`/`continue`/`goto`/labels/`assert`/`stop`/locals/assignment/expression statements | yes | `lower._st_*` (16 handlers) |
| `do … until` | **no** | parsed (`parser._parse_do` → `Stmt(kind="do")`); no `lower` handler → `"statement 'do' not supported yet"` |
| `foreach` + `EX_Iterator`/`IteratorNext`/`IteratorPop` | yes | `lower._st_foreach`, `foreach_depth` |
| `state { Label: … }` + label table + `EX_Nothing` padding | yes | `compile._build_one_state`, `compile-model.md` |
| `state X extends Y`, `ignores`, state function overrides | **no** | three named `LowerError`s |
| `replication { … }` | **no** | `_reject_unsupported` |
| `cpptext` / `structcpptext` | **no** | parsed then `_reject_unsupported` |
| Native classes (`RF_Native`, `CLASS_Inherit`, transitive `PackageImports`) | yes | `compile.py`, `compile-model.md` |
| `ProbeMask` (inheritance-accumulating `EProbe` bits) | yes | `_EPROBE_TABLE`, `_probe_bits` |
| `IgnoreMask` | **no** | tied to `ignores`, unimplemented |
| Operator overload resolution by operand type | yes | `natives.Catalog`; `_WIDEN` is **invented**, not UCC's `ConversionCost` (open item D) |
| Constant folding into operator param types | partial | expected-type threaded through assign/return/`for`; **function-argument position not threaded** |
| `#exec TEXTURE IMPORT` (PCX) | yes, 1 per class | `texture_import.py`; two tie-break formulas are declared judgment calls |
| `#exec CONVERSATION IMPORT` | 16 of 19 event types | `conimport.py`; multiple imports per package raise |
| `#exec MESH/AUDIO/SOUND/FONT IMPORT` | **no** | `_reject_unsupported`; owner scoped out 2026-09-05 |
| Cyclic same-package class references | yes | `_prepass_signatures` two-pass signature graph |
| Base class with no super | **no** | `"base class … has no super — later rung"` |

### 4. The fidelity target, and what is actually proven

The oracle is **a fresh `UCC.exe` compile of the exact same `.uc` sources**, never a shipped retail
`.u` (those are editor-serialized: own zero-valued defaults dropped, `None`-holes accreted from GUI
resaves). The comparison is raw bytes. Two gates, in `gate.py`:

- `gate()` — **strict**: byte-for-byte, masking only the GUID and `InternalTime[2]`. Both are
  per-compile-random: two clean UCC compiles of identical source differ in exactly those regions.
- `perm_gate()` — additionally tolerates name/import/export **table order** and FName **case**. The
  owner ruled order must be reproduced, not excluded, so this is explicitly a **diagnostic
  stepping-stone**; `parity.md` states a `perm_gate`-only package is an open item.

Both also compare each export's canonicalised `Super` and `ObjectFlags` — added after an adversarial
review found `perm_gate` missed them, masking a real bug (overrides emitted `Super=0`).

**Proven, unambiguously:** all **3,581** `UFunction`/`UState` scripts across all 32 stock UED22
packages decode and re-encode byte-exact (`test_uscript_bytecode.py`). Because `Tok` parts are
index-independent, lowered tokens compare equal to UCC-decoded tokens iff they encode identically —
a clean lowering oracle.

**Strict gate, real packages: 4** (all UED22, all one class). Plus `ConvTest` (DXORIG) and controlled
fixtures `UscHello`/`UscVars`/`UscBB`/`UscFn`/`UscW`/`UscSt`/`UscStateForeach`/`UscTexAsym4x4`.
**`perm_gate`-exact but strict-failing: ~24 real packages** (`ExtendedBuilders`; `Fire`, `UWeb`,
`IpServer`, `UTServerAdmin` and ~19 community UT99 mutators). So 28/30 at the permutation level,
**4/30 at the stated bar**.

Verification infrastructure (`uscript-algorithm-fidelity/harness/`, 675 LOC) is genuinely
non-circular: `extract_ename.py` (114) recovers a substrate's intrinsic `EName` order by
disassembling `core.dll`'s `RegisterNames` `push` sequence, a computation over the binary rather than
a baked list; `dump_gobj.py` (178) plants a winedbg INT3 at `SavePackage` and dumps live
`GObjNames`/`GObjObjects`; `dump_name_creation_order.py` (163) breaks on every `AllocateNameEntry`
call during a real compile; `probe_encounter_order.py` (63) isolates the own-name encounter rule by
controlled compiles; `reproduce_from_dump.py` (157) checks the shipped dump reproduces every
fixture's order, with the dump supplying gather index, golden bodies supplying counts and golden
tables the expected output.

The campaign log's honesty is an asset: it records a fitted `OBJECT_ORDER`/`NAME_ORDER` table caught
by review and **deleted**, a diagnostic `>` → `>=` qsort tweak identified as curve-fitting and **not
applied**, and a shared-mechanism fix that landed with a regression against an already-passing
package which only a full-suite re-run caught.

### 5. `ordering.py` — what has to be ordered, and why

**What:** all three package tables — names, imports, exports.

**Why it is not cosmetic:** object bodies reference names and objects *by table index*. Permute the
name table and every name-index byte inside every body shifts. Byte parity is therefore impossible
without reproducing order exactly.

**The mechanism** (RE'd from `uned/UED22/core.dll`, ImageBase `0x10000000`):
`UObject::SavePackage` @`0x277c0` gathers each table, then sorts it with `appQsort` @`0x315c0` — a
thunk to the MSVC CRT `qsort` @`0x77cb0` — **descending by an integer reference count**.

| Table | Descending key | Gather (tie) order |
|---|---|---|
| names | `NameIndices[globalNameIndex]` | global `FName` registration order |
| imports | `ObjectIndices[obj]` | global `GObjObjects` creation order |
| exports | `ObjectIndices[obj]` | the package's own object creation (parse) order |

Keys come from the tagging pass `FArchiveSaveTagImports`: `operator<<(FName)` @`0x162e0` does
`NameIndices[name]++`; `operator<<(UObject)` @`0x161c0` does `ObjectIndices[obj]++` and recurses into
an import's Outer chain (why `Core` sorts first among imports). Both arrays are `AddZeroed` in the
linker ctor @`0x4a6f0`, so the key is a pure reference count.

**Three facts make this hard, and are why `ordering.py` is 319 LOC of ported `qsort`:**

1. **The CRT `qsort` is unstable**, so count-tied entries are permuted deterministically but
   non-obviously, and that permutation is part of the output. `msvc_qsort` ports the modern MSVC
   algorithm (`__shortsort` selection for runs ≤ 8, else median-of-3 kept in place with a Hoare
   partition skipping the equal-key run), re-verified instruction-exact **three times** — one pass
   specifically settled the `>` vs `>=` tie test as strict `>`.
2. **The gather order is a boot+load artifact**, not derivable from the source under compilation: the
   engine's live global `FName`/`GObjObjects` index after booting and loading dependencies. Hence
   the runtime dump, shipped as per-substrate JSON. **UED22 only** — precisely why every UT99
   package fails the strict gate.
3. **The gather must interleave by true source-textual declaration order**, which the compiled `.u`
   cannot express. Three successive bugs were this shape, one level up each time: enum-vs-property
   interleaving; a function's locals registering inline rather than deferred; and, across a class
   boundary, a multi-class package's per-class `defaultproperties` value names. Two extra rules: a
   package self-reference registers at class-header time, a `defaultproperties` name-typed *value*
   registers last.

**The open residual, precisely.** `ExtendedBuilders`'s name table diverges in 16 entries. Everything
cheap is eliminated by measurement: the `qsort` port is instruction-exact; the decoded gather arrays
and refcounts are byte-identical to golden's across all 84 names; the live capture confirms the
relative registration order of the second diverging region; and feeding golden's own bytes back
through `order_package` reproduces the identical divergence — so the bug is in the *input array*, not
the sort. One surviving hypothesis: `FName::FName` pops from an `Available` free-list before
appending, so an index may be **reused**, making `ordering.py`'s `by_name_index` sentinel (own-new
names sort after all dumped names) wrong. The existing capture reads `AllocateNameEntry`'s `Name`
argument but never its `Index`, so it cannot see this. Next steps named in-repo: read the `Index`
argument (cheap), or hook the `qsort` call and dump its real input array (conclusive).

### 6. `reference.py`, `reference_ut99.py`, `reference_dxorig.py` — drivers, not corpora

These are **UCC driver modules, one per engine substrate** — how goldens get minted, not stored
sources. Each stands up an ephemeral wine container, stages `.uc` sources, injects `EditPackages`,
runs `wine UCC.exe make`, and reads the resulting `.u` back out. `reference.py` also wraps
`ucc batchexport`, the decompiler that extracts `.uc` from a real `.u` to seed the corpus.

| Module | Substrate | Why it exists separately |
|---|---|---|
| `reference.py` | `uned/UED22` (committed) | OldUnreal-patched DX engine, package v69 — the primary substrate |
| `reference_ut99.py` | `uned/UT99` (gitignored, `fetch_ut99.sh`) | UT99's `Core.u` and native indices differ; UED22's UCC **cannot** compile UT99 packages |
| `reference_dxorig.py` | `uned/DXORIG` (gitignored, `fetch_dxorig.sh`) | Only an original Ion Storm build still has the `#exec CONVERSATION IMPORT` handler |

**Reachability (verified):** importers are `old/uedcli/tests/test_uscript_*.py` plus the board
harness (`reference_ut99`/`reference_dxorig` also import `UccError` from `reference`). **No shipping
module imports them** — the sibling finding is confirmed, and extends to `gate.py`. Correct by
design: drivers and gate are test-time oracles. For costing, ~1,090 LOC of `uscript/` (`gate` 545 +
three drivers 545) is **test infrastructure**, not product.

### 7. Packages it compiles against, and how dependencies resolve

`env.InstallEnv(search_dirs)` resolves symbols against **already-compiled `.u` packages** on a search
path, using the byte-exact read side: `old/uedcli/upackage.py` (328 LOC) and `old/uedcli/uprops/`
(1,782 LOC). `bytecode.py` is described as extending `uprops.ufield._walk_expr` from a read-only skip
walker into a full decode/encode — the compiler sits directly on the decoder; they are one codebase.

It reads from a dependency: home package, super chain, stored `ScriptText` CRC (an imported
dependency's CRC is **read from its home package, never recomputed**), member/param types, struct
members, and each callee `UFunction`'s `iNative` and `FunctionFlags`.

**Required minimum:** `core.u` and `Engine.u` in the **first** search dir
(`compile.py`: `pkgs = ["core.u", "Engine.u"]`). The CLI puts the UED22 substrate first when
installed, else requires a `--deps` dir holding both; none at all exits 2. Beyond that discovery is
transitive: `_extra_super_packages` fixed-point-walks newly-discovered classes' member types (the fix
that made `Botpack`-dependent mutators compile), and `env.class_home_from_imports` /
`import_only_class_package` resolve a class with no `.uc` source anywhere by scanning another
package's **import** table — a purely static decode. Corpus reality: `native noexport` classes
(`ConSys`, most of DeusEx) don't round-trip even under UCC, so reaching 30 required community UT99
mutators.

### 8. What consumes the output, and CLI reachability

**Confirmed: `uscript compile` is the only leaf verb** — one family, one subparser, five arguments
(positional `SRC-DIR`, `-o/--out`, `--package`, `--deps` repeatable, `--json`). `dispatch.py:115`
routes `uscript`; `run()` raises `CommandError` for any other sub-verb.

**Confirmed: nothing consumes the output.** Every importer of `compile_package_dir` /
`uscript.serialize` outside `uscript/` is the CLI command module or a test. No level build,
materialize, preview, or stub path reads a compiled `.u`. The verb writes `<Pkg>.u` (plus conversation
siblings) and prints the path; the only in-repo consumer of its *bytes* is `gate.py`, in tests. So
11,043 LOC reachable through one verb whose output no other uedcli feature reads — not an argument
against the compiler (the consumer is the engine), but it means no internal dependency forces the
rewrite's ordering here.

### 9. Known live defects

From `old/dev/docs/board/inbox/`. Priority/kind are the items' own front-matter.

| Item | Pri | What is wrong |
|---|---|---|
| `uscript-bare-function-call-name-treated-as` | p4 | Class-discovery pre-pass treats **every** bare-name call's callee as a candidate class, relying on `env.resolve_class` returning `None` to no-op. A function whose name legally coincides with a real class name (separate namespaces) would pull that class's whole transitive `package_imports` into the discovery frontier. Not traced through to whether compiled bytes change. Same review: the 3-site duplicated resolve guard, and `_extra_super_packages` rebuilding a whole-search-path `ClassGraph` per call with no caching |
| `uscript-two-hand-rolled-lexical-scanners` | p4 | `compile._skip_defaultproperties_block` and `compile._mask_lexical_noise` each re-derive comment/string/name-literal rules `lexer._Lexer` already implements. Both verified correct against live UCC today, but a lexer-rule fix would need hand-replicating in up to three places. Blocked on `Token` carrying line/col, not absolute offsets |
| `uscript-import-only-class-fallback-could` | p4 | `env._import_only_class_to_package` indexes import-only classes by casefolded name and `setdefault`s the **first** package found, with no ambiguity check. Probably safe (a coherent UE1 install shouldn't have two different classes of one name), unproven, and contrary to the repo's own no-silent-fallback rule |
| `autonomous-struct-class-compile-diverges-from` | p2 | **Appears stale.** Claims (A) the `Struct` name misses `RF_HighlightName` `+0x400` and (B) struct member `UProperty`s are not `next_field`-chained. Both now look fixed: `global_index.HIGHLIGHT_NAME_POOL` contains `struct`, `enum`, `const`, `state`; `compile.py:2029` chains `s.member_keys` into `next_lookup`. The `_STRUCTURAL_NAMES` set it names no longer exists. Recommend verifying and closing rather than scheduling |
| `extendedbuilders-name-table-qsort-residual` | p3 | The one real ordering blocker on UED22 — see Finding 5. Narrowed to the `FName` index-reuse question |
| `uscript-name-table-member-fname-order` | p2 | Historical: diagnoses member FNames interleaving with stock names. Superseded by the runtime dump; the specific hypothesis ("by property type") was disproven. Likely stale |
| `uscript-compile-package-dir-is-o-n-2-in-classes` | p2 | `compile_package_dir` re-finalizes and re-serializes the whole package per class and discards `ClassGraph` memoization — O(N²) on the growth axis the 30-package goal needs |
| `uscript-pre-merge-hardening` | p2 | Flag maps (`_CLASS_/_VAR_/_FUNC_MODIFIER_FLAGS`, `CPF_EDIT`) are RE'd but only `event`/`final`/`input` are pinned by a golden; latent `Super=0` for a struct/state that `extends`; array/enum/struct default emission load-tested but not byte-parity'd |
| `uscript-path-to-30-packages` | p1 | The campaign's own gap list: `replication`, `#exec` asset imports, expected-type-directed operator overloads, and the corpus itself |
| `uscript-nested-literal-fold-rule-unverified-for` | p3 | The constant-fold rule is unverified in function-argument position (the `_NESTED` sentinel's known hole) |
| `uscript-{resolve-class-has-no-memoization,has-three-small-quadratic-hot-spots}` | p2/p3 | Further perf: no `resolve_class` memoization, three quadratic hot spots |
| `uscript-{in-package-struct-enum-type-resolution,local-struct-member-map-collides-across,same-class-typed-param-context-under,struct-type-cast-vector-rotation,utserveradmin-round-mechanism-edge}` | p3 | Five narrower investigate/implement items in struct/enum/type-resolution and one rounding edge |
| `givemeitems-blocked-by-missing-pcx-texture-asset` | p3 | A corpus package blocked on a missing PCX in the GitHub mirror, not a compiler bug |

Also flagged in `USCRIPT-COMPILER.md` as cross-campaign: `old/uedcli/native/saveorder.py` (the
map-parity path) carries **its own copy** of the CRT `qsort`, which may be the mis-ported classic
variant this campaign initially suspected (`saveorder-msvc-qsort-misport`). One canonical port in the
Rust tree would retire that risk.

### 10. UE1 bytecode and the VM — external documentation

<!--EXTERNAL-10-->

### 11. Tooling comparison

<!--EXTERNAL-11-->

### 12. Has anyone written an independent UE1 UnrealScript compiler?

<!--EXTERNAL-12-->

### 13. What makes one compiler's output byte-identical to another's

<!--EXTERNAL-13-->

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Port the compiler late, after the decoder** | The compiler is built on `upackage`/`uprops`; porting the reader first is forced anyway. No other uedcli feature depends on the compiler, so nothing blocks | Leaves the largest single Python subsystem (11k LOC) alive longest; the Python↔Rust seam would sit where byte-exactness is hardest if any hybrid is attempted |
| **B. Port bytecode codec + ordering first, as standalone Rust crates** | These are the two proven, self-contained, heavily-tested pieces (3,581-script round-trip; instruction-exact `qsort`). They have clean inputs/outputs and no editor dependency. One canonical `qsort` also retires the `saveorder.py` duplicate-port risk | Doesn't deliver a usable verb until the front end follows; risks a long half-ported state |
| **C. Declare `perm_gate` the shipped bar and strict parity a stretch goal** | 28/30 real packages already pass it; the remaining strict failures are all table *order*, functionally inert to the engine. Would let the rewrite ship a working compiler without re-doing the live-capture RE | Directly contradicts the owner's 2026-09-05 ruling, which retired exactly this exclusion. Owner's call only |
| **D. Extract the UT99 name pool, then re-measure** | One known cause explains **every** UT99 strict failure; `extract_ename.py` already does this per-substrate from `core.dll`. Plausibly converts ~19 perm-only packages to strict in one change | Needs the gitignored UT99 substrate plus a live capture environment; the UED22 `GObjNames`/`GObjObjects` dump would also need a UT99 equivalent |
| **E. Leave the compiler in `old/`, call it done** | Zero cost; the Python compiler still runs via `old/` | The rewrite spec eliminates Python entirely, so this is a scope change, not a plan |

## Proposal (owner's call — not decided)

Sequence B then D, and do not touch the front end until both land. Concretely: port `bytecode.py` +
`ordering.py` + `crc.py` (678 LOC together, the three pieces with the strongest evidence and the
cleanest contracts) into the Rust tree as standalone crates with the existing goldens re-used as
`cargo` fixtures; make that the single canonical `msvc_qsort` so `native/saveorder.py`'s copy retires
with it. Then run `extract_ename.py` against UT99's `core.dll` and re-measure the UT99 corpus
strictly — it is the one change that could plausibly move ~19 packages from `perm_gate` to `gate` and
would tell the owner whether the 30-package bar is reachable before the parser/lowering port is
costed.

Separately, worth deciding explicitly: the rewrite spec scopes the compiler in by silence. 11k LOC of
product + ~1.1k LOC of test oracles, with a stated bar (byte-identity vs a closed binary) stricter
than anything else in the rewrite, deserves its own line in the spec and its own parity statement.

## Open questions / what to verify next

- Does `FName::FName` reuse freed indices from the `Available` list during a UCC compile? Reading
  `AllocateNameEntry`'s `Index` argument settles `ExtendedBuilders`. Everything else is eliminated.
- Does extracting UT99's own name pool actually convert the ~19 UT99 perm-only packages to strict, or
  is there a second UT99-specific cause behind it?
- Is `autonomous-struct-class-compile-diverges-from` (p2) stale? Both findings look fixed; confirm
  and close rather than schedule.
- The campaign's "247/285 passed" figures were not re-run here (no venv in this worktree). Static
  count is 203 test functions; the expanded count should be confirmed before it is quoted.
- `natives._WIDEN` is an invented widening order standing in for UCC's real `ConversionCost`. It has
  not failed on the corpus; it is not RE'd. Does any corpus package actually discriminate them?
- Are the two `texture_import.py` tie-break formulas (mip quantization favouring the lower palette
  index; the exact-`.5` `MipZero` tie) ever exercised? `UscTexAsym4x4` was chosen specifically to
  avoid them.
- Is there a licence-clean, UE1-covering grammar or opcode table the rewrite can validate its parser
  against, rather than only against UCC's own output? (See Findings 11–12.)

## Sources

<!--EXTERNAL-SOURCES-->

In-repo (all verified by reading in this worktree):

- `old/USCRIPT-COMPILER.md` (760 lines) — the campaign's single source of truth: goal, substrates,
  gates, per-package pass table, RE findings, open items.
- `old/dev/docs/unrealed/unrealscript/` — `compile-model.md` (343), `u-format.md` (91), `bytecode.md`
  (59), `toolchain.md` (48), `parity.md` (36), `README.md` (27). The RE facts.
- `old/dev/docs/board/to-build/uedcli-unrealscript-compiler/` — `spec.md` (91), `overview.md` (29),
  and two parked questions: `name-table-order-exclusion.md` (the proposed exclusion the owner
  refused) and `substrate-premise-was-wrong.md` (why the compiler is Python, not Rust).
- `old/dev/docs/board/to-build/uscript-algorithm-fidelity/` — `findings-ordering-re.md` (735 lines,
  the ordering RE log) and `harness/` (675 LOC, 5 scripts + `ename_ued22.json`).
- `old/uedcli/uscript/` (22 files, 11,043 LOC), `old/uedcli/cli/{parsers,commands}/uscript.py`,
  `old/uedcli/upackage.py`, `old/uedcli/uprops/`.
- `old/dev/docs/board/inbox/` — 18 uscript-related items (Finding 9).
- `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md` — scopes `uedcli/` in, `uned/` out,
  never names the compiler.
- Sibling notes, not duplicated here: `dev/research/ue1-package-format-prior-art.md` (the decoder-side
  prior-art and licence table), `dev/research/port-order-and-cost-model.md` (uscript LOC/test ratios).

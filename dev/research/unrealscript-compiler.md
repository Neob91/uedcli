# The UnrealScript compiler — purpose, fidelity target, and prior art

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** Why does uedcli contain its own UnrealScript compiler, how close is it to the
byte-parity bar it set itself, and what prior art exists for the Rust rewrite?

## Summary

- **The motive is an editor-free pipeline, not compilation itself.** `UCC.exe` is a closed Win32
  binary needing wine-in-docker, a substrate laid out its way, `EditPackages=` injected *inside*
  `[Editor.EditorEngine]` (it rewrites the ini), and textual success detection. uedcli's compiler is
  the one path that compiles `.uc` with no docker, wine, or editor.
- **The bar is byte-identity.** Owner ruling 2026-09-05: reproduce UCC's algorithm, never fit a
  table; finish line 30 real packages; exclusions exactly two per-compile-random fields (the package
  GUID, a `UTexture`'s `InternalTime[2]`).
- **Proven strict-byte-exact: 4 real packages**, all UED22, all single-class, plus controlled
  fixtures and the DXORIG conversation proof. **~24 further real packages pass only `perm_gate`**,
  which tolerates table order and FName case — an open item, not a pass. So 4/30 at the stated bar.
- **Two residual causes, both ordering.** Every UT99 package fails strict on one known gap: UT99's
  own name pool was never extracted (`ENGINE_NAME_POOL`/`HIGHLIGHT_NAME_POOL` are
  UED22-`core.dll`-specific). `ExtendedBuilders` (UED22) fails on a name-table `qsort`-tie residual
  narrowed, after three disassembly passes and two live captures, to one unverified assumption —
  whether `FName` slot indices are ever reused.
- **The bytecode codec is the one unambiguously proven claim:** `bytecode.py` round-trips **all
  3,581** `UFunction`/`UState` scripts across all 32 stock UED22 packages byte-exact. **`ordering.py`
  is the crux**: bodies reference names and objects *by table index*, so a permuted table changes
  every body's bytes.
- **`reference{,_ut99,_dxorig}.py` are not corpora** — three UCC *driver* modules, one per substrate,
  minting goldens in a wine container. Test-only, like `gate.py`: ~1,090 LOC is oracle, not product.
- **`uscript compile` is the sole leaf verb**, nothing else in uedcli consumes a compiled `.u`, and
  the Rust rewrite spec **never mentions the compiler** — 11k LOC in scope by silence, uncosted.
- **No independent UE1 UnrealScript compiler is reachable anywhere.** The opcode set *is* public (in
  Epic's shipped headers); the compiler is not, and every community tool shells out to `UCC`
  (Findings 10–13).

## What we have today

`old/uedcli/uscript/` — 22 files, **11,043 LOC**. Tests: 26 `test_uscript_*.py` files, **4,201 LOC**,
**203 test functions** (several parametrized over package lists, so the campaign's "247/285 passed"
claims are expanded counts; not re-run here). Goldens: **77 committed `.u`** and **63 `.uc`** under
`old/uedcli/tests/fixtures/uscript/` — 37 top-level, 6 `realpkg/` and 34 `ut99/` package dirs.

| File | LOC | Purpose |
|---|---|---|
| `compile.py` | 3,299 | Declarations → object graph: class header/flags, vars, enums, structs, consts, `defaultproperties` diffing, imports, `#exec` wiring, multi-class two-pass signature graph |
| `lower.py` | 1,692 | AST → `Tok` bytecode stream with type inference, operator/native resolution, flat jump patching |
| `parser.py` | 1,078 | Recursive-descent parser for the full UED22 grammar → `ClassDecl` |
| `conimport.py` | 703 | `#exec CONVERSATION IMPORT`: `.con` binary parser + `ConSys` object graph → sibling `<Pkg>Text.u`/`<Pkg>Audio*.u` |
| `natives.py` | 627 | Operator/native catalog; reads `iNative`/`FunctionFlags` out of compiled `.u` |
| `gate.py` | 545 | Parity gate: strict `gate()` (masked byte compare) + `perm_gate()` (identity/permutation), with structural first-divergence diagnostics |
| `reorder.py`, `ordering.py` | 696 | Re-derive the true table order by decoding an already-emitted package's own `<<FName`/`<<UObject` streams, then reproduce `SavePackage`'s gather + instruction-exact MSVC CRT `qsort` |
| `bytecode.py` | 332 | Byte-exact `EExprToken` decode/encode with the dual on-disk/in-memory cursor |
| `lexer.py`, `env.py`, `model.py`, `ast.py`, `tokens.py`, `texture_import.py`, `serialize.py` | 1,341 | Front-end plumbing (token stream with keywords left contextual, the dependency symbol environment over the `.u` search path, the fully-linked `CompiledPackage` contract, AST nodes incl. `ClassDecl.decl_order`) plus `#exec TEXTURE IMPORT` PCX decode and the mechanical `CompiledPackage` → `.u` encode |
| `reference{,_ut99,_dxorig}.py` | 545 | Drive the UED22 / UT99 / original-Ion-Storm `UCC.exe` in containers; `reference.py` also wraps `batchexport` |
| `global_index.py`, `crc.py`, `__init__.py` | 185 | Runtime-dumped `GObjNames`/`GObjObjects` order + the two name-flag pools; `appStrCrc` (CRC-32/BZIP2 over UTF-16LE `ScriptText`) |

Plus `uscript/data/gobjnames_ued22.json` (93 KB) + `gobjobjects_ued22.json` (437 KB) — the dumped
engine global index, UED22 only.

## Findings

### 1. Why not just use `UCC`?

`old/USCRIPT-COMPILER.md` never states the motive in one line; this is assembled from `toolchain.md`,
`reference*.py` and the CLI help. `UCC.exe` works, and uedcli uses it — as the golden. What it cannot
be is part of a pipeline:

| UCC constraint | Source | What an editor-free pipeline needs |
|---|---|---|
| Win32 binary; runs only under wine in a docker container (`ephemeral_build_container`) | `reference.py` | A native binary, no container, no wine |
| Sources must sit at `<GameRoot>/<Pkg>/Classes/*.uc`, output lands in `System/`; `EditPackages=<Pkg>` must go **inside** `[Editor.EditorEngine]` (at EOF it is silently skipped) and `make` then **rewrites the ini** | `toolchain.md`, `stub.inject_edit_package` | Compile a directory in place to a chosen `-o` path, with no mutable global config |
| Success detection is textual: exit 0 **and** `Success - 0 error(s)` **and** output > 64 bytes (a 64-byte `.u` is a failed compile that exits 0); `make` also rebuilds by timestamp and cascades into later `EditPackages` entries | `toolchain.md` | A real exit code and deterministic single-package compilation; `uscript compile` exits 2 naming the construct |
| Each engine build is its own substrate: UED22, UT99 and DXORIG `UCC.exe` produce different bytes and cannot cross-compile; OldUnreal's rebuilt `Editor.dll` also **removed** the `#exec CONVERSATION IMPORT` handler (silent no-op) | `USCRIPT-COMPILER.md`, `reference_dxorig.py` | One compiler parameterised by a `--deps` search path, with a capability no current UCC build has in one place |

The conversation row is the strongest standalone argument: that importer exists in no maintained
toolchain, and `conimport.py` (703 LOC) reimplements it — the one thing uedcli's compiler does that
no available `UCC` can.

### 2. Implementation shape and pipeline

Verified pipeline (module docstrings + `cli/commands/uscript.py`):

```
*.uc ─ lexer.py ─► tokens ─ parser.py ─► ClassDecl (ast.py, decl_order preserved)
     env.py (upackage/uprops read .u deps: supers, iNative, CRCs, types)
  ─► compile.py  pass 1 _prepass_signatures (every class's ClassSig)
                 pass 2 per class: declarations + defaults + #exec
                   ├─ lower.py/natives.py → Tok stream → bytecode.py encode
                   └─ texture_import.py (PCX), conimport.py (.con siblings)
  ─► serialize.py → provisional .u ─► reorder.py (decode own bodies → ref streams)
     + ordering.py (gather + msvc_qsort) ─► serialize.py again, true order → .u
```

Two things about this shape are unusual. **It serializes twice:** table order is not computed from the
AST but re-derived by *decoding the package the compiler just wrote* (`reorder.py`), then re-emitted.
Three of the ordering bugs the campaign fixed were this detour — true declaration order cannot be
recovered from compiled bytes, because the `Children` chain bins properties and non-properties into
separate sub-chains and loses their interleaving; the fix threaded `ast.ClassDecl.decl_order` back in,
partially bypassing the decode path. **And the hot path is quadratic:** `compile_package_dir`
re-finalizes and re-serializes the whole package per class, discarding `ClassGraph` memoization.

**Refusal discipline is real and worth preserving:** 100 explicit `raise` sites (`compile.py` 51,
`lower.py` 37, `texture_import.py` 10, `conimport.py` 1, `serialize.py` 1), each naming the
construct, with `cli/commands/uscript.py` mapping every one onto exit 2 rather than a traceback.

### 3. Language-feature coverage

Supported = lowers/compiles; all rows **verified in-repo**, not claims about the engine.

| Feature | Supported | Evidence |
|---|---|---|
| Class header + `extends`/`expands`; modifiers `abstract native intrinsic transient safereplace noexport perobjectconfig nativereplication` | yes | `_build_class`, `_CLASS_MODIFIER_FLAGS`; any other modifier raises. A base class with no super raises (`"later rung"`) |
| Scalar `var` (all types), static arrays, object/class/struct/enum-typed vars; `const`, `enum`, `struct` incl. non-scalar members | yes | `_resolve_var_type`, `_VAR_MODIFIER_FLAGS`, member builders |
| Dynamic arrays (`array<T>`) | partial | declarable; unknown element type raises a named `LowerError` |
| `struct X extends Y`; dynamic-array struct member; explicit struct/array defaults | **no** | four named `NotImplementedError`s |
| `defaultproperties` (own + inherited-override diff) | yes | `_super_field_order`, `_auto_emit_defaults` |
| `function`, `event`; modifiers `final singular native simulated static`; params `optional out coerce` | yes | `compile.py:740` accepts only these two kinds; `_FUNC_`/`_PARAM_MODIFIER_FLAGS`, others raise |
| `operator`/`preoperator`/`postoperator`/`delegate` **declarations**; array params/locals | **no** | parsed (`_FUNC_KW`), then `"function kind … not supported yet"`; `"array param/local …"` |
| `if`/`while`/`for`/`switch`/`return`/`break`/`continue`/`goto`/labels/`assert`/`stop`/locals/assignment/expression statements | yes | `lower._st_*` (16 handlers) — but **`do … until` is not**: the parser emits `Stmt(kind="do")` and `lower` has no handler, so it raises |
| `foreach` + `EX_Iterator`/`IteratorNext`/`IteratorPop` | yes | `lower._st_foreach`, `foreach_depth` |
| `state { Label: … }` + label table + `EX_Nothing` padding | yes | `_build_one_state`, `compile-model.md` |
| `state X extends Y`, `ignores`, state function overrides, `IgnoreMask`; `replication { … }`; `cpptext` | **no** | three named `LowerError`s (`IgnoreMask` is tied to `ignores`); the rest parsed then `_reject_unsupported` |
| Native classes (`RF_Native`, `CLASS_Inherit`, transitive `PackageImports`); `ProbeMask` (inheritance-accumulating `EProbe` bits); cyclic same-package class refs | yes | `compile-model.md`; `_EPROBE_TABLE`/`_probe_bits`; `_prepass_signatures` |
| Operator overload resolution by operand type; constant folding into operator param types | yes / partial | `natives.Catalog`, but `_WIDEN` is **invented**, not UCC's `ConversionCost`; the expected type is threaded through assign/return/`for` and **not** through function-argument position |
| `#exec TEXTURE IMPORT` (PCX) | yes, 1 per class | `texture_import.py`; two tie-break formulas are declared judgment calls |
| `#exec CONVERSATION IMPORT` | 16 of 19 event types | `conimport.py`; multiple imports per package raise. `MESH`/`AUDIO`/`SOUND`/`FONT IMPORT` all raise — owner scoped out 2026-09-05 |

### 4. The fidelity target, and what is actually proven

The oracle is **a fresh `UCC.exe` compile of the exact same `.uc` sources**, never a shipped retail
`.u` (those are editor-serialized: own zero-valued defaults dropped, `None`-holes accreted from GUI
resaves). The comparison is raw bytes. Two gates, in `gate.py`: `gate()` is **strict**, byte-for-byte
with only the GUID and `InternalTime[2]` masked (two clean UCC compiles of identical source differ in
exactly those regions); `perm_gate()` additionally tolerates name/import/export **table order** and
FName **case**, and since the owner ruled order must be reproduced rather than excluded it is
explicitly a **diagnostic stepping-stone**. Both also compare each export's canonicalised `Super` and
`ObjectFlags`, added after an adversarial review found `perm_gate` missed them and masked a real bug
(overrides emitted `Super=0`).

**Proven, unambiguously:** all **3,581** `UFunction`/`UState` scripts across all 32 stock UED22
packages decode and re-encode byte-exact (`test_uscript_bytecode.py`). Because `Tok` parts are
index-independent, lowered tokens compare equal to UCC-decoded tokens iff they encode identically —
a clean lowering oracle. **Strict gate, real packages: 4** (all UED22, one class each), plus
`ConvTest` (DXORIG) and the controlled fixtures. **`perm_gate`-exact but strict-failing: ~24 real
packages** (`ExtendedBuilders`; `Fire`, `UWeb`, `IpServer`, `UTServerAdmin`, ~19 community UT99
mutators). So 28/30 at the permutation level, **4/30 at the stated bar**.

The verification harness (675 LOC) is genuinely non-circular: `extract_ename.py` disassembles
`core.dll`'s `RegisterNames` `push` sequence for a substrate's intrinsic `EName` order (a computation
over the binary, not a baked list); `dump_gobj.py` plants a winedbg INT3 at `SavePackage` and dumps
live `GObjNames`/`GObjObjects`; `dump_name_creation_order.py` breaks on every `AllocateNameEntry`
call during a real compile; `reproduce_from_dump.py` then checks the dump reproduces every fixture's
order, golden bodies supplying the counts and golden tables the expected output. The campaign log's
honesty is an asset too: a fitted `OBJECT_ORDER`/`NAME_ORDER` table caught by review and **deleted**,
and a `>` → `>=` qsort tweak identified as curve-fitting and **not applied**.

### 5. `ordering.py` — what has to be ordered, and why

**What:** all three package tables — names, imports, exports. **Why it is not cosmetic:** object
bodies reference names and objects *by table index*, so permuting the name table shifts every
name-index byte inside every body; byte parity is impossible without reproducing order exactly.
**The mechanism** (RE'd from `uned/UED22/core.dll`, ImageBase `0x10000000`):
`UObject::SavePackage` @`0x277c0` gathers each table, then sorts it with `appQsort` @`0x315c0` — a
thunk to the MSVC CRT `qsort` @`0x77cb0` — **descending by an integer reference count**. Names sort
on `NameIndices[globalNameIndex]`, tie-broken by global `FName` registration order; imports and
exports on `ObjectIndices[obj]`, tie-broken by global `GObjObjects` creation order and by the
package's own object parse order respectively. The keys come from the tagging pass
`FArchiveSaveTagImports`: `operator<<(FName)` @`0x162e0` does `NameIndices[name]++`;
`operator<<(UObject)` @`0x161c0` does `ObjectIndices[obj]++` and recurses into an import's Outer
chain (why `Core` sorts first among imports). Both arrays are `AddZeroed` in the linker ctor, so the
key is a pure reference count.

**Three facts make this hard, and are why `ordering.py` is 319 LOC of ported `qsort`:**

1. **The CRT `qsort` is unstable**, so count-tied entries are permuted deterministically but
   non-obviously, and that permutation is part of the output. `msvc_qsort` ports the modern MSVC
   algorithm (`__shortsort` selection for runs ≤ 8, else median-of-3 kept in place with a Hoare
   partition skipping the equal-key run), re-verified instruction-exact **three times**.
2. **The gather order is a boot+load artifact**: the engine's live global `FName`/`GObjObjects` index
   after booting and loading dependencies, not derivable from the source under compilation. Hence
   the runtime dump, shipped as per-substrate JSON — **UED22 only**, precisely why every UT99
   package fails strict.
3. **The gather interleaves by true source-textual declaration order**, which the compiled `.u`
   cannot express. Three successive bugs were this shape: enum-vs-property interleaving; a function's
   locals registering inline rather than deferred; and, across a class boundary, a multi-class
   package's per-class `defaultproperties` value names. Two extra rules: a package self-reference
   registers at class-header time; a `defaultproperties` name-typed *value* registers last.

**The open residual, precisely.** `ExtendedBuilders`'s name table diverges in 16 entries, and
everything cheap is eliminated by measurement: the `qsort` port is instruction-exact; the decoded
gather arrays and refcounts are byte-identical to golden's across all 84 names; a live capture
confirms the second diverging region's relative registration order; and feeding golden's own bytes
back through `order_package` reproduces the identical divergence — so the bug is in the *input
array*, not the sort. One surviving hypothesis: `FName::FName` pops from an `Available` free-list
before appending, so an index may be **reused**, making `by_name_index`'s sentinel wrong — and the
capture reads `AllocateNameEntry`'s `Name` argument, never its `Index`, so it cannot see that.

### 6. The three `reference*.py` modules are drivers, not corpora

They are **UCC driver modules, one per engine substrate** — how goldens get minted, not stored
sources. Each stands up an ephemeral wine container, stages `.uc` sources, injects `EditPackages`,
runs `wine UCC.exe make`, and reads the `.u` back out; `reference.py` also wraps `ucc batchexport`,
the decompiler that seeds the corpus from a real `.u`. Three modules because the substrates are
mutually incompatible: `uned/UED22` (committed; OldUnreal-patched DX engine, package v69, primary),
`uned/UT99` (gitignored; its `Core.u` and native indices differ, so UED22's UCC *cannot* compile UT99
packages), `uned/DXORIG` (gitignored; the only build that still has the conversation handler).

**Reachability (verified):** importers are `test_uscript_*.py` plus the board harness; **no shipping
module imports them** — the sibling finding is confirmed, and extends to `gate.py`. Correct by
design, but ~1,090 LOC of `uscript/` is therefore **test infrastructure**, not product.

### 7. Dependency resolution, and what it compiles against

`env.InstallEnv(search_dirs)` resolves symbols against **already-compiled `.u` packages** on a search
path, using the byte-exact read side: `old/uedcli/upackage.py` (328 LOC) and `old/uedcli/uprops/`
(1,782 LOC). `bytecode.py` extends `uprops.ufield._walk_expr` from a read-only skip walker into a
full decode/encode — the compiler sits directly on the decoder. It reads a dependency's home package,
super chain, stored `ScriptText` CRC (an import's CRC is **read from its home package, never
recomputed**), member/param types, struct members, and each callee's `iNative`/`FunctionFlags`.

**Required minimum:** `core.u` and `Engine.u` in the **first** search dir; the CLI puts the UED22
substrate first when installed, else requires a `--deps` dir holding both, and none at all exits 2.
Beyond that, discovery is transitive: `_extra_super_packages` fixed-point-walks newly-discovered
classes' member types (the fix that made `Botpack`-dependent mutators compile), and
`env.class_home_from_imports`/`import_only_class_package` resolve a class with no `.uc` source
anywhere by scanning another package's **import** table. Corpus reality: `native noexport` classes
(`ConSys`, most of DeusEx) don't round-trip even under UCC, so reaching 30 needed community UT99
mutators.

### 8. What consumes the output, and CLI reachability

**`uscript compile` is the only leaf verb** — one family, one subparser, five arguments (positional
`SRC-DIR`, `-o/--out`, `--package`, `--deps` repeatable, `--json`); `dispatch.py:115` routes
`uscript` and `run()` raises `CommandError` for any other sub-verb. **Nothing consumes the output:**
every importer of `compile_package_dir`/`uscript.serialize` outside `uscript/` is the CLI command
module or a test, and the only in-repo consumer of its *bytes* is `gate.py`. So 11,043 LOC reachable
through one verb whose output no other uedcli feature reads — not an argument against the compiler
(the consumer is the engine), but no internal dependency forces the rewrite's ordering here.

### 9. Known live defects

From `old/dev/docs/board/inbox/`; priorities are the items' own.

| Item | Pri | What is wrong |
|---|---|---|
| `uscript-path-to-30-packages` | p1 | The campaign's own gap list: `replication`, `#exec` asset imports, expected-type-directed operator overloads, and the corpus itself. `extendedbuilders-name-table-qsort-residual` (p3) is the one real ordering blocker on UED22 — Finding 5, narrowed to the `FName` index-reuse question |
| `uscript-compile-package-dir-is-o-n-2-in-classes`, `uscript-pre-merge-hardening` | p2 | Re-finalizing and re-serializing the whole package per class is O(N²) on exactly the growth axis the 30-package goal needs. Hardening: the flag maps (`_CLASS_/_VAR_/_FUNC_MODIFIER_FLAGS`, `CPF_EDIT`) are RE'd but only `event`/`final`/`input` are pinned by a golden; latent `Super=0` for a struct/state that `extends`; array/enum/struct default emission load-tested, not byte-parity'd |
| `uscript-bare-function-call-name-treated-as` | p4 | The class-discovery pre-pass treats **every** bare-name call's callee as a candidate class, relying on `env.resolve_class` returning `None` to no-op. A function whose name legally coincides with a class name (separate namespaces) would pull that class's transitive `package_imports` into the discovery frontier. Not traced to whether bytes change |
| `uscript-two-hand-rolled-lexical-scanners`, `uscript-import-only-class-fallback-could` | p4 | `compile._skip_defaultproperties_block` and `_mask_lexical_noise` each re-derive comment/string/name-literal rules `lexer._Lexer` already implements (correct today, but a lexer-rule fix would need hand-replicating in three places; blocked on `Token` carrying line/col, not offsets). And `env._import_only_class_to_package` `setdefault`s the **first** package found for a casefolded class name with no ambiguity check — probably safe, unproven, contrary to the repo's no-silent-fallback rule |
| `autonomous-struct-class-compile-diverges-from` | p2 | **Appears stale.** Both claims (the `Struct` name missing `RF_HighlightName`; struct members not `next_field`-chained) now look fixed — `HIGHLIGHT_NAME_POOL` contains `struct`/`enum`/`const`/`state`, and `compile.py:2029` chains `s.member_keys`. The `_STRUCTURAL_NAMES` set it names no longer exists. Verify and close rather than schedule. Likewise `uscript-name-table-member-fname-order` (p2), superseded by the runtime dump with its "by property type" hypothesis disproven |
| 8 further items | p2–p3 | The constant-fold rule unverified in function-argument position (the `_NESTED` sentinel's hole); perf (`resolve_class` memoization, three quadratic hot spots); five narrower struct/enum/type-resolution and rounding investigations; one corpus package blocked on a missing PCX |

Cross-campaign: `old/uedcli/native/saveorder.py` (the map-parity path) carries **its own copy** of the
CRT `qsort`, possibly the mis-ported classic variant this campaign initially suspected.

### 10. UE1 bytecode and the VM — external documentation

The key correction to the usual assumption: **the opcode set is not secret**. Epic's shipped UE1
public source carries the complete `EExprToken` enum verbatim in `Core/Inc/UnStack.h` ("Copyright
1997-1999 Epic Games", "Created by Tim Sweeney"): `EX_LocalVariable=0x00` through
`EX_GlobalFunction=0x38`, the conversion range `EX_MinConversion=0x39 … EX_MaxConversion=0x60`, then
`EX_ExtendedNative=0x60`, `EX_FirstNative=0x70`, `EX_Max=0x1000`. `Core/Inc/UnClass.h` gives the
layouts: `UStruct { UTextBuffer* ScriptText; TArray<BYTE> Script; INT TextPos; INT Line; }`,
`UFunction { _WORD iNative; BYTE OperPrecedence; }`, `UState { QWORD ProbeMask; _WORD
LabelTableOffset; }`, plus `FLabelEntry` and its `operator<<`. *Verified by fetch.*

**This independently corroborates four of uedcli's RE conclusions**, each derived from disassembly
and corpus measurement rather than the headers: native dispatch (`EX_FirstNative=0x70`,
`EX_ExtendedNative=0x60` ↔ uedcli's `0x70–0xFF` single-byte and `((op-0x60)<<8)|next` extended form);
the measured conversion opcodes `0x43`/`0x44`/`0x4A`/`0x4B`/`0x4C` all inside the conversion range;
the `UFunction` tail order `iNative u16`, `OperPrecedence u8`, `FunctionFlags u32`; and the `UState`
tail `ProbeMask, IgnoreMask, LabelTableOffset, StateFlags`. The one finding the headers do **not**
explain is the `EX_Nothing` padding count before a label table —
`FLabelEntry` is declared, but the emitter lives in the unshipped `Core/Src`. Two caveats: the UT99
public-source README forbids commercial exploitation, so these headers are **read-for-facts only**,
never a source to copy into an MIT tree; and OldUnreal 227's `UnStack.h` fork adds non-stock opcodes
(`EX_MapKeyElement`, `EX_RefIsValid=0x0191`, …) — not stock UE1.

What is *not* public is the compiler: Epic shipped `Core/Inc` and `Core/Lib` but **no `Core/Src`**, so
`SerializeExpr` is declared and never defined publicly. Sweeney's original *UnrealScript Language
Reference* says so outright — *"at this time, there are no plans to document the Unreal VM to the
extent necessary for others to create independent but compatible implementations"* — though it does
confirm the two-pass structure uedcli's spec assumes and that `native(266)` is the C++
`AUTOREGISTER_NATIVE` index. Coverage is thinnest where it matters most: **the BeyondUnreal wiki has
no UE1 bytecode page at all** (`UnrealScript_bytecode` redlinks), its UE1 material being
container-level only. So uedcli's `compile-model.md` — ordering, flags, CRC, `ProbeMask`, label-table
padding, `Dependency` rules — is a **primary source with no public prior write-up reachable from
here**, not a restatement.

### 11. Tooling comparison

Compiler/grammar-relevant tools only (the decoder-side table lives in the sibling prior-art note);
all rows verified by fetch.

| Tool | Lang | Licence | UE1 coverage | Maintained | To us |
|---|---|---|---|---|---|
| `UCC` (Epic) + its public headers (`ut432pubsrc` and mirrors) | C++ | proprietary; pubsrc forbids commercial exploitation | native, authoritative; headers give `EExprToken` and the `UStruct`/`UFunction`/`UState` layouts | n/a | **Oracle only, and cite-for-facts only.** Ships `Core/Inc`+`Core/Lib`, no `Core/Src` — no compiler source exists publicly. Keep out of the implementation's provenance |
| UELib (`Eliot.UELib`) | C# | **MIT** | UE1/2/3, incl. Deus Ex | active (2026-08) | Best *decompiler* reference, MIT-safe. **Read-only for bytecode**: `ByteCodeDecompiler` has `Deserialize()` and no serializer; write-support requests (#27, #98) closed unimplemented. Only the name/import/export tables have round-trip write tests |
| UnrealScript Language Service (EliotVU) | **TypeScript**, ANTLR4 (`grammars/UCParser.g4`) | **MIT** | `UCGeneration = Auto\|1\|2\|3` — **UE1 is a supported generation** | last commit 2025-10-10 | **The one usable grammar-coverage comparison**: a declarative ANTLR4 grammar to diff uedcli's hand-written `parser.py` against. Emits no bytecode. (UE Explorer, the GPL-3.0 C# GUI over UELib, is oracle-only) |
| `DarklightGames/UnrealScriptPlus` | **Rust** (`pest`) | **MIT** | UE2-targeted | 2026-01, 5★ | The only Rust UnrealScript parser reachable, and its README calls it "very early stages": reference, not a dependency. Sibling `upio` (Rust, GPL-3.0) is copyleft. Every other Rust `unreal*` crate (`unreal_asset`, `uasset`, `unreal_pak`) is UE4/5, and `crates.io?q=unrealscript` returns one unrelated hit |
| `shrimpza/unreal-package-lib`, `unreal-archive` | Java | MIT / Unlicense | UE1/2/3 containers; corpus indexer | active (2026-08/09) | Container-level only — the README is explicit: *"no support for reading or extraction of data such as UnrealScript classes"* |

### 12. Has anyone written an independent UE1 UnrealScript compiler?

**No reachable evidence of one.** Repo search for `unrealscript compiler` returns four hits, all UCC
wrappers or shell scripts; `ucc-rs` is an unrelated OpenSHMEM binding; `openunreal` is all UE4/5;
code search for `EX_LetBool` across Rust/Python/TypeScript returns only UE4/5 Kismet/Blueprint tools,
never UE1. OldUnreal publishes renderers, localization and UnrealScript, but no compiler. The
strongest counter-signal is what the most active UE1 *build* tool does instead: Deus Ex Randomizer's
"UnrealScript Injector" is a **source-level** preprocessor/merger that shells out to the real binary
— `compiler/compiler.py`'s header says it *"calls the other modules and runs the UCC make
compiler"*, invoking `[System/UCC.exe, 'make', '-h', '-NoBind', '-Silent']` (AGPL-3.0, active
2026-09). The strangler pattern, community-validated — and the one thing this campaign refuses.

So uedcli's compiler appears to be **the only independent UnrealScript→UE1-bytecode compiler
reachable from here**, and the only project attempting byte parity with `UCC`. Nobody reports what is
hard because nobody reachable has tried. *Confidence: absence of evidence over a thorough search,
not a proof.*

### 13. What makes one compiler's output byte-identical to another's

The reproducible-builds catalogue maps cleanly onto what this campaign hit: stable order for inputs,
stable order for outputs, randomness, value initialization, locale-dependent sorting. Hash-iteration
order is called out explicitly — Python/Rust/Perl/Ruby hash orders vary per run by design, and the
documented fixes are an explicit `sort` or a `BTreeMap` rather than a `HashMap`. That is a direct
constraint on a Rust port of `ordering.py`/`reorder.py`: every container feeding the gather must be
ordered by construction. Epic independently documents the one exclusion uedcli granted itself —
*"In UnrealEd, each time a package file is saved, it is assigned a new GUID"* — so the GUID mask is
externally corroborated, not merely locally convenient. The converse risk the headers imply:
`UStruct` serializes `Line`/`TextPos` and `UClass` carries `ScriptTextCRC`, so **whitespace drift in
the `.uc` input changes the output bytes**, which is why the campaign's `_script_text` /
`_skip_defaultproperties_block` work was load-bearing rather than cosmetic.

The matching-decompilation scene reached the opposite conclusion, the most useful external data point
here. `zeldaret/oot` md5-checks its build against the original ROM and gets there by **resurrecting
the original compiler binaries** (IDO 5.3/7.1 via static recompilation of the IRIX toolchain, plus a
patched EGCS 1.1.2) rather than reimplementing them — to the point of documenting a *workaround* for
an original-compiler bug, because fixing it would break the match. Byte-identity against a closed
compiler is normally achieved by running the original; projects that reimplement instead pay in
exactly the places uedcli is paying.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Port bytecode codec + ordering first, as standalone Rust crates** | These are the two proven, self-contained, heavily-tested pieces (3,581-script round-trip; instruction-exact `qsort`). They have clean inputs/outputs and no editor dependency. One canonical `qsort` also retires the `saveorder.py` duplicate-port risk | Doesn't deliver a usable verb until the front end follows; risks a long half-ported state |
| **B. Declare `perm_gate` the shipped bar and strict parity a stretch goal** | 28/30 real packages already pass it; the remaining strict failures are all table *order*, functionally inert to the engine. Would let the rewrite ship a working compiler without re-doing the live-capture RE | Directly contradicts the owner's 2026-09-05 ruling, which retired exactly this exclusion. Owner's call only |
| **C. Extract the UT99 name pool, then re-measure** | One known cause explains **every** UT99 strict failure; `extract_ename.py` already does this per-substrate from `core.dll`. Plausibly converts ~19 perm-only packages to strict in one change | Needs the gitignored UT99 substrate plus a live-capture environment; the `GObjNames`/`GObjObjects` dump would also need a UT99 equivalent |

## Proposal (owner's call — not decided)

Sequence A then C, leaving the front end alone until both land. Port `bytecode.py` + `ordering.py` +
`crc.py` (678 LOC together — strongest evidence, cleanest contracts) into the Rust tree as standalone
crates reusing the existing goldens as `cargo` fixtures, and make that the single canonical
`msvc_qsort` so `native/saveorder.py`'s copy retires with it. Then run `extract_ename.py` against
UT99's `core.dll` and re-measure the UT99 corpus strictly — the one change that could move ~19
packages from `perm_gate` to `gate`, and that would say whether the 30-package bar is reachable
before the parser/lowering port is costed. Separately: the rewrite spec scopes the compiler in by
silence, and 11k LOC of product plus ~1.1k LOC of test oracles, with a bar stricter than anything
else in the rewrite, deserves its own line in the spec and its own parity statement.

## Open questions / what to verify next

- Does `FName::FName` reuse freed indices from the `Available` list during a UCC compile? Reading
  `AllocateNameEntry`'s `Index` argument settles `ExtendedBuilders`; everything else is eliminated.
- Does extracting UT99's own name pool actually convert the ~19 UT99 perm-only packages to strict, or
  is a second UT99-specific cause hiding behind it? And are the two p2 board items that look
  superseded (`autonomous-struct-class-compile-diverges-from`,
  `uscript-name-table-member-fname-order`) in fact closable?
- The campaign's "247/285 passed" figures were not re-run here (no venv in this worktree). Static
  count is 203 test functions; confirm the expanded count before quoting it.
- `natives._WIDEN` is an invented widening order standing in for UCC's `ConversionCost`; it has not
  failed on the corpus and is not RE'd. Does any corpus package discriminate them? Same question for
  `texture_import.py`'s two declared tie-break judgment calls, which `UscTexAsym4x4` avoids.
- Can the rewrite validate its parser against the licence-clean UE1-covering ANTLR4 grammar in
  Finding 11, rather than only against UCC's own output?

## Sources

External — fetched 2026-10-03. `wiki.beyondunreal.com`, `docs.unrealengine.com/udk` and `decomp.me`
403 automated fetches; the wiki was read via Wayback instead.

- `github.com/wrstone/ut432pubsrc` — Epic's UE1 public source (proprietary, no commercial
  exploitation): `Core/Inc/UnStack.h` (full stock `EExprToken` with hex), `Core/Inc/UnClass.h`
  (`UStruct`/`UFunction`/`UState` layouts, `FLabelEntry`); `Core/Src` is **not** in the release.
  Mirrors: `FaultyRAM/Ut99PubSrc`, `SWRC-Modding/CT`, `onnoj/DeusExEchelonRenderer` (DX copy).
  `github.com/OldUnreal/Unreal-PubSrc` `Core/Inc/UnStack.h` is 227's forked opcode set — use only to
  know which opcodes are *not* stock UE1.
- `github.com/EliotVU/Unreal-Library` — UELib (MIT): `src/ByteCodeDecompiler.cs` (native dispatch
  ranges), `src/Core/Classes/{UStruct,UFunction,UState}.cs` (wire format), `UDefaultProperty.cs`
  (UE1 tagged-default info byte: type nibble, `InfoSizeMask` 0x70, `InfoArrayIndexMask` 0x80).
  Bytecode read-only, no serializer; write-support issues #27/#98 closed unmet.
- `github.com/EliotVU/UnrealScript-Language-Service` — TypeScript/ANTLR4 LSP, MIT, `UCGeneration`
  includes UE1; `grammars/UCParser.g4` is the grammar to diff uedcli's `parser.py` against. Also
  `github.com/DarklightGames/UnrealScriptPlus` (Rust `pest`, MIT, UE2, early), `.../upio` (Rust,
  GPL-3.0), `github.com/shrimpza/unreal-package-lib` (Java, MIT, no UnrealScript),
  `github.com/unreal-archive/unreal-archive` (Java, Unlicense), and
  `crates.io/api/v1/crates?q=unrealscript` / `?q=unreal` — no UE1 Rust crate exists.
- `github.com/Die4Ever/unrealscript-injector` `compiler/compiler.py` — the most active UE1 build
  tool: a source-level preprocessor shelling out to `UCC.exe make` (AGPL-3.0).
- `web.archive.org/web/20080102113247/http://unreal.epicgames.com/UnrealScript.htm` — Sweeney's
  *UnrealScript Language Reference*: the "no plans to document the Unreal VM" statement, the two-pass
  compile model, `native(N)` indices, operators left undocumented. Also `…/Packages.htm` (new GUID
  per save), `…/CppObjects.htm` (the four package sections), and
  `…/wiki.beyondunreal.com/Legacy:Package_File_Format/Data_Details` (snapshot `20201023062426`) —
  the only UE1 wiki material, container level, no bytecode page.
- `reproducible-builds.org/docs/` + `/docs/stable-outputs/` (causes catalogue: hash-iteration order,
  locale-dependent sorting, `BTreeMap` over `HashMap`); `github.com/zeldaret/oot/blob/main/docs/
  compilers.md` (matching decompilation by resurrecting the original compiler binaries).

In-repo, all verified by reading in this worktree: `old/USCRIPT-COMPILER.md` (760 lines — the
campaign's source of truth); `old/dev/docs/unrealed/unrealscript/` (`compile-model.md` 343,
`u-format.md` 91, `bytecode.md` 59, `toolchain.md` 48, `parity.md` 36, `README.md` 27);
`old/dev/docs/board/to-build/uedcli-unrealscript-compiler/` (`spec.md`, `overview.md`, and the parked
questions `name-table-order-exclusion.md` and `substrate-premise-was-wrong.md`) and
`.../uscript-algorithm-fidelity/` (`findings-ordering-re.md` 735, `harness/` 675 LOC);
`old/uedcli/uscript/`, `old/uedcli/cli/{parsers,commands}/uscript.py`, `old/uedcli/upackage.py`,
`old/uedcli/uprops/`; `old/dev/docs/board/inbox/` (18 uscript items);
`old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md`. Siblings, not duplicated here:
`dev/research/ue1-package-format-prior-art.md`, `dev/research/port-order-and-cost-model.md`.

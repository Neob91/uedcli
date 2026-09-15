# UnrealScript compiler — byte parity with UED22 `UCC.exe`

This is the single source of truth for the uedcli UnrealScript compiler campaign: the goal, the
reference toolchains, the parity bar, the current status, and the crux RE findings. Read this before
doing any uscript-compiler work so you don't re-derive it. Detailed RE facts live in
`dev/docs/unrealed/unrealscript/` (the sole home for that knowledge, per `CLAUDE.md`); process/board
state lives under `dev/docs/board/.../uedcli-unrealscript-compiler/` and
`dev/docs/board/.../uscript-algorithm-fidelity/`.

## Goal

`uedcli` compiles UnrealScript (`.uc`) into a `.u` package **byte-identical to what UED22's
`UCC.exe make` produces from the same sources** — not merely functionally equivalent. Owner ruling
(2026-09-05): "Strive for our algorithm to be on par with UCC's. Don't do hacks just to satisfy a
single package scenario." — i.e. reproduce UCC's real mechanism (ordering, flags, CRCs, bytecode),
never fit a table or special-case a package to make one test pass. Campaign target: 30 real
(stock + community) packages byte-exact vs UCC.

## The reference toolchains — three substrates

Never cross-compile a package with the wrong build's `UCC.exe` — different builds have different
`Core.u`/DLLs and produce different bytes. Each substrate is driven only by its own compiler.

| Substrate | What it is | Why it exists | Driver | Fetch |
|---|---|---|---|---|
| `uned/UED22` (committed) | OldUnreal-patched Deus Ex engine, package v69 | The default/primary substrate; most RE and the DeusEx brush-builder corpus | `uedcli/uscript/reference.py` | already in the repo |
| `uned/UT99` (gitignored) | Original UnrealTournament GOTY | A large corpus of stock + community pure-script packages; its own `Core.u` differs from UED22's | `uedcli/uscript/reference_ut99.py` | `bash uedcli/uscript/fetch_ut99.sh` (archive.org) |
| `uned/DXORIG` (gitignored) | Original Ion Storm Deus Ex (GOTY game files + SDK `UCC.exe`) | **Required for conversations** — UED22's OldUnreal `Editor.dll` REMOVED the `#exec CONVERSATION IMPORT` handler entirely (it silently no-ops); only an original Ion Storm build has it | `uedcli/uscript/reference_dxorig.py` | `bash uedcli/uscript/fetch_dxorig.sh` (archive.org) |

**Golden gotcha:** a shipped/retail `.u` is NOT a valid golden — it's editor-serialized (drops own
zero-valued defaults, carries accreted `None`-holes from years of GUI resaves). Always build the
golden fresh from the exact same sources via `ucc_compile`/`ucc_compile_ut99`/`ucc_compile_dxorig`.

## The parity bar — two gates, converging on one

- **`gate()` (strict)** — raw byte-for-byte compare. Exclusions: the 16-byte per-build-random package
  GUID, and (2026-09-13) a `UTexture` export's `InternalTime[2]` property — a SECOND per-compile-random
  field, same evidence bar as the GUID (two clean compiles of the same `#exec TEXTURE IMPORT` source
  differ in exactly those two places; `dev/docs/spikes/2026-09-13-texture-import-re/spike.md`). This
  is a new exclusion, added without a prior owner ask (the owner's standing direction for this item
  authorized it) — flagged here for review. This is the real target.
- **`perm_gate()` (permutation)** — identity/permutation compare (mirrors the `NATIVE-MATERIALIZE.md`
  campaign's methodology): resolves every ref to an identity so it also tolerates name/import/export
  table **order** and FName **case**. Originally meant as a permanent exclusion (order = pure
  indexing, functionally inert) — but the owner ruled to REPRODUCE order/case instead of excluding
  them, so `perm_gate` is now a **diagnostic stepping-stone**, not an accepted final bar: a package
  that only passes `perm_gate` (not `gate`) is an open item, not "done."

Both gates additionally compare each export's **Super** (canonicalised) and **ObjectFlags** — an
adversarial Opus review (2026-09-05) found `perm_gate` originally missed these, masking a real bug
(overriding functions emitted `Super=0` instead of the parent function); fixed.

## Status (2026-09-05)

**Architecture:** the whole compiler is Python (`uedcli/uscript/`) — lexer → parser → AST → env
(dependency resolution) → `compile.py` (declarations + defaults + `#exec`) → `lower.py`/`natives.py`
(AST→bytecode) → `ordering.py`/`reorder.py`/`global_index.py` (table order) → `serialize.py` → `.u`
bytes, checked by `gate.py`. (A parked question records that this substrate choice overturns an
earlier Rust-core framing based on a wrong premise — see the board item's `questions/`.) CLI:
`uedcli uscript compile <src-dir>`. 214 uscript tests green.

**Declaration surface — complete:** all scalar var types, static/dynamic arrays, object/class/struct
property type-tails, enums, consts, structs (incl. non-scalar struct members), `defaultproperties`
(own + inherited-override diffing), multi-class packages (`compile_package_dir`, same-package supers,
cross-class calls), native classes (RF_Native, `CLASS_Inherit` flag inheritance, the
native-or-transient defaults rule, transitive `PackageImports`).

**Bytecode — complete codec, near-complete lowering:** `bytecode.py`'s decode/encode round-trips
**all 3,581** UFunction/UState scripts across all 32 stock UED22 packages byte-exact. AST→bytecode
lowering (`lower.py`) covers essentially every construct exercised by the corpus so far (operators,
casts, control flow, Context/member access, native/virtual/final calls, switch, enum tags, cross-
package symbol resolution) — measured **99–100%** of real functions in `Extension`/`ConSys`/`UWindow`.
Every unsupported construct raises a named `LowerError`/`NotImplementedError` — confirmed by an
adversarial review that no code path emits a plausible-but-wrong token.

**Table ordering — the true UCC algorithm, reproduced from a runtime dump, not fitted:**
`UObject::SavePackage` gathers each table (names/imports/exports) from a **global engine array in
ascending index**, then sorts DESCENDING by reference count with `core.dll`'s actual CRT `qsort`
(re-verified **instruction-exact**, three times now — twice statically plus a 2026-09-13 fresh pass
that specifically settled a `>` vs `>=` tie-test question — including the tail recursion-stack logic
once suspected of hiding extra behavior; none of it does). The global index (`GObjNames`/`GObjObjects`) is a boot+load
artifact not derivable from source, so it was **dumped from a live, booted `UCC.exe` under `winedbg`**
(an INT3 planted at `SavePackage`, base `0x10000000`, no ASLR) and shipped as per-substrate data
(`uedcli/uscript/data/{gobjnames,gobjobjects}_ued22.json`). The previous fitted `OBJECT_ORDER`/
`NAME_ORDER` tables (inverse-images of the sort over 3 samples, zero predictive power — caught by an
adversarial Fable review) are **deleted**. A second real bug was found and fixed: "value-only" names
(never an object's own name — a package self-reference spliced into `PackageImports`, a
`defaultproperties` tag whose *value* is a name) were gathered in a trailing catch-all after the main
walk instead of at their real registration point (a self-name registers at class-header time; a
default-value name registers after every member/function, since `defaultproperties` compiles last).

**`#exec CONVERSATION IMPORT` — byte-exact for 16 of 19 event types.** The directive does **not**
write into the compiling package — it auto-creates sibling packages (`<Pkg>Text.u` holding the
`Conversation`/`ConEvent*`/`ConSpeech`/`ConChoice`/`ConFlagRef` object graph + mission-list
scaffolding, and `<Pkg>Audio<name>.u`). Implemented in `uscript/conimport.py`: a `.con` binary-format
parser + a ConSys object-graph builder, validated against goldens from the original Deus Ex UCC.
Other `#exec` asset types (`TEXTURE`/`MESH`/`AUDIO`/`FONT` IMPORT — image/mesh/sound codecs) are
**out of scope for now** (owner, 2026-09-05: conversations first).

### Byte-exact-vs-UCC packages (real, non-trivial)

| Package | Substrate | Classes | Strict `gate` | Notes |
|---|---|---|---|---|
| FrameBuilder | UED22 | 1 | ✅ | |
| RahnemBrushBuilders | UED22 | 1 | ✅ | pins the value-only-name gather fix |
| ExtendedBuilders | UED22 | 2 | perm only | a per-class defaultproperties-timing bug is FIXED (2026-09-13, see below); still fails `gate()` — `msvc_qsort` itself is disassembly-exact AND (2026-09-13, later pass) a live capture now confirms the gather order feeding it is exact too, so the residual is purely inside the real `qsort` call's own array handling, see below |
| DavesBrushBuilders | UED22 | 1 | ✅ | the export-gather bug (see Open items) turned out to be the same top-level-interleaving bug one level up — fixed by feeding both gathers the same AST-derived walk |
| Fire | UT99 | 6 (native) | perm only | strict-gate diff traced to compact-index width, itself a consequence of UT99 needing its OWN name-pool extraction (`ENGINE_NAME_POOL`/`HIGHLIGHT_NAME_POOL` are UED22-`core.dll`-specific); not a new bug |
| ConvTest + siblings | DXORIG | 1 (+2 auto) | ✅ | conversation import proof |
| UnrealShare | UED22 | 1 | ✅ | first live proof of the `ProbeMask` fix (`UnrealTestInfo` overrides `Tick` alone) |
| UscStateForeach | UED22 | 1 | ✅ | controlled: `Trigger`→`GotoState`→`state` (label+`Sleep`+`GotoState('')`) plus a `foreach AllActors` loop — first state-block + foreach proof |
| UscTexAsym4x4 | UED22 | 1 | ✅ | controlled: `#exec TEXTURE IMPORT` proof (no mip-average tie on any channel, so unaffected by the two open judgment calls below) |
| pkg_Mutual | UED22 | 2 | perm only | controlled: two SIBLING classes referencing each other MUTUALLY — the two-pass signature-graph proof (see below); residual is the same open name-table qsort-tie class as ExtendedBuilders |
| UscAutoEmitDefaultsUT99 | UT99 | 1 | perm only | controlled: pins the substrate-aware `_auto_emit_defaults` fix (below) — an object + every scalar type, explicit empty `defaultproperties{}`, no auto-zero tag under UT99; residual is the same UT99 own-name-pool gap as `Fire` |
| **UWeb** | UT99 | 7 | perm only | **real corpus package**, full byte match at the permutation level (identity/order/case-tolerant) — the substrate-aware `_auto_emit_defaults` fix below was the last blocker; residual is the same UT99 own-name-pool gap as `Fire` |
| UscIpAddrProbe | UT99 | 1 | perm only | controlled: pins the cross-package-struct-type-resolution fix (below) — a member var AND a function param both typed to `IpDrv.InternetLink.IpAddr`, plus struct-member access on both; residual is the same UT99 own-name-pool gap as `Fire` |
| UscImportIdentityProbe | UED22 | 1 | perm only | controlled: pins the cross-package import-identity-collision fix (below) — a class (`GameReplicationInfo`) and an inherited field sharing that same display name, both needing separate import rows; residual is the same open import/name table order tie-break `ExtendedBuilders` hits |
| **IpServer** | UT99 | 2 | perm only | **real corpus package** — with the struct-member identity fix below (a param and the struct field it accesses sharing a name, e.g. `IpAddr Addr`'s own `.Addr`), the last of a chain of gaps this package surfaced (assert, byte→string, static-through-instance call, import-identity collision) is closed; compiles end to end, `perm_gate` byte-exact; residual is the same UT99 own-name-pool gap as `Fire`/`UWeb` |
| **NoGunsMutator** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/vumaq/ut99-mutators) — hand-authored with no `defaultproperties` block and a trailing blank line, a source shape no prior fixture had; exposed a `_script_text` bug (see below), now fixed; `perm_gate` byte-exact; residual is the same UT99 own-name-pool gap as `Fire`/`UWeb`/`IpServer` |
| **ASPMutator** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/rxut/AdvancedSpawnPoints) — a `Botpack`-dependent mutator; needed the Botpack-load fix (below) plus five further real gaps (cross-package type discovery, `Vect`/`Rot` literals, Vector/Rotator→string, compound-assign operator overload, `for`-loop update-clause dependency double-recording, explicit-zero-default suppression), all now fixed; `perm_gate` byte-exact; residual is the same UT99 own-name-pool gap as the other UT99 packages. Review (2026-09-14) caught the compound-assign fix not reaching the `for`-loop update path, the struct-member half of cross-package type discovery, the `for`-loop dependency landing in init/update/cond order instead of init/cond/update, and a docker-gate skip check missing the new Sounds substrate — all fixed; the zero-default suppression was scoped back to only the measured plain-scalar case (an explicit zero-ordinal enum default is left unsuppressed, open question filed) |
| **UTServerAdmin** | UT99 | 4 | perm only | **real stock UT99 package** (`UTServerAdmin`/`UTImageServer`/`UTServerAdminSpectator`/`ListItem`) — needed nine further real gaps, all now fixed (see below); `perm_gate` byte-exact; residual is the same UT99 own-name-pool gap as the other UT99 packages |
| **ProtectSeanMutator** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/smcl/ut99-dev) — already passed `perm_gate` with no compiler change; residual is the same UT99 own-name-pool gap as the other UT99 packages |
| **VampireSeanMutator** | UT99 | 1 | perm only | **real corpus package** (same repo) — already passed `perm_gate` with no compiler change; residual is the same UT99 own-name-pool gap as the other UT99 packages |
| **SeanMutator** | UT99 | 1 | perm only | **real corpus package** (same repo, `HelloMut.uc`) — has NO `defaultproperties` block and NO trailing newline at all (ends `}` with nothing after, a source shape narrower than `NoGunsMutator`'s trailing-blank-line case); real UCC's `ScriptText` still ends with exactly one line terminator, ADDING one where the source has none — `compile._script_text`'s no-newline branch now appends `\n` instead of returning the source unchanged; `perm_gate` byte-exact; residual is the same UT99 own-name-pool gap as the other UT99 packages |
| **CrouchBlocksDamage** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/joeytwiddle/code) — its `defaultproperties` block sits BEFORE its functions in source order (every prior fixture had it last); `_script_text` used to TRUNCATE the source at the block, silently dropping every later function — real UCC EXCISES just the block (keyword through matching `}`, plus one trailing line terminator) and keeps what follows, renumbering `Line`/`TextPos` as if the block had never been there (confirmed byte-exact against a live UT99 UCC build); fixed with `compile._skip_defaultproperties_block` (a lexer-faithful brace/comment/string scanner) + a rewritten `_script_text`; `perm_gate` byte-exact; residual is the same UT99 own-name-pool gap as the other UT99 packages |
| **IdcKicker** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/joeytwiddle/code) — static-array `config` vars, `~=`, `Super` calls, `FRand()`; already `perm_gate` byte-exact with no compiler change; residual is the same UT99 own-name-pool gap |
| **NerfSniper** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/joeytwiddle/code, `NerfAmmo`), `Botpack`-dependent — a WRITE through a `class'X'.default.Field` chain, the lvalue counterpart of `UTServerAdmin`'s `.default` reads; already `perm_gate` byte-exact with no compiler change |
| **MessageAdmin** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/joeytwiddle/code) — surfaced an over-broad literal-operand constant-fold bug (`i = 256*FRand();` shifted every later jump target by 1 byte); `lower._binary` folded a constant operand into an operator's param type UNCONDITIONALLY — live-probed (`UscFoldProbe`), UCC only folds when the operator's own result needs no further outer conversion; `expr()` now threads an optional expected type from `_st_assign`/`_st_return`/`_value` (the `for`-loop init/update sibling, missed in the first pass, caught in review). `_ex_unary`'s preoperator fold was ALSO gated on `expected` in the first pass but with no live-probe evidence for unary — reverted to unconditional fold (caught in review); function-argument position isn't threaded yet, same open gap for that one context. `perm_gate` byte-exact |
| **NoPistonCamping**, **ForceBehindView**, **TeamSwitcher**, **RedirectPlayers** | UT99 | 1 each | perm only | **real corpus packages** (community mutators, github.com/joeytwiddle/code) — all already `perm_gate` byte-exact with no compiler change; `ForceBehindView`'s package name differs from its containing repo directory (`WeirdMuts`) |
| **RandomMutators** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/joeytwiddle/code) — four real gaps, all fixed: an explicit empty scalar default (`Field=`, String/Name only); `Obj.Class.Name` member access (`.Class` resolves against `Object`, the two extra Dependency entries a `.Class`-chained access adds are `Core.Class` then the chain's real underlying class — isolated via three live probes, `UscCastDepProbe`/`UscClassOnlyDepProbe`/`UscClassNameDepProbe2`; review caught the real-class lookup re-lowering its own base expression a second time, double-recording a Dependency for anything but a bare-name base — now guarded to only the measured bare-name shape); case-insensitive `class:<Name>` cast/metaclass-cast import resolution in the multi-class build path (`compile._resolve_class_ident`, matching its own same-package-sibling check and the single-class path's equivalent resolvers); a comment/string-masked function-position search (`compile._mask_lexical_noise`) so a commented-out duplicate declaration before the real one can't be matched by mistake. `perm_gate` byte-exact; controlled fixture `UscRandomMutatorsGaps` isolates the first three |
| **ArenaFallback** | UT99 | 1 | perm only | **real corpus package** (community mutator, github.com/joeytwiddle/code), `Botpack`-dependent — a bare `return;` as the last statement inside a `foreach` needs an `IteratorPop` first (`break` already got this via its jump-to-`end` flow-through; `return` exits directly and bypassed it); fixed (`lower._Lowerer.foreach_depth`); `perm_gate` byte-exact |

Controlled (non-corpus) fixtures `UscHello`/`UscVars`/`UscBB`/`UscFn`/`UscW`/`UscSt` all pass the
strict gate autonomously. `UscBareDefaultProbe`/`UscFloatByteProbe` (both UT99, found compiling
`Resize` — not itself landed, see Open items) pin a bare `default.Field` access (implicit `Self`,
lowers to a bare `DefaultVariable` token) and the `float -> byte` conversion opcode (`0x43`, a free
slot before the already-known `float -> int` at `0x44`).

**`UTServerAdmin` (2026-09-14):** the `class<T>`-typed-variable `.default` gap
(`dev/docs/board/done/class-t-typed-variable-s-default-field-needs/`) was tractable after all. Full
finding-by-finding detail (each live-probed, each with a committed regression):
`dev/docs/spikes/2026-09-14-utserveradmin-class-ref-gaps/spike.md`. Summary:

1. `class<T>.default.Field` (a `class<T>` local/param/member/metaclass cast, or a nested `class<T>`-
   typed FIELD reached through another `.default`) — `type_label` collapses every `class<T>` to the
   bare string "class", losing `T`; `lower._meta_class_of` recovers it via a side-effect-free AST
   walk, backed by a new parallel `member_meta`/`member_array_dim` channel (`natives.ClassSig`)
   alongside the existing type-label one. An OBJECT-INSTANCE `.default` uses the ordinary
   Context(0x19), not ClassContext(0x12), and records only one Dependency entry, not two.
2. `ArrayCount(...)` on a `.default` chain — a pure compile-time constant (the field's ArrayDim),
   yet every Dependency entry evaluating the discarded argument normally would have is still
   recorded (`lower._array_count_dim`/`_record_default_chain_deps`).
3. `ClassRef.Static.Method(...)` — the SAME ClassContext(0x12) wrapper `.default` uses, wrapping a
   VirtualFunction call instead of a DefaultVariable (`lower._call_method`).
4. A class with NO exported script body anywhere on the search path but reachable as an IMPORT
   elsewhere (`Engine.NetConnection`, fully native, no `.uc` source at all) is still a valid cast
   target — `env.class_home_from_imports` scans another package's own IMPORT table, a purely static
   decode, no live capture needed.
5. `"..." $/@ SomeClassRef` — the operator-overload search never let `class` widen into `string`,
   even though `_coerce`'s `ObjectToString` codegen already handled it.
6. `bool(SomeString)` = conversion opcode `0x4B`, a free slot between `string->int`(`0x4A`)/
   `string->float`(`0x4C`).
7. Two SOURCE occurrences of the same inherited field/function/struct member differing only in
   CASE used to register as two separate (ambiguous) import rows — `compile._existing_import_key`
   dedupes case-insensitively at all three import-registration sites.
8. A bare expression-statement whose call returns a STRING (result discarded) wraps in
   `EatString`(0x0E) — only the string case is verified.
9. An overriding function inherits `FUNC_Net`(+`FUNC_NetReliable`)/`RepOffset` from the function it
   overrides (replication is a property of the function itself); a bare `config;` modifier (no
   explicit name) inherits the super's `ClassConfigName` rather than resetting to `System`
   (`Engine.MessagingSpectator` is `config(User)`).

A tenth, unrelated bug found along the way: `_record_dep` wrongly SKIPPED a Context whose target was
the compiling class itself (assumed redundant with its own deep=1 self-Dependency) — real UCC does
not dedupe `Dependencies` by class at all, even for self (confirmed on real `ListItem`, a self-
referencing linked-list class, and a controlled `SelfDepNode` probe). One smaller gap found but NOT
chased (filed to the board): `ArrayCount` on a plain non-`.default` member access. The other
(a same-package inherited `defaultproperties` override crash) is FIXED — `_super_field_order` now
falls back to an in-package super's AST (`b.in_pkg_decls`) when it has no compiled export yet;
regression `pkg_SamePkgInheritedDefault` (`test_uscript_package.py`).

## Key RE findings (crux facts, detail in `dev/docs/unrealed/unrealscript/`)

- **`appStrCrc`** (`ScriptTextCRC`): CRC-32/BZIP2, poly `0x04C11DB7`, init/xor `0xFFFFFFFF`,
  non-reflected, over UTF-16LE bytes of the class's stored **CRLF** `ScriptText` (truncated at
  `defaultproperties`). An imported dependency's CRC is read from its home package, never recomputed.
- **Name-table flags** = two independent, corpus/DLL-derived pools (not per-package heuristics):
  `RF_Native` (0x04000000, the engine boot name pool) and `RF_HighlightName` (0x400, keywords +
  intrinsic type/struct names).
- **`ClassFlags`/`CPF_`/`FunctionFlags`** bit maps measured against controlled UCC compiles (plain
  class = `0x12`; plain function = `FUNC_Defined = 0x02`; etc.) — see `compile-model.md`. A pre-merge
  hardening item tracks widening goldens to cover every modifier (only a handful are pinned so far).
  `PropertyFlags`/CPF and native-class rules likewise.
- **Function `Line`/`TextPos`** point at the first EXECUTABLE statement (not the declaration).
- **Two-level `Children` chains**: class → all fields (funcs first reverse-decl, then vars
  forward-decl — UE1 prepends); function → params (decl order) → `ReturnValue` → locals.
- **Determinism**: two clean UCC compiles of identical source differ in *only* the 16-byte GUID.
- **`ProbeMask`** (the `EProbe` bit map, RE'd 2026-09-12): recovered from the boot `EName` ordinals —
  probe function names sit at consecutive ordinals from `Spawned`=217; an unused slot's placeholder
  name (`ProbeN`) IS its own bit index (self-confirming). Accumulates through inheritance:
  `ProbeMask(class) = ProbeMask(super) | own probe-function bits`. See `compile-model.md`.
- **States** (RE'd 2026-09-13): `state Foo { Label: ... }` compiles byte-exact — the `EX_LabelTable`
  format, and the `EX_Nothing` padding before it (`pad = (#GotoState/FinishAnim calls - #explicit
  Stop; statements + 2) % 4`, an empirical formula with the mechanism still unknown). See
  `compile-model.md` "UState label tables". `state` function overrides, `state X extends Y`, and
  `ignores` blocks remain unimplemented (each raises a named `LowerError`).
- **`foreach`** (RE'd 2026-09-13): `EX_Iterator`/`EX_IteratorNext`/`EX_IteratorPop` lowering is
  byte-exact — the iterator call lowers like any other call, `break`/an empty iterator both land on
  `IteratorPop` (never skip past it), `continue` jumps to `IteratorNext`. See `compile-model.md`.
- **Cross-class `Dependency` entries** (RE'd 2026-09-13, corrected 2026-09-13): a class's
  `Dependencies` array gets one entry PER SYNTACTIC Context occurrence reached via a member
  access/call through a typed object (not merely declared or cast) — never deduped by class. Within
  one function/state, occurrences record in source-textual order (an outer Context records before
  one nested in its own call's arguments); across functions/states, the class's full array gathers
  them in reverse declaration order. See `compile-model.md`.
- **`#exec TEXTURE IMPORT`** (RE'd + wired in 2026-09-13): creates a `UTexture`+`UPalette` export
  pair INSIDE the compiling package (unlike conversation import's sibling packages). `MaxColor` is
  the per-channel max over every pixel in the whole mip chain (no ambiguity); `MipZero` is the flat
  mip0 average, floored — except at an exact `.5` tie, unresolved (see Open items). See
  `compile-model.md`.

## Open items / known gaps (honest — not excluded, not hacked around)

- **The enum-vs-property name-table interleaving bug is FIXED (2026-09-13)**: a live
  `AllocateNameEntry` capture (`findings-ordering-re.md`) showed UCC registers names in plain
  interleaved SOURCE TEXTUAL order, which the compiled `.u`'s own `Children` chain cannot reproduce
  (it bins all properties into one forward sub-chain and all non-properties into a separate reverse
  sub-chain). `ast.py`'s `ClassDecl.decl_order` + `compile._top_level_name_order` thread the parser's
  own true declaration order into `reorder._Decoder.name_creation_order` (new `class_order`/
  `top_level_by_class` params), bypassing the decode-from-compiled-bytes path for this one piece.
  `DavesBrushBuilders` went from diverging at name-table index 14/74 (cascading through most of the
  table) to matching golden in all but one swapped pair (indices 21/22, `Core`/the package's own
  self-name) — since FIXED (2026-09-13, `dev/docs/board/done/uscript-name-order-core-vs-package-self-
  name/`): `ordering._gather_names` registered a class's own FName before its package's PackageImports
  self-reference; the real order (confirmed by the live `AllocateNameEntry` capture already on file)
  is self-reference first. `DavesBrushBuilders`'s name table is now byte-exact. The package's
  remaining EXPORT-table divergence (two isolated swapped pairs among tied-refcount function
  params/locals) turned out to be the SAME bug one level up, not a qsort bug: `reorder.true_order`
  fed the export gather (`order_package`'s `creation_order` arg) the OLD binned `_decl_forward` walk
  via a separate `_Decoder.creation_order()` method, even after `name_creation_order()` had already
  been fixed to use the AST-derived true top-level order. Object creation and FName registration are
  the same single top-to-bottom declaration walk in real UCC, so both gathers need the same order —
  confirmed by feeding golden's own decoded gather through the existing (already instruction-exact)
  `msvc_qsort` and finding it reproduces golden's true export order exactly once both gathers share
  one walk. `creation_order()` is removed; `name_creation_order()` is now the sole gather-order
  source for both tables. `DavesBrushBuilders` now passes the strict gate outright —
  `dev/docs/board/done/davesbrushbuilders-export-table-qsort-tie/`. `ExtendedBuilders` still fails
  `gate()` on the SAME root cause as before (a DIFFERENT, larger name-table qsort-tie-permutation
  among real engine-pool names and own-new value-only names) — but its compiled bytes are not
  unaffected: `compile_package_dir` always feeds `true_order` the AST-derived walk, so this fix
  changes the export gather for every multi-class compile, `ExtendedBuilders` included. Its total
  size now happens to match golden's (11429 B, was 11424 B) even though content still diverges from
  offset `0x4b3` on. A real sub-bug
  found by the same capture is fixed too: a function's body locals register inline, not deferred to a
  trailing pass — pinned by `test_davesbrushbuilders_locals_register_inline_not_deferred`. Known gap
  in the fix: `decl_order` doesn't place a HOISTED nested enum/struct (one declared inline inside a
  struct body) correctly — `parser.py`'s own comment on `self._hoisted` admits it lands at "the same
  (unresolved) position as in `members`." Not exercised by any current fixture; no test covers it.
- **`ExtendedBuilders`'s multi-class defaultproperties-timing bug is FIXED (2026-09-13)**: a THIRD
  instance of the same "gather order isn't reproducible from decoded bytes alone" bug class, one
  level up again — this time across a CLASS boundary, which a single-class fixture can never
  exercise. `reorder._Decoder.objinputs()` only split a class's header refs from its
  defaultproperties tag refs (`late_name_refs`) for `self.class_i` (the first class export by array
  position); every OTHER class in a multi-class package fell through to the merged `_class_streams`
  path, so its defaultproperties tag VALUE (`ExtendedBuilders`'s `GroupName="Parellelepiped"`/
  `GroupName="Wave"`, both own-new) registered as an ordinary early ref right after that class's
  header, instead of after its own members. `ordering._gather_names` compounded this: it flushed
  `late_name_refs` in ONE trailing pass over the WHOLE package, which for a multi-class compile
  defers the FIRST class's own defaultproperties past the SECOND class's entire body — wrong, since
  `compile_package_dir` compiles one class fully (through its own defaultproperties) before starting
  the next. Fix: `objinputs()` splits every class export (`e["cls"] == 0`), not just `self.class_i`;
  `_gather_names` flushes each class's `late_name_refs` right before the next class object starts (or
  at the very end, for the last class). `Parellelepiped`/`Wave` now land at golden's exact name-table
  index — `test_extendedbuilders_defaultproperties_values_land_per_class`. `ExtendedBuilders` still
  fails `gate()` outright: the first diff moved from name-table index 12 (`Core` vs `Vertex3f`) to
  index 7 (`BuildCube` vs `GetVertexCount`, both refcount 3) — this fix changed the array's own-new
  tail, and `msvc_qsort`'s median-of-3 pivot is sensitive to the WHOLE array, not just a local tied
  group, so a tail change can (and did) shift an unrelated front tie's permutation. Investigated
  further: every name in the diverging front range genuinely ties on refcount (verified identical
  between `mine`'s and golden's own independently-decoded counts), and the tail region it interacts
  with is a ~90-item refcount-0 tie (mostly never-referenced function params/locals across BOTH
  classes) — the SAME bug class as `DavesBrushBuilders`'s enum-tag scatter, which `findings-ordering-
  re.md` already concluded needs a live `AllocateNameEntry` capture, not more static reasoning, to
  pin. Not attempted here (no live UED22/winedbg environment in this sandbox).
  **2026-09-13, follow-up static pass**: re-checked all three prior candidate causes (own-new gather
  timing for engine-pool names, class-boundary interleaving, a refcount miscount) — all cleared by
  direct measurement. All 11 names in the diverging range (`BuildCube`/`GetVertexCount`/`Editor`/
  `Core`/`GroupName`/`Vertex3f`/`Width`/`System`/`EndBrush`/`Breadth`/`BeginBrush`) carry a REAL dumped
  `global_index`, not "own-new" — gather-array raw position is provably moot for them (`sorted(...,
  key=by_name_index)` ignores it). `mine`'s and `golden`'s decoded gather arrays and refcounts are
  byte-identical across all 84 names, not just these 11 — the class-boundary fix is correct.
  `BuildCube`/`GetVertexCount`'s refcount=3 is traced to real call-site `<<FName` tokens (declaration +
  call sites), confirmed identical from both packages' own decoded bytes. A SECOND, previously
  unreported divergence was found at name-table index 70-76 (`Vector` vs `BuildCube`'s params
  `LRi`/`LRj`/`LRk` and `Build`'s locals `Ri`/`Rj`/`Rk`, all refcount 0) — the same bug class as
  `DavesBrushBuilders`'s enum-tag scatter. The true ambiguous refcount=0 tier is 39 names (corrects the
  earlier "~90" estimate), still far past brute-force reach.
  **2026-09-13, live-capture pass**: ran the live `AllocateNameEntry` capture this blocked on. The
  capture ends at `ExtendedBuilders`'s own class self-name, so it directly settles only REGION 1's 11
  names (index 7-17, all header/class-level refs): each is already interned (from Editor/Fire/IpDrv/
  Extension/`DavesBrushBuilders`/`FrameBuilder`/`RahnemBrushBuilders`) before `ExtendedBuilders`'s
  compile starts, and the capture's indices for all of them match the committed `gobjnames_ued22.json`
  dump exactly — no registration-order question left for these 11. Region 2's own-new names
  (`Vector`/`LRi`/`LRj`/`LRk`/`Ri`/`Rj`/`Rk`, index 70-76) register inside the class BODY, after the
  self-name, so this capture — which stops at the self-name — says nothing about their order; that
  question stays open. A follow-on self-consistency test
  (decode `ExtendedBuilders.u`'s OWN bytes and feed its own objectively-correct refcounts/gather back
  through `order_package`) reproduces the identical 16-entry divergence, proving the bug is inside
  `order_package`/`msvc_qsort` itself, not in gather-order derivation from compile order — a materially
  different, more precisely located finding than the registration-order framing this item carried
  before. Traced `msvc_qsort` on the real array: the `BuildCube`/`GetVertexCount` swap looked like a
  `_shortsort` tie-handling question (a diagnostic `>` → `>=` tweak closes 2 of 16 diffs); the
  `Vector`/`LRi..Rk` swap sits in a 39-item all-tied run where the containing partition call is a
  provable no-op (loguy/higuy both scan off the ends without ever swapping), so `Vector`'s placement
  looked like it was set by the OUTER partition's positional Hoare-scan mechanics.
  **2026-09-13, disassembly pass: mechanism 1 REFUTED, mechanism 2 narrowed.** Extracted `core.dll`
  fresh from the `ued-x86-runtime:latest` image and re-disassembled `qsort`@`0x77cb0`-`0x781a0`
  (`objdump -d -M intel`) end to end, independently of the two prior static passes. `_shortsort`'s tie
  test (`0x77d63`-`0x77d92`: `call comp(p,mx); test eax,eax; jle skip-update`) is confirmed **strict
  `>`, not `>=`** — the diagnostic tweak was curve-fitting `ExtendedBuilders`'s one array shape, not a
  real bug; NOT applied. The median-of-3 pivot swaps and the full loguy/higuy Hoare scan also re-trace
  instruction-for-instruction to `ordering.py`'s port, with the same strict-`>` convention throughout —
  a third independent confirmation the qsort port is exact. So mechanism 2 is NOT a qsort algorithm
  bug either: with the sort proven exact, `Vector`'s wrong position must come from the ARRAY
  `_gather_names`/`order_package` hand qsort, before any sorting happens — i.e. it's a gather-order
  question after all, just one level deeper than `reorder.py`'s decode (already ruled out by the
  self-consistency test above): the true registration order of names inside a class BODY, which no
  capture so far has reached (every capture stops at the class self-name). Not fixed; no code changed
  (`ordering.py`/`reorder.py` unmodified). Settling it needs a deeper live capture reaching past the
  self-name into the class body — a separate, larger investigation (same cost class as the
  `DavesBrushBuilders` capture), not attempted this pass. Full trace:
  `findings-ordering-re.md`'s 2026-09-13 updates.
  **2026-09-13, later pass: the deeper capture ran — region 2's RELATIVE registration order among
  `LRi`/`LRj`/`LRk`/`Ri`/`Rj`/`Rk` is confirmed correct; the residual is still open.** Every prior
  capture (this campaign's included) silently stalled at the class self-name for a harness reason,
  not a natural stopping point: `dump_name_creation_order.py`'s `_setup_package` deleted the stale
  `.u` but never staged the package's `.uc` sources (the baked UED22 image ships only compiled `.u`s
  for the `realpkg` corpus, no source tree), so `UCC.exe make` aborted immediately with "can't find
  files" before parsing a single line of the class body — fixed by staging the fixture sources, same
  as `ucc_compile` already does. With that fix, the capture ran the real compile to completion (6556
  hits, was 6249) and shows `LRi`/`LRj`/`LRk`/`Ri`/`Rj`/`Rk` registering in exactly the order our
  AST-derived walk already produces, and `Vector` never firing a new-name registration at all near
  this point — it's a boot-time name (global index 31) with no timing relationship to
  `ExtendedBuilders`'s compile. **This does NOT fully confirm `order_package`'s gather-order
  modeling** — the capture only reads the `AllocateNameEntry` breakpoint's `Name` argument, never its
  `Index` argument, so it cannot see whether any name reuses a freed `FName` slot (a real, documented
  possibility — `FName::FName` pops from an `Available` array before appending). `ordering.py`'s
  `by_name_index` sentinel (own-new names sort after all dumped names) is an unverified assumption
  this capture cannot rule out. Given the qsort port is independently confirmed instruction-exact
  (three disassembly passes), a genuine residual on a deterministic sort logically must come from
  the INPUT array differing from what `SavePackage` actually builds — so the open question is
  precisely this index-reuse possibility, not "how qsort partitions the array." The next step is
  either extending the existing capture to also read the `Index` argument (cheap), or a live hook on
  the `qsort` call itself to dump its actual input array (more expensive, fully conclusive either
  way). Board item: `dev/docs/board/inbox/extendedbuilders-name-table-qsort-residual/`.
- **Calling an inherited `final` function, and reading an inherited member variable, are both FIXED
  (2026-09-13)**: an ordinary call to a function the class being compiled doesn't itself
  declare/override, any `Super.Foo()` call (always an ancestor's function, even when the current
  class overrides `Foo` under the same name — that case previously self-referenced the override
  instead of the parent, silently), and reading an inherited member variable never declared locally,
  all raised or mis-resolved because `compile.py`'s `resolve_inv` only knew the class's own
  functions/members and existing imports. `lower.py`'s `CallTarget`/`Symbol` now carry the
  function's/field's declaring class (`owner`) when it isn't the class being compiled; the token's
  obj identity is `func:<Class>.<Name>`/`mem:<Class>.<Name>` for an inherited target
  (`_final_call_ident`/`_member_ident`), bare otherwise. `compile.py`'s `_register_final_call_imports`/
  `_register_member_var_imports` import the function/property from its declaring class after lowering
  (the property import's Class is its concrete UProperty subclass, e.g. `IntProperty`), deduping onto
  `_super_func_import`'s existing key format where they name the same function. `canon()`'s
  qualifier-strip (needed because a decoded golden token only ever carries the bare name) covers both
  prefixes. Verified against a live UT99 UCC compile: fixture `UscInheritFinal` (extends
  `UWindowDialogClientWindow`) calls `SetSize`/`Super.Created()` and reads `WinWidth`/`WinHeight` —
  `perm_gate` byte-exact; the strict gate's one diff is the pre-existing UT99 name-pool gap already
  noted for `Fire` below, not new. The real community package `GiveMeItems` no longer hits either gap
  (confirmed on `GMIClientWindow.uc`'s `Created()`, which reads both) but still doesn't fully
  compile — a separate, unrelated blocker: its `#exec TEXTURE IMPORT`'s PCX asset isn't in the GitHub
  mirror, see `dev/docs/board/inbox/givemeitems-blocked-by-missing-pcx-texture-asset/`.
- **A two-pass "signature graph" for mutually-referencing same-package classes is IMPLEMENTED
  (2026-09-13)**: two SIBLING classes (no inheritance relation) that reference each other MUTUALLY —
  A holds a member typed B and calls a B method, B holds a member typed A and calls an A method —
  compile correctly. `compile_package_dir`'s old single-pass scheme built one class fully (decls +
  bytecode) before starting the next, resolving a cross-class reference by re-decoding the
  already-serialized PARTIAL package built so far; a genuine cycle has no valid single order, so
  either direction failed. Fixed with a real two-pass split in `compile.py`: pass 1
  (`_prepass_signatures`) walks every class's AST (no bytecode needed — UnrealScript var/param/return
  types are explicit in source) into a `natives.ClassSig` per class, so every class's signature exists
  before ANY class's bytecode body is lowered; pass 2 (the existing per-class loop) shares one graph
  (`_PkgSigGraph`, a `ClassGraph` that falls back to the pass-1 signature when the disk-backed lookup
  doesn't know an in-package class yet) across every class, so lowering order no longer constrains
  which cross-class refs resolve. Turned up three further gaps in the SAME area, previously
  unreachable because no test exercised a same-package non-super class reference at all (only
  same-package SUPER references, a separate, already-working mechanism): a class-typed member/param/
  local naming an in-package sibling always treated it as an unresolvable cross-package import
  (`_resolve_var_type`/`_resolve_array_type`/`_func_prop_type`); a final-function call or field access
  through such a typed reference did the same (`_register_final_call_imports`/
  `_register_member_var_imports`/`_multi_function_exports`'s `resolve_inv`, now falling back to a
  same-package EXPORT ref via the new `_sibling_export_ref` helper); and a same-package
  cross-class `Dependency` entry (`compile-model.md`'s "Cross-class Dependency entries") crashed
  outright (`_multi_class_export`'s `extra_deps` always called `env.resolve_class(dep).self_crc`, `None`
  for an in-package class — fixed to read the sibling's own already-built `self_crc`). All fixed
  together; each was load-bearing for the controlled fixture below to compile at all.

  The mechanism was first proven on a controlled fixture, `pkg_Mutual`
  (`uedcli/tests/test_uscript_package.py::test_mutual_same_package_classes`) — matching this
  campaign's controlled-vs-real distinction (a controlled fixture proves the mechanism; only a real
  corpus package counts toward the "30 packages" goal). `perm_gate` byte-exact against a fresh live
  UED22 UCC build (`docker`-gated, `test_goldens_match_ucc`); the strict gate's one residual is a
  same-package name-table qsort-TIE permutation among equal-refcount names — the SAME open,
  unresolved class of issue `ExtendedBuilders` already hits.

  **Real `UWeb` (2026-09-13): UT99 substrate fetched, package attempted, NOT YET passing either
  gate.** `bash uedcli/uscript/fetch_ut99.sh` + `ucc_decompile_ut99`/`ucc_compile_ut99` (the
  `test_ipserver_roundtrips` pattern) got real `.uc` sources and a fresh UT99-UCC golden for all 7
  `UWeb` classes. Compiling them surfaced SIX further real, previously-unexercised gaps, all fixed:
  (1) an inherited member of OBJECT/CLASS/STRUCT type (e.g. `Actor.Level`) couldn't be imported —
  `_register_member_var_imports` only handled `_SCALAR_KINDS` (`_member_import_prop_class` now maps
  `object:`/`class`/`struct:` labels to their UProperty subclass; an import table row needs no
  type-tail, so this was a narrower fix than it looked); (2) an unqualified ENUM TAG declared in a
  DIFFERENT same-package class (`Request_GET` from `WebRequest.ERequestType`, used bare in
  `WebConnection`) didn't resolve — enum tags are GLOBALLY scoped in real UCC
  (`ClassGraph.enum_ordinal` already scanned every ON-DISK package's enums regardless of class); the
  gap was the CURRENTLY-COMPILING package's own classes, which have no compiled bytes yet for that
  scan — `ClassSig` gained an `enums` field (own tags), `_PkgSigGraph.enum_ordinal` now falls back to
  scanning every in-package class's signature; (3) `new(None) class'WebRequest'` (a same-package
  class LITERAL used as a bare script ref, not through `func:`/`mem:`) wasn't resolved —
  `_sibling_export_ref` gained a bare-ident branch; (4) a NAME-TABLE CORRUPTION bug, found chasing an
  apparently-unrelated symptom (an export's baked-in name field pointing at a DIFFERENT export's
  name): `_multi_names`'s gather dedups on the SOURCE spelling (case-sensitive) BEFORE `pool_case`
  re-spells each name from the boot pool, so two source names differing only in case (`WebConnection`
  had a param `S` in one function and `s` in another) can both survive that dedup and then collapse
  onto the SAME pooled spelling — every export name index computed after the collision point was off
  by one relative to what `serialize.NameTable`'s own (correct, case-sensitive) dedup actually writes.
  Fixed with `_pool_cased_dedup` (dedup AFTER `pool_case`, matching `NameTable.index`'s semantics),
  applied at all three sites that build a package's name order; (5) an inherited function's `Super`
  field and a `class<T>` property's meta-class type-tail always imported the ancestor/meta class even
  when it was an IN-PACKAGE class (`HelloWeb extends WebApplication`, `WebServer.ApplicationClass:
  class<WebApplication>`) — `_super_func_import` and a new `_class_meta_ref` helper now check
  `b.in_pkg_class_names` first, same as an ordinary same-package member/call already did; (6) a class
  CAST (`WebServer(Owner)`) or `class'X'`/`class<T>()` literal targeting a same-package class shared
  the SAME bare-string "obj" identity as an ORDINARY MEMBER of that same name (`var WebServer
  WebServer;` is legal UnrealScript — `WebServer(x)` still casts to the class, `WebServer` alone
  reads the member) — `resolve_inv` couldn't tell them apart. Fixed by tagging every cast/metacast/
  class-literal ident `class:<Name>` at lower time (never bare), resolved BEFORE any local/member/func
  lookup (`_resolve_class_ident`, wired into all four export resolvers;
  `_register_cast_class_imports` pre-registers the import for an out-of-package target, since
  discovering one this late would miss the already-frozen import table). Two smaller, previously-
  silently-wrong gaps found and fixed alongside: a `native` var modifier persisted NO CPF bit
  (an EARLIER version of this fix wrongly modeled it as unconditional — see the review correction
  below); a function PARAM's static-array size (`byte B[255]`) was parsed and then discarded (`Param`
  had no `array_dim` field) — the SAME drop existed for a multi-name `local` declaration's own
  already-captured dim, never reaching `_add_func_prop` (which hardcoded `array_dim=1`) — both now
  flow through.

  **Review pass (2026-09-13) found one more real bug and corrected one of the six above; two claims
  did NOT reproduce.** (7) A property TYPE reference to another package (`var LevelInfo Level;`,
  Engine) spuriously added that package to `PackageImports` — reproduced on 4 of 6 real `UWeb` classes
  (`HelloWeb`/`ImageServer`/`WebApplication`/`WebResponse`) and on a trivial isolated fixture. Real
  UCC's `PackageImports` = own package + the super chain's transitive package deps + Core, full stop —
  a property/param/local/return type, a class-literal, or a `Texture'Pkg.Name'` still gets its own
  IMPORT table entry, it just never counts toward `PackageImports` (`b.class_ref_packages`, the old
  third source, is dead code now). **Correction to (part of) fix 5**: `CPF_Native` needs BOTH the
  var's own `native` keyword AND the OWNING CLASS itself being native — the original fix set it
  whenever the var said `native`, regardless of the class; a live `CPFNativeProbe` fixture (a `native`
  var in a NON-native class) shows real UCC sets no CPF bit there. Fixed by threading
  `native_class: bool` (`compile.ClassDecl`'s own modifiers, not inherited native-ness) into
  `_build_var`. **Two claims investigated, NOT reproduced**: a spurious zero-value defaultproperties
  tag on an own unset object/string var (`Level=None`/`Path=""`) — tested directly against live UED22
  on the exact reported shape and on real `WebRequest`/`WebResponse`; both sides always agree. (A
  REAL, but unrelated and much narrower, defaults divergence was found investigating this — a native
  class's own UNSET PLAIN property sometimes gets a spurious zero default, sometimes doesn't,
  real `WebRequest` itself does NOT hit it — filed separately, not chased further:
  `dev/docs/board/inbox/native-class-lone-plain-var-gets-a-spurious-zero-default/`.)

  **All seven fixes are now pinned by committed, live-UED22-verified regression fixtures** in
  `test_uscript_package.py` (`pkg_SamePkgMisc`, `pkg_PoolCaseDedup`, `pkg_InheritedObjMember`,
  `pkg_GlobalEnumTag`, `pkg_MiscFlags`, `pkg_NoSpuriousPkgImport`, `pkg_CPFNativeProbe` — one test
  function each, each verified via `test_goldens_match_ucc`'s docker-gated fresh-UCC rebuild too, not
  just the committed golden).

  **The `Dependencies`-array bug is FIXED 2026-09-13** (`dev/docs/board/done/
  uweb-dependencies-array-over-counts-cross-class/`) — decoding the committed `uned/UED22/uweb.u`
  directly (it's UWeb's own stock UED22 build, self-consistent with `UCC batchexport`-decompiled
  sources of it) found the real rule: ONE entry per syntactic Context occurrence, never deduped by
  class, gathered per-function/state forward (outer Context before one nested in its own call's
  args) but ACROSS functions/states in REVERSE declaration order (the same reversal the Children
  chain already applies). Fixed in `lower.py`'s `_call_method`/`_context`/`_record_dep` and
  `compile.py`'s `_build_callables`; full detail in `compile-model.md`'s "Cross-class `Dependency`
  entries". Verified byte-exact (count AND order) against all 7 real `uweb.u` classes'
  `Dependencies` arrays, decoded independently of the rest of the package, plus a new controlled
  fixture (`pkg_DepOrderProbe`, `test_uscript_package.py`) that isolates all three mechanics and
  passes both `perm_gate` offline and the docker-gated fresh-UCC rebuild. Full offline
  (`test_uscript_*.py`, non-integration) and integration (`-m integration`) suites both green, no
  regressions on any previously byte-exact package (`FrameBuilder`/`RahnemBrushBuilders`/
  `ExtendedBuilders`/`DavesBrushBuilders`/`UnrealShare`/`pkg_Mutual`/the six other UWeb-gap
  fixtures).

  **Both remaining blockers are FIXED (2026-09-13)**: a `pointer` var type (`WebRequest.VariableMap`,
  `WebResponse.ReplacementMap`) is now a real `PointerProperty` in `_SCALAR_KINDS` — confirmed a real
  UProperty subclass with no type-tail (`gobjnames_ued22.json`'s dumped global index,
  `uedcli/uprops/base.py`'s closed `PROPERTY_TYPES`/`_KINDS_WITH_TYPE_REF` sets) — with a named
  `PT_POINTER` sentinel that raises cleanly instead of guessing a value if a default were ever
  attempted (it never is: `pointer` only appears on native classes, which skip unset defaults). An
  explicit `Foo=None` object default (`WebApplication.WebServer`, `WebConnection.WebServer`) now
  resolves through `_object_default_ref` — the same helper the INHERITED-default path already used —
  instead of `_emit_default`'s old unconditional raise for any explicit object override. Both pinned
  by live-UED22-verified fixtures (`pkg_PointerVar`, `pkg_ExplicitNoneDefault`,
  `test_uscript_package.py`). `dev/docs/board/done/uscript-pointer-var-type-not-supported/`,
  `dev/docs/board/done/uscript-explicit-none-object-default-not/`.

  **Real `UWeb` now compiles end-to-end and is ONE divergence from a corpus win.** With both gaps
  fixed, `compile_package_dir` runs all 7 real classes (`WebResponse`/`WebRequest`/`WebApplication`/
  `WebServer`/`WebConnection`/`ImageServer`/`HelloWeb`) against a fresh UT99 UCC build with no
  exception. `perm_gate` finds exactly ONE remaining divergence: `WebApplication`'s class body emits
  3 default tags (`Level=None`/`WebServer=None`/`Path=""`) the golden omits — a NEWLY FOUND, DIFFERENT
  gap, root-caused to a genuine UED22-vs-UT99 substrate difference (not a WebApplication-specific
  bug): **UT99's own UCC never auto-emits a type-zero defaultproperties tag for a plain class's unset
  own property**, contradicting the UED22-measured `_auto_emit_defaults` rule (`compile-model.md`)
  that a non-native/non-transient class auto-emits one for every own property. Isolated on 5 minimal
  UT99 UCC compiles (an exact `NoSpuriousPkgImport`-shaped single-property class, a 3-property/
  in-package-object-type/body-less-function variant matching `WebApplication`'s exact shape, an
  all-scalar variant, and a no-`defaultproperties`-block variant) — none get an auto-zero tag under
  UT99, all get one under UED22 for the same shapes. Not fixed here (a real compiler behavior
  difference needing substrate-aware `_auto_emit_defaults`, not a quick patch — flagged for the
  owner rather than guessed at): `dev/docs/board/inbox/ut99-ucc-never-auto-emits-type-zero/`. Fixing
  it would very likely take `UWeb` to full `perm_gate` (worth re-checking strict `gate()` too) — every
  other class and the rest of `WebApplication` already identity-match.

  **FIXED 2026-09-13 — real `UWeb` is a corpus win at `perm_gate`.** Re-verified the substrate claim
  fresh (a live UT99 container, the same 2 minimal shapes plus a fresh `UWeb` decompile+recompile):
  compiling `UDPOne`/`UDPScalar`-shaped classes with the OLD (UED22-only) rule fails `perm_gate`
  against a fresh UT99 golden every time; with the rule substrate-gated, both pass. `InstallEnv`
  gained `substrate: str = "ued22"` (`"ued22"` or `"ut99"`, validated) — the search-path packages'
  real `UCC.exe` build, already conceptually distinct the way `reference.py`/`reference_ut99.py` are
  separate drivers, just not threaded into `compile.py` before. `_auto_emit_defaults` takes
  `substrate=env.substrate`: `"ut99"` always returns `False` (never auto-emit); `"ued22"` keeps the
  native/transient rule unchanged. Threaded at both call sites (`_compile_single`, `_build_class_unit`)
  via the `env` already in scope — no other signature grew. `InstallEnv`'s default keeps every UED22
  call site (the CLI, every other test) unchanged; only `test_uscript_ut99.py`'s `_compile` helper
  passes `substrate="ut99"`. Real `UWeb` (all 7 classes) now matches its fresh UT99 golden
  byte-for-byte at `perm_gate` — the permutation-tolerant bar this campaign's own `NATIVE-MATERIALIZE.md`
  methodology mirrors. Strict `gate()` still fails on name-table ORDER — the same pre-existing UT99
  own-name-pool gap already noted for `Fire` (not a new bug; UT99 needs its own `ENGINE_NAME_POOL`/
  `HIGHLIGHT_NAME_POOL` extraction, not attempted here). Pinned by two committed, live-UT99-UCC-verified
  fixtures in `test_uscript_ut99.py`: `UscAutoEmitDefaultsUT99` (controlled — one class, an object +
  every scalar type, explicit empty block) and `UWeb` itself (the real 7-class package,
  `fixtures/uscript/ut99/UWeb/`). Re-verified the full offline (`test_uscript_*.py`, non-integration)
  and integration (`-m integration`) uscript suites green, including every previously byte-exact UED22
  package individually (`FrameBuilder`/`RahnemBrushBuilders`/`DavesBrushBuilders`/`ExtendedBuilders`/
  `pkg_Mutual`/`UnrealShare`/`UscStateForeach`/`UscTexAsym4x4`/`UscInheritFinal`) — the `substrate`
  default means none of their `InstallEnv` construction changed, and none of their results moved.
  `dev/docs/board/done/ut99-ucc-never-auto-emits-type-zero/`.

  **Scope note, not applied without asking:** the `uedcli uscript compile` CLI (`cli/commands/
  uscript.py`) has no `--substrate` flag and always builds `InstallEnv` with the default (`"ued22"`)
  — a real user pointing `--deps` at a UT99 substrate would still get the UED22 defaults rule. Out of
  scope for this fix (only the `compile.py`/`InstallEnv` threading and the test-harness call site were
  asked for); flagged here rather than silently added.
- **`assert` lowering is FIXED (2026-09-13)**: found compiling the real UT99 `IpServer` package
  (below). `EX_Assert` (0x09)'s u16 operand is the 1-based source line of the `assert` keyword itself
  (probed live: two `assert`s on different lines each encode their own line number) — not a jump
  offset. `Token.line` (already tracked by the lexer) now threads through `Stmt.line`
  (`parser._parse_assert`) into the new `lower._st_assert`. Verified byte-exact vs a fresh UED22 UCC
  build (`UscAssertObjToStr` fixture, `test_uscript_assert_objtostring.py`). `do..until` lowering
  remains unimplemented.
- **Object -> string conversion is FIXED (2026-09-13)**, found in the same `IpServer` pass:
  `string(SomeObject)` casts raised "no conversion" — `_CONV`'s flat table can't hold a parametrized
  object type, so this opcode was never added. Probed live: `EX_ObjectToString` (0x56), sitting
  between `FloatToString` (0x55) and `NameToString` (0x57) in UCC's own conversion-opcode block.
  Handled directly in `_coerce` (not the `_CONV` table). Verified byte-exact in the `UscAssertObjToStr`
  fixture. The `class<T>` case (`string(SomeClass)`) uses the same code path and compiles, on the
  inference that an object and a class both store as a 4-byte object ref — but this half is NOT
  live-verified (no golden exercises it); a future package hitting a different real opcode there would
  surface as a normal gate failure, not a silent corruption. Non-conversation `#exec` (mesh/audio/font
  import codecs) remain fully unimplemented, scoped out for now.
- **`#exec TEXTURE IMPORT`** (RE'd + wired in 2026-09-13, `dev/docs/board/done/
  uscript-texture-import-compiler-integration/`): a controlled single-class fixture with no
  mip-average tie (`UscTexAsym4x4`) passes the STRICT gate byte-exact. Two open judgment calls,
  documented (not guessed silently) in `compile-model.md`/`spike.md`: the mip-quantization
  tie-break (favors the lower palette index) and `MipZero`'s rounding at an exact `.5` average
  (favors rounding up) — both unresolved for real UCC behavior, both exceedingly unlikely to affect
  real (non-degenerate) content. Only one `#exec TEXTURE IMPORT` per class is verified; a second is
  handled the same way but untested. The real community package this was scoped for, `GiveMeItems`,
  still does NOT fully compile — it needs the UT99 substrate (now fetched,
  `bash uedcli/uscript/fetch_ut99.sh`) and hits an unrelated, pre-existing gap right after the
  texture-import line: calling an inherited `final` function with no local override finds no import
  for it (`dev/docs/board/inbox/calling-an-inherited-final-function-needs-an/`).
- Expected-type-directed operator overload resolution (e.g. an int-divide whose result narrows into
  an int field) — attempted twice and reverted; UCC's real tie-break rule is subtler than modeled.
- **Corpus reality**: many stock packages (most of `ConSys`, `DeusEx`, even parts of `Extension`) are
  `native noexport` and do not round-trip **even through UCC itself** — not valid golden targets.
  Reaching 30 packages needs community/Internet pure-script packages (network access confirmed
  working) once the substrate + `#exec` gaps above narrow further.
  **2026-09-13 UT99 stock-package survey** (beyond `UWeb`/`Fire`, looking for the next corpus wins):
  `IpDrv` is `native noexport` (batchexport asserts on `Class->ScriptText`) — not a valid target, same
  class as the UED22 natives above. `UnrealI` (146 classes) and `UWindow` (78 classes) both decompile
  fine but do NOT round-trip even through UT99's own UCC — both need game content this substrate never
  fetches (`UnrealI`: `.pcx`/sound assets via `#exec TEXTURE IMPORT`/sound refs; `UWindow`: a `MenuBar`
  texture `UWindowMenuBar.uc` expects loaded). `UTServerAdmin` won't even LOAD (`Female2Voice` audio
  package missing). `UBrowser`/`UMenu`/`UTMenu`/`UTBrowser` all depend on `UWindow` and were not
  reached (blocked by the same missing-texture issue one level down). None of these five are content-
  free code-only packages the way `UWeb`/`Fire` are — not valid targets without a much larger
  asset-fetch effort, out of scope here.
  `IpServer` (2 classes, `UdpServerQuery`/`UdpServerUplink`) IS content-free and round-trips cleanly
  through UT99's own UCC — a real candidate, not yet a corpus win. Compiling it surfaced the `assert`
  and object/class->string gaps above (now fixed) and a `byte -> string` conversion gap, also now
  FIXED (2026-09-14): `("byte", "string")` = `0x52`, live-probed against a fresh UED22 UCC compile of
  `local byte B; S = string(B);` — one free slot before `int->string` (`0x53`) in UCC's conversion
  block, contrary to the earlier "fully packed, no free slot" assumption. Added to `_CONV`; regression
  `test_uscript_bytetostring.py` (`UscByteToStr` fixture, both the committed-golden and docker-gated
  fresh-UCC checks). `dev/docs/board/done/uscript-byte-to-string-conversion-missing/`.
  Re-attempting `IpServer` with the fix compiled past the `Team` line into a second gap, also now
  FIXED (2026-09-14): `P.static.GetMultiSkin(P, SkinName, FaceName)` — a `static` function called
  THROUGH AN INSTANCE expression (`P`, a `PlayerPawn`) — parsed fine (`static` is an ordinary member
  name mid-chain) but `lower.py`'s `_ex_call` tried to resolve `P.static` itself as a real member,
  raising `unresolved member object:playerpawn.static`. Live-probed: `X.static.Method(args)` and
  `X.Method(args)` compile to BYTE-IDENTICAL bytecode — `.static.` is a compile-time-only permission
  marker, no separate opcode. Fixed by unwrapping a `.static.` member sitting between a call target
  and its base before resolving the call. Regression `test_uscript_staticcall.py` (function-level
  bytecode compare, not the whole-package gate — the fixture's class body hits an unrelated,
  pre-existing Dependencies-array gap, `dev/docs/board/inbox/uscript-same-class-typed-param-context-
  under/`, found as a byproduct and not chased). `dev/docs/board/done/uscript-static-through-instance-
  member-call-p/`.
  `IpServer` then compiled past BOTH gaps and hit a THIRD, different-class gap:
  `UdpServerUplink.MasterServerIpAddr` is `var IpAddr MasterServerIpAddr;` — `IpAddr`, a struct
  declared in `IpDrv` (on `InternetLink`), not in the compiling package. `_resolve_var_type` was the
  ONE type-resolution site still missing the cross-package-struct branch `_func_prop_type`/
  `_resolve_array_type` already had (`_member_graph(b).is_struct_name(base)` + `_add_struct_import`,
  the same mechanism `Vector`/`Rotator`/… already use) — **FIXED 2026-09-14**, added mirroring those
  two exactly, no `IpAddr`/`IpServer` special-casing. Regression: `UscIpAddrProbe`
  (`uedcli/tests/fixtures/uscript/ut99/UscIpAddrProbe/`, `test_uscript_ut99.py`) — a member var AND a
  function param both typed to `IpDrv.InternetLink.IpAddr`, plus struct-member access on both —
  `perm_gate` byte-exact against a fresh live UT99 UCC build; the strict gate's only residual is the
  same pre-existing UT99 own-name-pool gap as `Fire`/`UWeb`. `dev/docs/board/done/
  uscript-cross-package-struct-type-not-resolved/`.

  `IpServer` itself was still not a corpus win at this point, but one of its two remaining gaps was
  now FIXED:
  - **The cross-package import-identity collision is FIXED (2026-09-14).**
    `Level.Game.GameReplicationInfo.Region` (`UdpServerQuery.ParseQuery`) used to raise
    `KeyError: 'GameReplicationInfo'` — `GameInfo`'s own member field `GameReplicationInfo` is named
    identically to its type, the class `Engine.GameReplicationInfo`, and every step of the ordering
    pipeline (`compile._imports_by_display`, and, deeper, `reorder._Decoder`'s whole import-identity
    model) resolved an import purely by its bare display name, so the two same-named rows collided
    onto one identity and one silently dropped from the import table. Fixed by giving every import a
    disambiguated identity end to end, mirroring the export `ekey`/`func:`/`mem:` pattern already used
    elsewhere: `reorder._Decoder` keys each import row by its own table index (`ikey`, parallel to
    `ekey`) instead of its display spelling, threaded through `objkey`/`streams`/
    `_class_split_streams` (every raw-ref-to-identity resolution) and `ordering.order_package`'s
    refcount tally/gather (`o.class_name` — always an unambiguous engine META-TYPE spelling — now
    resolves through a separate display-keyed map, since it's no longer findable via the
    identity-keyed one); `reorder.true_order` returns import rows as `(display, outer display)` pairs,
    the same disambiguation `export_rows` already carried; `compile._imports_by_display` maps a row
    back to its `b.imports` key by `(display, outer)` when the bare display alone is ambiguous.
    Verified with a new controlled fixture, `UscImportIdentityProbe` (reproduces the exact
    `GameInfo.GameReplicationInfo` shape) — `perm_gate` byte-exact against a fresh UED22 UCC build;
    the strict gate's one residual is the SAME already-tracked import/name table order tie-break gap
    `ExtendedBuilders` hits, not anything this fix touches. Re-attempting real `IpServer`: it now
    compiles the WHOLE package with no exception (was: crashed on `ParseQuery`'s first line). Full
    offline and integration uscript suites re-verified green, no regression on any previously
    byte-exact/perm-exact package. `dev/docs/board/done/uscript-cross-package-import-identity-collides/`.
  - **The struct-member/local name collision is FIXED (2026-09-14).**
    `MasterServerIpAddr.Addr = Addr.Addr;` (`UdpServerUplink.Resolved`, and the same shape in
    `ParseQuery`/`SendQueryPacket`/…) — the param `Addr` and the `IpAddr` struct's own field `Addr`
    share a name; the compiled `EX_StructMember` token's field identity was the bare field name, and
    `compile.resolve_inv`'s local-then-import lookup order let the param's own export shadow the
    struct field's import — a silent wrong-bytes bug, no exception, only visible via `perm_gate`.
    Fixed the same way the campaign already fixed the analogous inherited-call/-member collision:
    `lower._struct_member_ident` now always qualifies the token's identity `smem:<Struct>.<Field>`
    (mirroring `func:`/`mem:`), stripped in `canon()` before comparing against decoded golden
    bytecode. The owning struct is already known at lowering time (`lower._ex_member`'s own type
    inference), so `compile._register_struct_member_imports` no longer needs to re-derive it by
    walking the base sub-expression — the old `_struct_var_map`/`struct_of` machinery is deleted.
    Verified against a live UT99 UCC build: `UscIpAddrProbe`'s param reverted `NewTarget` → `Addr`
    (the real `IpServer` shape) reproduces the bug exactly (confirmed failing without the fix, passing
    with it) and is now the fixture's permanent regression. `dev/docs/board/done/
    uscript-struct-member-access-confuses-a-local/`.

  **With both gaps fixed, `IpServer` is now a real corpus win.** It compiles end to end and reaches
  `perm_gate` byte-exact against a fresh UT99 UCC build; the strict gate's only residual is the same
  pre-existing UT99 own-name-pool gap already noted for `Fire`/`UWeb`. Committed as a proper fixture
  (`fixtures/uscript/ut99/IpServer/`, `test_uscript_ut99.py`'s `_PACKAGES`), verified both offline
  (committed golden) and docker-gated (`test_ut99_matches_fresh_ucc`, an independent fresh rebuild).
  Full offline and integration uscript suites re-verified green, no regression on any previously
  byte-exact/perm-exact package.
- **`ScriptText`'s no-`defaultproperties` trailing-blank-line trim is FIXED (2026-09-14)**, found
  compiling the real community mutator `NoGunsMutator` (`github.com/vumaq/ut99-mutators`, UT99). Every
  prior fixture's source always had a `defaultproperties` block, even an empty one (real UCC's own
  `batchexport` always emits one) — `compile._script_text`'s no-block branch (`return source`
  unchanged) was never exercised against a hand-authored source lacking one entirely. `NoGunsMutator`
  has none, and its source file — as authored on GitHub — ends with a trailing blank line after the
  class's final `}`. UCC's own `ScriptText` capture drops it (and so does its `appStrCrc`-derived
  self-`Dependency` CRC, computed over the same stored text): golden's stored text ends `}\r\n`, ours
  ended `}\r\n\r\n`. Fixed: the no-`defaultproperties` branch now strips trailing wholly-blank line(s),
  keeping exactly the newline terminating the last real line
  (`re.sub(r"(\r\n|\r|\n)[ \t\r\n]*\Z", r"\1", source)`) — the `defaultproperties`-truncation branch is
  untouched (already byte-exact on every existing fixture). Verified: every existing no-
  `defaultproperties` fixture (`UscW`/`UscFn`/`UscAssertObjToStr`/`UscByteToStr`/
  `UscStaticThroughInstance`/`UscImportIdentityProbe`/`UscStateForeach`/`UscInheritFinal`/
  `UscTexAsym4x4`/`UscIpAddrProbe`/`UscTextPos`) already ends its file with a single trailing newline
  and no blank line, so the fix is a no-op for all of them — confirmed by the full offline uscript
  suite staying green (247 passed) with no fixture's golden changing. `NoGunsMutator` now reaches
  `perm_gate` byte-exact against a fresh UT99 UCC build (both the committed golden and an independent
  docker-gated rebuild, `test_ut99_matches_fresh_ucc`); the strict gate's only residual is the same
  pre-existing UT99 own-name-pool gap as `Fire`/`UWeb`/`IpServer` (here: a bare `Name` literal,
  `'Enforcer'`, naming a real `BotPack` class not in the UT99 name-pool dump — confirmed harmless to
  `perm_gate`, since bytecode `Name` tokens are casefolded before comparison; only the strict gate's
  table order/case is affected, the same as every other UT99 corpus package). `NoGunsMutator` is a real
  corpus win — `fixtures/uscript/ut99/NoGunsMutator/`, `test_uscript_ut99.py`'s `_PACKAGES`. A related,
  NOT fixed, out-of-scope-for-this-change infra gap found along the way (ruled out as unrelated to this
  package, which needs no `Botpack` dependency): `dev/docs/board/inbox/
  ut99-ucc-make-treats-botpack-as-needing-rebuild/`.
- **Cross-campaign flag**: `uedcli/native/saveorder.py` (the map-parity path) has its own copy of the
  same CRT `qsort` — worth checking it isn't the mis-ported classic variant we initially (wrongly)
  suspected here (board item `saveorder-msvc-qsort-misport`).

## Testing

Per this campaign's own testing note (mirrors `NATIVE-MATERIALIZE.md`'s project rule): run only the
uscript-relevant tests, never the whole suite blindly. On this host, `bin/test`/bare `pytest` piped
through `tail` can crash on pytest's capture tmpfile under concurrent sessions — use `-s` (capture
off) and a worktree-relative `TMPDIR`:

```
mkdir -p _scratch/pt && TMPDIR=$PWD/_scratch/pt .venv/bin/python -m pytest \
  -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_uscript_*.py -q \
  -k "not docker and not integration and not decompile and not corpus and not fresh and not rebuild"
```

Docker-gated tests (fresh-UCC rebuilds) need the relevant substrate fetched first and are skip-gated
without it. Never write scratch probe scripts via a `PYTHONPATH=` env prefix or heredoc-to-python on
this host — write a file with `sys.path.insert(0, cwd)` at the top and run it plainly.

## Where the detail lives

- RE knowledge (language, bytecode, format, compile model): `dev/docs/unrealed/unrealscript/`
  (`toolchain.md`, `u-format.md`, `compile-model.md`, `bytecode.md`).
- Process, spec, plan, parked questions: `dev/docs/board/to-build/uedcli-unrealscript-compiler/`.
- The ordering-fidelity campaign (Fable audit + the runtime-dump RE): `dev/docs/board/to-build/
  uscript-algorithm-fidelity/` (`overview.md`, `findings-ordering-re.md`).
- Pre-merge hardening backlog + the path-to-30 corpus plan: `dev/docs/board/inbox/
  uscript-pre-merge-hardening/`, `dev/docs/board/inbox/uscript-path-to-30-packages/`.
- Code: `uedcli/uscript/` (compiler), `uedcli/tests/test_uscript_*.py` + `uedcli/tests/fixtures/
  uscript/` (goldens).

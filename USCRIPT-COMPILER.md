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
(re-verified **instruction-exact**, twice, including the tail recursion-stack logic once suspected of
hiding extra behavior — it doesn't). The global index (`GObjNames`/`GObjObjects`) is a boot+load
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
| ExtendedBuilders | UED22 | 2 | perm only | a per-class defaultproperties-timing bug is FIXED (2026-09-13, see below) — its two classes' own-new `GroupName` default values now land at the byte-exact right spot; still fails `gate()` on a separate, still-open large-tied-group qsort permutation (first diff now at name-table index 7, was 12) |
| DavesBrushBuilders | UED22 | 1 | ✅ | the export-gather bug (see Open items) turned out to be the same top-level-interleaving bug one level up — fixed by feeding both gathers the same AST-derived walk |
| Fire | UT99 | 6 (native) | perm only | strict-gate diff traced to compact-index width, itself a consequence of UT99 needing its OWN name-pool extraction (`ENGINE_NAME_POOL`/`HIGHLIGHT_NAME_POOL` are UED22-`core.dll`-specific); not a new bug |
| ConvTest + siblings | DXORIG | 1 (+2 auto) | ✅ | conversation import proof |
| UnrealShare | UED22 | 1 | ✅ | first live proof of the `ProbeMask` fix (`UnrealTestInfo` overrides `Tick` alone) |
| UscStateForeach | UED22 | 1 | ✅ | controlled: `Trigger`→`GotoState`→`state` (label+`Sleep`+`GotoState('')`) plus a `foreach AllActors` loop — first state-block + foreach proof |
| UscTexAsym4x4 | UED22 | 1 | ✅ | controlled: `#exec TEXTURE IMPORT` proof (no mip-average tie on any channel, so unaffected by the two open judgment calls below) |

Controlled (non-corpus) fixtures `UscHello`/`UscVars`/`UscBB`/`UscFn`/`UscW`/`UscSt` all pass the
strict gate autonomously.

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
- **Cross-class `Dependency` entries** (RE'd 2026-09-13): a class's `Dependencies` array gets one
  more entry (`deep=0`) per distinct external class reached via a member access/call through a
  typed object (not merely declared or cast) — see `compile-model.md`.
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
  earlier "~90" estimate), still far past brute-force reach. Confirmed blocked on docker/winedbg
  availability, not a research dead end — full evidence and the precise live-capture questions in
  `findings-ordering-re.md`'s 2026-09-13 update.
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
- `assert`/`do..until` lowering, and a two-pass "signature graph" for mutually-referencing
  same-package classes (blocks `UWeb`) — real, scoped gaps in `lower.py`/`compile.py`. Replication
  blocks and non-conversation `#exec` (mesh/audio/font import codecs) remain fully unimplemented,
  scoped out for now.
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

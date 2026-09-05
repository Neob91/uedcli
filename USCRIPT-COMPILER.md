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

- **`gate()` (strict)** — raw byte-for-byte compare. Only exclusion: the 16-byte per-build-random
  package GUID. This is the real target.
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
| ExtendedBuilders | UED22 | 2 | perm only | raw byte-count diff (+5 B), unexplained — likely multi-class-specific |
| DavesBrushBuilders | UED22 | 1 | perm only | name-table order diff inside one Enum's own value list — same bug *class* as the fix above, narrower scope, not yet applied there |
| Fire | UT99 | 6 (native) | not re-verified since the ordering fixes | was perm-only pre-fix; likely strict now, re-check before relying on it |
| ConvTest + siblings | DXORIG | 1 (+2 auto) | ✅ | conversation import proof |

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

## Open items / known gaps (honest — not excluded, not hacked around)

- `ExtendedBuilders` byte-count diff and `DavesBrushBuilders`'s enum-value-list ordering — both real,
  both open (`findings-ordering-re.md`).
- `ProbeMask`/`IgnoreMask` (the `EProbe` bit map): a fixed engine enum that **accumulates through
  inheritance** — not solvable by static correlation over the stock corpus (tried, ruled out); needs
  either `Engine.dll` RE or a runtime dump, same method as the ordering breakthrough. Blocks most
  gameplay classes (`UnrealShare`/`IpServer`/etc.).
- States, replication blocks, and non-conversation `#exec` (texture/mesh/audio/font import codecs) —
  not implemented; scoped out for now.
- `foreach`/`assert`/`do..until` lowering, and a two-pass "signature graph" for mutually-referencing
  same-package classes (blocks `UWeb`) — real, scoped gaps in `lower.py`/`compile.py`.
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

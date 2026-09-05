# Spec — UnrealScript compiler with UCC byte parity

## Goal

`uedcli` compiles a UnrealScript package (a directory of `.uc` classes) into a `.u` package that is
byte-identical to what UED22 `UCC.exe make` produces from the same sources, modulo a closed
exclusion set of per-build-random fields.

## Reference (the golden)

UED22 `UCC.exe` in `uned/UED22/`:
- `ucc make` — compiles packages named in the ini `EditPackages=` list; sources at
  `<GameDir>/<Package>/Classes/*.uc`, output `<GameDir>/System/<Package>.u`.
- `ucc batchexport <Pkg>.u Class uc <dir>` — decompiles a compiled package back to `.uc`.

Run headlessly through the existing docker+wine harness (`uedcli/driver.py` / `editor.py` drive
`unrealed.exe`; UCC is the same wine binary). The golden for any test is **UCC's compile of the
exact `.uc` we feed uedcli**, never a shipped retail `.u`.

## Parity bar

Identity/permutation-based `.u` comparison (extends `parity_gate.py` philosophy to script objects):
resolve every `ObjRef` by class + outer chain, match object bodies byte-for-byte, name/import table
content must match, surviving export set + order must match.

Excluded (only these, each evidence-backed):
- Per-save-random: 16-byte package GUID, generation/save counts, any timestamp field.

Any *new* candidate exclusion needs: an adversarial subagent review confirming it is functionally
inconsequential, full evidence written into `dev/docs/unrealed/unrealscript/`, AND a board question
parked for the owner. Proceed treating it as excluded only if it is clearly per-build-random or the
review is unambiguous; otherwise fix it, don't hide it.

## Architecture

Rust crate `uedcli-native` gains a `uscript` module; Python bridge + CLI verb on top.

```
.uc sources ─► lexer ─► parser (AST) ─► pass 1: declarations ─► pass 2: code+bytecode ─► link ─► .u
                                         (classes/vars/structs/                          (name/
                                          enums/consts/fn sigs/states)                    export/
                                                                                          import
                                                                                          tables)
```

Components (each independently testable):

1. **Lexer** — UnrealScript tokens: identifiers, keywords, int/float/string/name literals,
   operators, comments, `#exec` directive lines. Byte-accurate about what becomes a name-table entry.
2. **Parser** — one class per `.uc` into an AST: class header (extends/flags), `var`/`const`/`enum`/
   `struct`, function signatures + bodies, `state` blocks, `replication`, `defaultproperties`,
   `#exec` directives.
3. **Compile environment** — loads dependency packages (already-compiled `.u`, e.g. `Core`,
   `Engine`) to resolve inherited symbols, native function indices, property offsets. Reuses the
   existing `.u` reader.
4. **Pass 1 (declarations)** — register every class, then its consts/enums/structs/vars/function
   signatures/states into the symbol table; assign property offsets; resolve superclass links.
5. **Pass 2 (code)** — compile each function/state body to UE1 bytecode (`EExprToken` stream),
   resolve labels, emit `defaultproperties` as the class default object's property block.
6. **Serializer** — write the `.u`: name table (encounter order), import table, export table,
   each UClass/UState/UFunction/UStruct/UEnum/UConst/UProperty + UTextBuffer, script bytecode.
   The byte-exact package plumbing is **Python** (`uedcli/native/codec.py`, `pkg_write.py`,
   `actor_write.py`; read-side schema `uedcli/uprops/`) — the Rust core produces a fully-resolved
   compiled-package model (offsets, flags, name-encounter order, bytecode bytes, defaults diff) and
   the Python bridge serializes it, reusing that plumbing plus new UField-body writers. See the
   parked question `substrate-premise-was-wrong` — the writer is Python, not Rust as my option
   implied. UField-body writers to add: UProperty (all subclasses), UEnum, UConst, UStruct, UState
   (+ label table), UFunction, UClass tail, UTextBuffer. Bytecode needs dual-cursor length
   accounting (variable on-disk compacts vs 4-byte in-memory `ScriptSize`).
7. **`#exec` handling** — `TEXTURE/MESH/SOUND/... IMPORT` etc. Order and effect must match UCC
   (may require driving import machinery; scoped in the plan).

## CLI

`uedcli uscript compile <pkg-src-dir> -o <out.u>` (exact spelling finalized in plan) — compiles one
package. Dependencies resolved from a search path of already-built `.u`. `--json` for structured
diagnostics. Errors exit non-zero naming the offending token/value; never a Python traceback.

## Method — lockstep feature ladder

Mirror native-materialize. Grow a minimal package by one language feature at a time; at each rung,
compile via UCC and uedcli and drive to byte-exact before adding the next feature. Order roughly:
empty class → vars (each type) → enums/structs/consts → const exprs → function sig → statements →
expressions/operators → local vars → states → replication → defaultproperties → arrays → `#exec`.
Then run the real-package corpus to 30 byte-exact.

## Testing

Per `NATIVE-MATERIALIZE.md` testing rule: run only the few relevant tests, in a stable TMPDIR, in
parallel with build work. `cargo test` for the Rust goldens (fast). The parity gate is the real
acceptance check. Pin every rung with a committed golden `.uc` + expected structural result.

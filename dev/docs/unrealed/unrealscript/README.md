# UnrealScript reverse engineering — the single home

**This directory is the ONLY place for reverse-engineered knowledge about UnrealScript and its
compilation (UED22 `UCC.exe`).** Do not scatter UnrealScript RE facts into other docs, code
comments, or spikes — record them here and back-reference from code. Sibling UnrealEd docs
(`../package-format.md`, `../class-schema.md`, `../t3d.md`) own the container/T3D format; this
directory owns the *language* and how the compiler turns it into package bytes.

Goal it serves: make `uedcli` compile `.uc` into `.u` byte-identical to `UCC.exe make`
(board item `uedcli-unrealscript-compiler`).

Every checkable claim here is pinned by a committed test (a golden `.uc` compiled by UCC, or a
`cargo` unit test). Confidence tags per `../../rules/documentation.md`.

## Topics

| Doc | Covers |
|-----|--------|
| [`toolchain.md`](toolchain.md) | running `ucc make` / `ucc batchexport` headlessly; the reference-build + decompile recipe |
| [`language.md`](language.md) | the UnrealScript grammar UCC accepts: lexical rules, declarations, statements, expressions, `defaultproperties`, `#exec` |
| [`compile-model.md`](compile-model.md) | the two-pass compile: symbol resolution, property offsets, name-table population order, export/import ordering |
| [`bytecode.md`](bytecode.md) | the `EExprToken` bytecode: opcode table, operand encoding, how expressions/statements lower |
| [`u-format.md`](u-format.md) | serialization of script objects (UClass/UState/UFunction/UStruct/UEnum/UConst/UProperty/UTextBuffer) and the class default-object block |
| [`parity.md`](parity.md) | the `.u` parity gate: identity/permutation comparison and the exclusion set |

_(Docs are added as each area is reverse-engineered; empty rows mean not-yet-written, not
not-applicable.)_

# Method and evidence conventions (read first)

Two engines are in play, and every claim must say which:

| Key          | Binary                                                | Lineage                                   | Image base |
|--------------|-------------------------------------------------------|-------------------------------------------|---
| `ued-engine` | `uned/UED22/Engine.dll` (2 722 064 B)                 | OldUnreal 469c / UT-lineage; what `PATHS BUILD` in UED22 runs | `0x10000000` |
| `ued-editor` | `uned/UED22/Editor.dll`                               | same; the `PATHS` exec dispatch           | `0x10000000` |
| `dx-engine`  | `dev/games/deusex/System/Engine.dll` (1 732 608 B)    | Deus Ex 1112fm, Unreal-1 lineage; what built the retail maps' reachspecs and what the game AI consumes | `0x10300000` |
| `dx-editor`  | `dev/games/deusex/System/Editor.dll`                  | Deus Ex 1112fm editor DLL (no UnrealEd.exe ships) | `0x10200000` |

The DX DLLs export `jmp rel32` thunks; `xdis.py` follows them (an export's listed RVA is the
thunk, the code is elsewhere).

## Tools (`harness/`, run with `/workspace/uedcli/.venv/bin/python`)

- `xdis.py <key> <export-substring|rva> [len-hex] [--nostop]` — annotated disassembly (calls
  resolved to exports/IAT/vtable slots, float/int/string annotations on absolute operands and
  immediates). `--exports <regex>`, `--strings <regex> [ctx]`, `--callers <target>`,
  `--floats <rva> <n>`.
- `layout.py <ued|dx> <Package.Class> [regex]` / `--at <hex>` — field offsets of a native class,
  computed from the `.u` (validated: Scout `GroundSpeed`/`JumpZ`/`MaxStepHeight` = +0x26c/+0x27c/
  +0x280 in `ued`, NavigationPoint `upstreamPaths`/`Paths`/`PrunedPaths` = +0x214/+0x254/+0x294,
  `bAutoBuilt` = +0x33c mask 0x40 — all match the disassembly). Use `--at` to name any
  `[reg+disp]` you meet once you know the register's class.
- `inventory.py` — export/version inventory of all five DLLs.

Class-layout hints: in `FPathBuilder` methods `ecx`/`this` is the builder; `ued` builder fields:
`+0` `ULevel* Level`, `+4` `AScout* Scout` (verify in `getScout`). `ULevel` (ued): `Actors` TArray
data at `+0x2c`, count `+0x30`; `ReachSpecs` TArray at `+0x8c` (prior spike). Always re-derive
an offset you rely on rather than trusting these.

## Evidence rules

- Every fact carries the binary key + RVA of the instruction(s) it comes from, e.g.
  `ued-engine 0x1017784f: mov [eax+0x280], 24.0 → Scout.MaxStepHeight = 24`.
- Numeric constants: quote the immediate or the `.rdata` address and value.
- Distinguish: ✅ read directly from the code · 🔬 inferred from surrounding code with the
  inference stated · 📖 hypothesis from public UE1 source knowledge, NOT yet confirmed here. Never
  promote a 📖 claim without the confirming RVA. Public UT/Unreal source knowledge (`UnPath.cpp`)
  is a useful hypothesis generator only — Deus Ex and 469 both diverge from it.
- When a function is too long to read in full, say which ranges you read and which you skipped.
- Write pseudocode for each function as you settle it (C-like, with real field names from
  `layout.py`), followed by the evidence table.

## Output

One markdown file per assignment in `findings/`, plain and short (`CLAUDE.md` "Keep it short and
plain"). No edits anywhere else in the repo; no commits.

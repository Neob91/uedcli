# T3D import: comment & unknown-property tolerance — static RE findings

**Date:** 2026-07-18
**Method:** static binary mining of UnrealEd 2.2 (`uned/UED22/*.dll`) — wide-string
extraction + `pefile`/`capstone` disassembly. **The editor was never run.** Harness in
`harness/` (`disasm.py`, `imports.py`). Confidence: 🔬 static-disassembly (byte-exact code read),
not yet live-verified — a follow-up live probe should confirm the four verdicts.

All source-path strings embedded in the code place these functions in
`C:\GameDev\UnrealTournament\Editor\Src\UnEditor.cpp` and `...\UnEdFact.cpp` — i.e. this is the
real UT/UE1 T3D import path, matching the public Unreal source lineage.

## TL;DR verdicts

| Input in an actor T3D block | Verdict | Where |
|---|---|---|
| `//` line-comment | **Stripped silently** (rest of line dropped, line still consumed) | `ParseLine`, core.dll @`0x57290` |
| `/* … */` block-comment | **NOT stripped.** No `*`/block handling exists at all. Fate depends on whether the line has `=` (see below) | `ParseLine` + `ImportProperties` |
| `;` semicolon-comment | **NOT stripped.** No `;` handling exists. Fate depends on `=` | same |
| Unknown property name (`Foo=…`, no such UProperty) | **Warned, skipped, import continues** (non-fatal) | `ImportProperties`, Editor.dll @`0x75de0` |

Extra: `\|` (pipe, `0x7c`) is a **line terminator** in `ParseLine` (outside quotes).

## The parse chain (verified by disassembly)

1. **`ULevelFactory::FactoryCreateText`** (Editor.dll @`0x58cb0`) scans the buffer for
   `Begin Map` / `Begin Brush` / `Begin Actor` … `End Actor`. For each spawned actor it calls, at
   `0x100593d5`, the free function **`ImportProperties`** (Editor.dll @`0x75de0`) with the actor's
   gathered property text. (Exports: `?FactoryCreateText@ULevelFactory@@…`,
   `?ImportProperties@@YAPBG…@Z`.)
2. **`ImportProperties`** loops over the text one line at a time. At the top of the loop
   (`0x10075e90`) it calls **`Core.dll ParseLine`** (`?ParseLine@@YAHPAPBGPAGHH@Z`, core.dll
   @`0x57290`) to pull the next line into a 1000-wchar buffer, **with the `Exact` argument = 0**
   (`push 0` at `0x10075e90`). The IAT slot `[0x100ce2d4]` was resolved to
   `Core.dll ?ParseLine@@YAHPAPBGPAGHH@Z`.
3. Per line, `ImportProperties` tries `GetBEGIN("Brush")`, `GetEND("Actor")`,
   `GetEND("DefaultProperties")`, then parses a `Name=` / `Name(` token and looks the property up.

### `ParseLine(const TCHAR** Stream, TCHAR* Result, INT MaxLen, INT Exact)` — the comment logic

Demangled signature: `int ParseLine(const TCHAR**, TCHAR*, int MaxLen, int Exact)`.
The per-character loop (`0x100572e0`):

```
0x100572f2  cmp edx, 0x0a  ; '\n'  -> end of line
0x100572f7  cmp edx, 0x0d  ; '\r'  -> end of line
...MaxLen-- guard...
0x10057305  test eax, eax          ; eax = "inside double-quotes" state
0x10057307  jne  0x10057327        ;   if in quotes, SKIP the comment check
0x10057309  cmp  [ebp+0x14], eax   ; [ebp+0x14] = the Exact arg; eax==0 here
0x1005730c  jne  0x10057327        ;   if Exact != 0, SKIP the comment check
0x1005730e  cmp  edx, 0x2f         ; current char == '/'  ?
0x10057311  jne  0x10057322
0x10057313  cmp  word [ecx+2], dx  ; …and NEXT char == '/'  ?   (dx still 0x2f)
0x10057317  mov  eax, 1
0x1005731c  cmove ebx, eax         ;   yes -> ebx = 1  (comment flag latched)
0x10057322  cmp  edx, 0x7c         ; '|'  -> terminate line
...
0x1005732c  sete al / xor [ebp-0x14] ; '"' toggles the in-quotes state
0x1005733f  test ebx, ebx
0x10057341  jne  0x10057351        ; if comment flag set: DO NOT copy char,
                                    ;   just advance Stream — rest of line dropped
0x10057343  mov  [edi], dx         ; else: copy char into Result
```

**Decoded behaviour:**
- The only comment token recognised is **`//`** — two consecutive `/` (`0x2f`). It is checked
  **only when (a) not inside a `"`-quoted string and (b) `Exact == 0`.** `ImportProperties` passes
  `Exact = 0`, so comment-stripping is **active** for actor property lines.
- Once `//` is seen, a latch (`ebx`) is set and every remaining char on the line is consumed but
  **not written** to `Result`. So `Brightness=200 // note` → `Result = "Brightness=200 "`; a line
  that begins with `//` → `Result = ""` (empty).
- Because the check is gated on the in-quotes state, a `//` **inside a double-quoted value**
  (paths, URLs) is preserved, not stripped.
- There is **no comparison against `*` (0x2a)** anywhere in the loop, so `/*`/`*/` are not
  special — `/*` is just a `/` whose next char isn't `/`, so the comment latch never sets.
- There is **no comparison against `;` (0x3b)**, so semicolons are ordinary characters.
- `|` (`0x7c`) is treated as an end-of-line terminator (outside quotes).

### `ImportProperties` — unknown property handling & what un-stripped junk does

Token scan at `0x10076030`: skip leading space (`0x20`) / tab (`0x09`), then read the property
name up to `=` (`0x3d`) or `(` (`0x28`) or NUL.

- **Line with no `=` and no `(`** (e.g. a bare `/* comment */` line or a `; comment` line with no
  `=`): the scan reaches NUL and jumps back to the loop at `0x10075fd8` — **silently skipped, no
  warning.** So a standalone block-comment or semicolon-comment line is tolerated *as long as it
  contains no `=`*.
- **Line with `=` whose name isn't a real UProperty:** `FindProperty` (call `0x100751e0`,
  `0x10076185`) returns NULL; the code falls through to `0x1007619b` and calls
  `FOutputDevice::Logf(NAME_Warning, "%s: Unknown property in defaults: %s", …)`
  (string @`0x100ec820`, warn via `[0x100ce768]` = `Core.dll Logf`), then **`jmp` back to the loop
  — import continues.** Non-fatal warning, line skipped.
  - Corollary: a `; foo=bar` line, or a `/* x */ Bar=1` line, *does* contain `=`, so its mangled
    name fails `FindProperty` and produces the "Unknown property" warning (harmless but noisy).
  - A block comment *inside* a value (`Brightness=/* x */200`) is NOT stripped; the value string
    passed to `UIntProperty::ImportText` would be `/* x */200` and mis-parse (→ 0). So block
    comments corrupt values rather than being ignored.

## Distractor ruled out

`core.dll` contains the string **`Unrecognized property %s`**, which looks relevant but is **not**
the T3D path: its only two xrefs (RVA `0x2b0dc`, `0x2b2a7`) sit inside
**`UObject::StaticExec`** (`?StaticExec@UObject@@…`, core.dll @`0x2adf0`) — the `SET`/`GET` console
command handler, unrelated to `MAP IMPORTADD`. The T3D actor path's own message is Editor.dll's
`"%s: Unknown property in defaults: %s"`.

Likewise, the comment strings `End of script encountered inside comment` /
`Unexpected '*/' outside of comment` belong to the **UnrealScript compiler** (`FScriptCompiler`),
a different tokenizer — as the task warned, T3D import does **not** share it.

## Confidence & what remains for a live probe

All four verdicts are read directly from the instruction stream (🔬 static). Two things worth a
one-shot live confirmation via `MAP IMPORTADD`:
1. That a `//`-only line and a no-`=` block/`;` line import cleanly (predicted: yes, silent).
2. That an unknown `Foo=1` line warns-and-continues rather than aborting the whole import
   (predicted: warn + continue; the warning goes to the editor log/`Warn`).

## Function/address reference

| Symbol | Binary | RVA |
|---|---|---|
| `ULevelFactory::FactoryCreateText` | Editor.dll | `0x58cb0` |
| `ImportProperties` (free fn) | Editor.dll | `0x75de0` |
| `GetBEGIN` / `GetEND` | Editor.dll | `0x80d10` / `0x80dd0` |
| `Core.dll ParseLine(TCHAR*,…)` | core.dll | `0x57290` |
| `UObject::StaticExec` (distractor) | core.dll | `0x2adf0` |

Relevant literal strings: `"Begin Actor Class=%ls Name=%ls"`, `"End Actor"` (Editor.dll);
`"%s: Unknown property in defaults: %s"` (Editor.dll @`0x100ec820`);
`"%s: Missing '=' in default properties assignment: %s"`, `"%s: Missing ')' in default properties
subscript: %s"` (Editor.dll — the only *hard* parse errors, for malformed `Name(idx` / missing `=`
after a subscript, none of which a comment triggers).

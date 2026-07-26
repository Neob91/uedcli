# Extracting UnrealEd command/behavior docs from the binaries

UnrealEd's exec commands are almost undocumented publicly. The fastest source of truth is the
shipped binaries themselves — the exec parser literals (`ParseCommand(&Str, TEXT("VERB"))`) and
the frontend's format strings are all in the DLLs/EXE. This is how the `commands.md` catalog
was built. Everything here is **static** (reads files, never runs the editor) — do it on the
bind-mounted `Tools/uedcli/uned/UED22/*.dll` directly, or inside any container.

## The one gotcha: strings are UTF-16LE
Engine `TCHAR` string literals are **wide (UTF-16LE)**. Only the C++ symbol/RTTI names are
ASCII. So `strings`/`grep "CAMERA"` finds **nothing** — you must search the wide form. (`strings`
isn't even installed in the image; use Python or `grep -a`.)

- Quick existence check (raw wide bytes): `grep -aoP "C\x00A\x00M\x00E\x00R\x00A\x00" file`
- Proper extraction (Python): match runs of `printable-byte + NUL`:
  ```python
  import re
  data = open("Editor.dll","rb").read()
  runs = [m.group().decode("utf-16le")
          for m in re.finditer(rb'(?:[\x20-\x7e]\x00){2,}', data)]
  ```
  `runs` is the wide-string table **in file order** — which roughly follows source order,
  so a parser's tokens cluster together (see below).

## Where each thing lives
- **`Editor.dll`** — the editor exec parser (`UEditorEngine`/`UUnrealEdEngine::Exec`) + all
  its `REN_*`, arg keys, and result strings ("Aligned camera on…", "Missing name", …).
- **`unrealed.exe`** — the WxWindows frontend; holds the **`printf`-style usages** that show
  real arg ordering, e.g. `'CAMERA UPDATE FLAGS=%d MISC1=%d MISC2=%d REN=%d NAME=TextureBrowser
  PACKAGE="%ls" …'`. Cross-referencing these with the parser tokens disambiguates which args go
  with which subcommand.
- **`Engine.dll`** — engine/client exec (`UEngine`/`UClient`/`ULevel`/`UViewport`): `SHOT`,
  `FLUSH`, `DEMOREC`, plus game/network verbs.
- **`core.dll`** — `UObject` exec, ini/package plumbing.

## Recipes
**1. Which binary owns a verb** (wide existence count):
```python
for f in dlls:
    n = len(re.findall(b"C\x00A\x00M\x00E\x00R\x00A\x00", open(f,"rb").read()))
```
**2. Arg-key inventory** — keys are `UPPER=` tokens:
```python
sorted({s for s in runs if re.fullmatch(r'[A-Z][A-Z0-9]{1,15}=', s)})
```
**3. The exec grammar in order** — dump every ALL-CAPS token (verbs/subcommands/flags) with its
run index; consecutive verbs = one handler's `else if` chain. This is what revealed the whole
`CAMERA` arg set (`OPEN HWND= XR= YR= REN= MISC1= MISC2= NAMEFILTER=` are adjacent) and the
full family list (`MAP`/`BRUSH`/`ACTOR`/`POLY`/`MODE`/`BSP`/`LIGHT`/`PATHS`/`CAMERA`/…):
```python
toks = [(i,s) for i,s in enumerate(runs) if re.fullmatch(r'[A-Z][A-Z0-9]{1,17}=?', s)]
# print in order; clusters of related verbs sit adjacent
```
**4. Read a cluster** — once a verb's index is known, print `runs[i-3 : i+12]` to see its
subcommands, arg keys, and the result/error strings the handler emits.

## Beyond strings: disassembly
The wide string table gives **vocabulary and arg keys**. To recover **algorithms and numeric
constants** (e.g. the CSG/BSP build), disassemble the code directly: the exports are
MSVC-mangled C++ names (`?bspBrushCSG@UEditorEngine@@...`, `?SplitWithPlane@FPoly@@...`), so a
`pefile`+`capstone` harness maps each export to its code and reads embedded float thresholds and
`appFailAssert` source paths out of `.rdata`. This is how the BSP-hole mechanism was pinned down
(`../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`); the reusable harness lives in
`_scratch/bspspike/` (`pip install capstone pefile`). Still static — reads the DLLs, never runs
the editor.

## Then verify live (separate container)
String extraction gives the **vocabulary and arg keys** with high confidence, but not exact
semantics. Confirm the interesting ones in an **isolated `docker compose run` editor** (never
`dx-lum-uned`) — drive the verb via `wine_ctl exec`, read the effect via `MAP EXPORT` /
`EDIT COPY` / the log window / `wmctrl`, then tear the container down. This is how `SELECTNAME`
and `CAMERA OPEN` were pinned down (and how the old "no select-by-name" claim was disproved).
Mark each doc entry with its confidence (✅ verified · 🔬 live-probed · 📖 string-extracted).

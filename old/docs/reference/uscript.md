# uscript

Compile UnrealScript source into a `.u` code package — a native compiler that matches UCC's byte
output. Fully offline: no editor, no docker.

- **`uscript compile <SRC-DIR> [-o OUT.u] [--package NAME] [--deps DIR …] [--json]`** — compile
  every `*.uc` in `SRC-DIR` into one package. `SRC-DIR` is a package's `Classes/` dir or a flat dir
  of sources; all its `.uc` files become one `.u`. Prints the written path — then any conversation
  sibling paths — to stdout, and a `compiled N class(es) → M bytes` summary to stderr.
  - **`-o, --out`** — output path (relative → cwd). Default: `<PkgName>.u` in the cwd.
  - **`--package`** — the package name (it heads every class's imports and names the output).
    Default: the source dir's name, or its parent's when the dir is named `Classes`.
  - **`--deps`** — extra `.u` search dirs for resolving superclasses and types (repeat to add more).
    The game substrate (Engine/Core packages) is searched by default; when it is unavailable, pass
    at least one `--deps` dir holding `core.u` and `Engine.u`.
  - **`--json`** — emit `{package, classes, bytes, path, siblings}` instead of the bare path lines
    (`siblings` lists any conversation packages written).

Compile errors — a parse error or a construct the compiler does not support yet — exit 2 with a
message naming the class and construct, never a traceback. A missing or empty source dir exits 2
naming it. With no dependency packages resolvable, it exits 2 telling you to pass `--deps`.

The compiler covers the class declaration surface (header/modifiers, member `var`s, `enum`/`const`/
`struct` declarations, `defaultproperties`) and function bodies. States, replication, `cpptext`, and
`#exec` directives other than `CONVERSATION IMPORT` are not yet supported and exit 2 naming the
construct.

## Conversation import

A class with `#exec CONVERSATION IMPORT FILE="X.Con"` adds nothing to its own package; it emits
SIBLING packages next to the output, exactly as the original Deus Ex editor does:

- `<Package>Text.u` — the conversation object graph (the `Conversation` / `ConEvent*` / `ConSpeech` /
  `ConChoice` / `ConFlagRef` objects plus the mission scaffolding).
- `<Package>Audio<AudioPackage>.u` — an audio-list stub, where `<AudioPackage>` is the `.con`'s
  audio-package name.

The `.con` file is read from `SRC-DIR` or its parent (a package keeps its `.con` beside `Classes/`).
The `ConSys` package must be resolvable on the search path (the substrate or `--deps`).

```bash
uedcli uscript compile MyMap/Classes --deps ~/DeusEx/System
# → MyMap.u, MyMapText.u, MyMapAudio<Pkg>.u
```

```bash
uedcli uscript compile MyPkg/Classes                    # → MyPkg.u
uedcli uscript compile src -o build/Foo.u --package Foo
uedcli uscript compile src --deps ~/MyGame/System --json
```

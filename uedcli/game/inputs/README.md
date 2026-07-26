# game/inputs/ — user-supplied, gitignored build inputs

Everything here is **gitignored** and copyright-derived — never commit it.

## `edit/` — the v469 UCC toolchain (9 files)

`uscript/build.sh` compiles the UedPreview packages with it inside the builder
container. Populate locally (same provenance as uplayctl's copy):

    cp -r ../uplayctl/game/inputs/edit uedcli/game/inputs/edit

Files: `hUCC.exe`, `Editor.dll`, `Editor.u`, `Editor.int`, `Window.dll`,
`RenderExt.dll`, `RenderExt.int`, `msvcr120.dll`, `CoreI.dll`.

A missing toolchain is a NAMED exit-2 from `level preview --game` (never a traceback).

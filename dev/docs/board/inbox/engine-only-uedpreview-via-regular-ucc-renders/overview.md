+++
priority = "p2"
kind = "debug"
summary = "Real engine pixel render WITHOUT hUCC: engine-only UedPreview.u (regular UED22 v469 UCC) loads and runs in v68 DeusEx.exe — partially unblocks level-preview-game-blocked-on-this-box-two."
+++

# Engine-only UedPreview via regular UCC renders in v68 DeusEx.exe (no hUCC)

`level-preview-game-blocked-on-this-box-two` says `--game` needs the gitignored `hUCC.exe` because
UED22's v469 UCC can't build the DeusEx driver `UedPreviewDX`. **But for an ENGINE-level render
(BSP + texture rasterization — e.g. a texture-alignment check) the DeusEx driver is not needed.**
Verified live 2026-08-03: the engine-only `UedPreview.u` compiled with regular UED22 v469 UCC LOADS
AND RUNS inside the retail v68 `DeusEx.exe` (versions are one apart, 68 vs 69; engine-only classes
reference only stock `Engine`/`Core`/`IpDrv`, resolved by name). Real SoftDrv frames captured; uedcli
`actor preview --faces textured` alignment MATCHES the engine pixels (F-glyph orientation, handedness,
tiling density, quadrant layout, registration dot).

Two GUI-editor gotchas cleared (not blockers): build the map via headless `Editor.ExecCommandlet`
(the GUI `UnrealEd.exe` GPFs on `OBJ LOAD`/`CAMERA OPEN` — see `dx-lum-uned-image-missing-rendering-md-editor`);
and `DeusEx.exe` hangs at boot on the modal First-Time-Config wizard, NOT the esync deadlock —
`FirstRun=400` in `DeusEx.ini` skips it and the link binds reliably (~12s).

## Repeatable (retail v68 System+content is at `dev/games/dxreal`, in the installer-url worktree)
1. Compile `UedPreview.u` engine-only with `UCC.exe make` (EditPackages += UedPreview; drop the
   3 UedPreview/*.uc, NOT dxdriver) in a `dx-lum-uned` container -> v69, 0 errors.
2. Build a bootable textured map headlessly: `UCC.exe Editor.ExecCommandlet` running
   BRUSH IMPORT/SUBTRACT + MAP IMPORTADD PlayerStart + MAP REBUILD + MAP SAVE -> `room.dx`.
3. Assemble a game root (dxreal/System + `UedPreview.u` + the `.utx` + `room.dx`); patch `DeusEx.ini`:
   `Console=UedPreview.UedPreviewConsole`, `RenderDevice=SoftDrv.SoftwareRenderDevice`,
   `WindowedColorBits=32`, `StartupFullscreen=False`, `FirstRun=400`; `WINEESYNC=0 wine DeusEx.exe -log -nosound`;
   drive the `127.0.0.1:7777` link (`travel`/`pose`/`shot`) to X-grab SoftDrv frames.

TODO: promote the harness (compile script, `room.exec.txt`, `grab.py`, the built `UedPreview.u`)
to a committed `dev/docs/spikes/` per `rules/spikes.md` (owner-gated) so this render capability isn't
lost with the scratch dir; and fold the engine-only-render unblock into the game-preview item.

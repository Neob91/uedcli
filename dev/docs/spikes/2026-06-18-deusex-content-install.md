# Deus Ex content install spike (2026-06-18)

Goal: make the missing base Deus Ex *content* packages available to the
`uedctl` editor substrate so real maps load/export end-to-end, by
downloading the user-pointed Deus Ex install.

**Outcome: content layer SOLVED.** With the install's content packages
(`.utx`/`.uax`/`.umx`) wired in — and **code coming only from the
substrate's stripped ver-69 `.u` files, never from the game** — the
editor loads and exports the vast majority of maps:

- **78 of 83 DeusEx retail maps** load and export to T3D.
- **LUM maps that use only base content** load (e.g. `19_FMA` →
  1.7 MB T3D; `Auto0/8/9`, `Entry`, `dx`).

The remaining failures are NOT content problems — they are
**substrate code-stripping limits**:

- 5 retail maps (`00_Intro`, `99_Endgame1..4`) fail on
  `Class Engine.CameraPoint` — stripped from UED22's `Engine.u`.
- Most LUM mission maps fail on `Class LUM_Core.<LUM_*>` — the repo's
  own `LUM_Core.u` in the substrate is a **stub** (20 names, none of
  the `LUM_*` classes whose `.uc` sources live in `LUM_Core/Classes/`).
- `20_Lenz` fails on `Function DeusEx.DeusExDecoration.BeginPlay` —
  stripped from UED22's `DeusEx.u`.

## Key correction: code comes from the substrate, content from the game

The earlier version of this note chased a "ver-68 vs ver-69 mismatch" by
trying to substitute the game's `.u` files. That is the wrong approach:
**UED22's stripped ver-69 `.u` files are the authoritative editor code.**
The game's `.u` files (whether retail v1.0 or the 1.112fm patch) are
ver 68 and incompatible with the ver-69 `UCC.exe`/DLLs — feeding them in
produces `Can't find FloatProperty Engine.Decoration.BaseEyeHeight` or
`Commandlet batchexport not found`. The only thing the install supplies
is **content**.

The 1.112fm patch (`DeusExMPPatch1112fm.exe`, kentie.net) was downloaded
and inspected: it ships **only code `.u` and DLLs — zero content
packages** — so under the content-only rule it contributes nothing. It
was deleted.

## Where the install lives (NOT in git)

**UPDATE 2026-06-20:** the durable copy of this content has since moved out of `_scratch/`
to `Tools/uedctl/uned/DeusExAssets/` — see
the asset-layout design (`specs/2026-06-20-uedctl-deusex-assets-layout-design.md`, landed; deleted) for why
(`_scratch/` is documented as throwaway-only; a real substrate dependency doesn't belong there)
and how it's wired into the container by default. The extraction narrative below (obtained
from the installer, the music-patch fix) is unchanged history; only the final resting path
differs from what's written below.

At extraction time (this spike), it sat under `_scratch/` (gitignored; substrate sees it at
`/repo/_scratch/`):

- `_scratch/deusex/extracted/Deus Ex Installer/` — installer leftovers
  (`Install.exe`, `install.dat`; the ACE volumes were deleted after
  extraction). Still lives here — genuinely throwaway, not moved.
- `_scratch/deusex/game/` — the extracted game tree used as the content
  source: `Textures/` (57 `.utx`), `Sounds/`, `Music/` (35 `.umx`),
  `Maps/` (83 retail `.dx`), plus a `System/` of ver-68 game `.u` that
  is **deliberately NOT on the editor's path**. **Moved** to
  `Tools/uedctl/uned/DeusExAssets/` 2026-06-20.

## How it was obtained / extracted

1. Download: `deusexinstaller_win.7z` (158 MB) →
   `7z x` (needs `p7zip-full`) → a multi-volume **ACE 2.0** archive
   (`deusex.ace` + `.c00`–`.c52`). `unar` / free `unace` can't do
   ACE 2.0; `unace-nonfree` (apt) extracted all 53 volumes (213 files).
2. Music fix: the download is a size-reduced distribution whose
   `SETUP.BAT` recreates every `*_Music.umx` as a **copy of
   `Training_Music.umx`** (placeholder music). Reproduced that step into
   `game/Music/` (2 → 35 `.umx`). This is what unblocked the NYC/other
   retail maps that import `*_Music` packages.

## Path wiring used (throwaway, ephemeral container only)

The editor reads `[Core.System] Paths` from `unrealtournament.ini`. The
committed file's `../Textures/*.utx`-style relative paths don't resolve
under UCC's cwd (`/opt/UED22`); rewrite to absolute and add the install
content (content only — no game `.u`):

```
[Core.System]
...
Paths=/repo/Tools/uedctl/uned/UED22/*.u        ; substrate code (authoritative)
Paths=/repo/System/*.u                          ; repo code (Endemia, CaroneElevatorSet)
Paths=/repo/Textures/*.utx                      ; repo textures incl. LUM_CoreTex
Paths=/repo/Sounds/*.uax
Paths=/repo/Music/*.umx
Paths=/repo/Maps/*.dx
Paths=/repo/_scratch/deusex/game/Textures/*.utx ; install content
Paths=/repo/_scratch/deusex/game/Sounds/*.uax
Paths=/repo/_scratch/deusex/game/Music/*.umx
```

**DONE 2026-06-20:** made permanent at `Tools/uedctl/uned/DeusExAssets/{Textures,Sounds,
Music}/*` — `entrypoint.sh` now appends these `Paths=` lines automatically at container boot,
conditional on the directory's presence (see the layout design doc above). The relative→
absolute rewrite described here is still the load-bearing mechanism; only the source dir and
the "who wires it" answer changed.

## Proof it loads/exports

Correct invocation (the out dir MUST be a wine `Z:\` path, not a Unix
path — a Unix path gives "Failed to make directory"):

```
$ wine /opt/UED22/UCC.exe batchexport \
    /repo/_scratch/deusex/game/Maps/00_Training.dx Level T3D 'Z:\repo\Temp\dxtest'
Loading package .../00_Training.dx...
Exported Level 00_Training.MyLevel to Z:\repo\Temp\dxtest\MyLevel.T3D
Success - 0 error(s), 0 warnings        # 6.0 MB T3D

$ wine /opt/UED22/UCC.exe batchexport /repo/Maps/19_FMA.dx Level T3D 'Z:\repo\Temp\dxtest'
Success - 0 error(s), 0 warnings        # 1.7 MB T3D (22 install content deps resolved)
```

Full retail sweep: 78/83 Success; the 5 failures all
`Can't find Class Engine.CameraPoint`.

## What's still needed (not content)

- **`LUM_Core.u`** in the substrate is a stub. The LUM mission maps need
  a real `LUM_Core.u` compiled from `LUM_Core/Classes/*.uc`. (Recompiling
  under UED22 is unlikely to work cleanly — noted, not attempted.)
- **`Engine.CameraPoint`** and **`DeusEx.DeusExDecoration.BeginPlay`**
  are stripped from the substrate's `Engine.u`/`DeusEx.u`; the 5 retail
  cinematic maps and `20_Lenz` need those symbols present.

None of these are fixable by adding game content; they are substrate
(editor `.u`) completeness issues.

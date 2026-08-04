+++
priority = "p2"
kind = "finding"
summary = "DeusEx.exe game-preview boot blocked by forced Entry->DX.dx auto-travel (:7777 never binds)"
+++

# DeusEx.exe game-preview boot blocked by forced Entry->DX.dx auto-travel (:7777 never binds)

From spike `2026-08-04-deusex-cd-bypass-and-game-travel-wall`. With the retail CD check bypassed
(stage `Textures\Palettes.utx`) and memory under the cap, `DeusEx.exe` boots through full engine init,
`MissingIni`, recovery-mode, and the entry map — to `Bringing Level Entry.MyLevel up for play` with a
spawned `Engine.Camera` — then dies at a **forced `Entry`->`DX.dx` game-travel**.

`UGameEngine::Init` browses a **hardcoded** `DX.dx` (DeusEx's standalone default start map), ignoring
`[URL] Map`/`LocalMap` in `DeusEx.ini`/`Default.ini`/`User.ini` **and** the command-line URL. The
browse fails **before** `LoadMap` with an empty reason (`Failed to enter DX.dx: `). So the
`UedPreviewConsole` never ticks to spawn the link and **`:7777` never binds** — the `render_frame`
game-boot path can't render.

This blocks the in-game (`--game`) preview via `DeusEx.exe` regardless of FEX/CD/memory. It was never
seen before because prior spikes wedged on memory first; the game-boot render path is thus unvalidated.

Open questions for whoever picks this up:
- Why is the `Entry`->`DX.dx` browse rejected pre-`LoadMap` (empty error)? Suspect the game-travel from
  a stock `GameInfo`/`Engine.Camera` standalone; needs `UGameEngine::Browse` RE (Engine.dll).
- Would the DeusEx engine (`dx`) + real menu maps (`Entry.dx`, `DX.dx`, `Index.dx`) + DeusEx content
  boot to the menu, bind `:7777`, then `TravelToLevel(room)` on the link? Heavier — OOM risk on the
  6 GiB cap; the real menu maps + deps weren't staged in this spike.

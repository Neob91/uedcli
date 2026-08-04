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

Two fixes tested and disproven (spike follow-up):
- **Rename room->`DX.dx`** (make the forced-travel target our room): does NOT work. `UGameEngine::Browse`
  rejects the travel BEFORE `LoadMap` (no `Loading: Package DX` line), so our map is never loaded —
  content/filename/case is irrelevant. `Browse` disasm (`Engine.dll` @ `0x1038b0fb`): a local map with a
  level already "up for play" takes the server/network-travel dispatch, not a direct `LoadMap`.
- **Real DeusEx engine** (`DeusExGameEngine`): needs the full content graph — dies at `InitEngine` with
  `Can't find file for package 'Effects'` (`DeusExItems`->`Effects.utx`, not staged). Memory still fit
  (peak 6.08 GiB). And `DX.dx` is then the real menu map, so it can't also be our room.

Open path for whoever picks this up:
- Either RE `UGameEngine::Browse`/`Init` to make the `Entry`->`DX.dx` travel load a fresh local map (or
  patch the engine to stay in `Entry`, where the room is already "up for play" with the console), OR
  stage the full DeusEx content (Textures/Sounds the graph pulls) so the `dx` engine reaches its real
  menu and `:7777` binds, then `TravelToLevel(room)` on the link. Both are larger than a config tweak.

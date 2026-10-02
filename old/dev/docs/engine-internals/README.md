# `dev/docs/engine-internals/` — game-runtime & RE-workflow gotchas

This directory holds cross-cutting gotchas found while reverse-engineering the Deus Ex game runtime
(the shipped `DX/System/*.dll` — `Render.dll`, `Engine.dll`) and driving/debugging it headless under
wine. It is distinct from the two other knowledge stores:

- `dev/docs/unrealed/` — facts about UnrealEd (the editor, UED22 DLLs at base `0x10000000`). Editor
  exec-verbs, T3D, CSG, editor quirks.
- This dir (`engine-internals/`) — facts about the game (the runtime, `DX/System` DLLs) and the
  workflow of RE-ing and live-debugging it (disassembly harness traps, `WINEDEBUG`/`winedbg`
  pitfalls, the boot/console-link infra, disk hygiene).

The game and the editor are different substrates with different DLL base addresses — do not conflate
them. `Render.dll` (the game's software renderer, base `0x10b00000`) has no editor equivalent;
`Engine.dll` exists in both but at different bases and different builds.

## Contents

- [gotchas.md](gotchas.md) — the running list: RE/disassembly workflow, wine/game live debugging,
  boot & driving infra, and verified game-runtime engine facts (Model layout, the lit-render path).
  Append to it as you go — every expensive-to-rediscover trap belongs here.

## Related

- `Tools/uplayctl/docs/DRIVING.md` — how to play the game faithfully (navigation philosophy). The
  gotchas here are about debugging/RE-ing it, not playing it.
- `dev/docs/spikes/2026-07-15-native-materialize/` — the native-materialize RE spike these gotchas
  were mostly mined from (sections 20/50/60 + the `harness/` disasm tools).

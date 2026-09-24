+++
priority = "p2"
kind = "debug"
summary = "RESOLVED: in-game room preview renders under wine-8/qemu + 16 GiB caps (FEX+wine-10 ClientTravel corrupts)"
+++

# DeusEx.exe game-preview boot blocked by forced Entry->DX.dx auto-travel

**RESOLVED 2026-08-05** (spike `2026-08-04-deusex-cd-bypass-and-game-travel-wall`). The original
finding (`UGameEngine::Init` force-travels a hardcoded `DX.dx`, ignoring `[URL] Map`/the CLI URL, so
`:7777` never binds) is superseded: with caps raised to 16 GiB, the actual wall was **FEX+wine-10
`ClientTravel`** object-system corruption on content-loading travel, not memory or the map. Under
**wine-8/qemu** (`dx-lum-uned`) the menu binds `:7777`, then `TravelToLevel room.dx` renders our
textured room (`game_preview_here_room.png`, deterministic) and OG retail maps; our room also needs
`Amark.utx` staged (wine-8 warns+reverts if missing, wine-10 crashes).

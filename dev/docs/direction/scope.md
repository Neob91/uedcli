# Scope — a generic UnrealEngine-1 tool

## What we want

uedctl is editor-automation for **UnrealEngine 1.0 games in general**, with
**Deus Ex as one baked-in substrate**, not as the tool's identity.

- New code, flags, verbs and naming avoid DeusEx-only framing.
- Map-file handling supports `.dx` (Deus Ex) and `.unr` (Unreal/UT) alike.
- Substrate-specific knowledge — class names, helper actors, packages — is
  **selected per-substrate, never hardcoded**.
- **Forward-looking, not a refactoring mandate.** Existing DeusEx-named code is
  not churned for this; only fresh things must adhere.

**The naming split:** the user-facing config key is **`game`**
(`[games.<name>]`, `--game`); the internal concept and code symbols stay
**`substrate`**. A substrate maps 1:1 to a game for every game we support, so
the TOML says what Andrzej says, and the code keeps the generic abstraction.

## Rejected

- **Treating uedctl as a Deus Ex tool.** The substrate split (code vs content,
  per-substrate helper classes) and the UE1-generic T3D/console-verb surface
  already make the core game-agnostic; naming should reflect that rather than
  re-entrench a DeusEx-only framing.
- **`substrate` as the user-facing config key.** Andrzej reads and says
  "game"; the TOML should match.
- **Renaming the internal `substrate` concept and symbols too.** Churns
  established code for no user benefit — the term is correct as the
  generic-UE1 abstraction.

## Refs

`../architecture.md` "Substrate" · `../board/README.md` "Portability goal"

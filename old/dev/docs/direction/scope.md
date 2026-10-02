# Scope — a generic UnrealEngine-1 tool

## What we want

uedcli is editor-automation for **UnrealEngine 1.0 games in general**, with **Deus Ex as one
baked-in substrate**, not the tool's identity.

- New code, flags, verbs and naming avoid DeusEx-only framing. Existing DeusEx-named code is
  not churned for this — but de-DeusEx-ify it opportunistically when the code is already being
  refactored and the change is cheap.
- Map-file handling supports `.dx` (Deus Ex) and `.unr` (Unreal/UT) alike.
- Substrate-specific knowledge — class names, helper actors, packages — is **selected
  per-substrate, never hardcoded**.

**The naming split:** the user-facing config key is **`game`** (`[games.<name>]`, `--game`); the
internal concept and code symbols stay **`substrate`**. A substrate maps 1:1 to a game for every game
we support, so the config says what the owner says while the code keeps the generic abstraction.

## Rejected

- Treating uedcli as a Deus Ex tool.
- `substrate` as the user-facing config key — the owner says "game".
- Renaming the internal `substrate` concept and symbols — churns established code for no user
  benefit.

## Refs

`../architecture.md` "Substrate" · `../board/README.md` "Portability goal"

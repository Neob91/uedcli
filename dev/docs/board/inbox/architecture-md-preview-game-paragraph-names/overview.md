+++
priority = "p2"
kind = "owner-question"
summary = "[OWNER — confirm] architecture.md's `level preview --game` paragraph still names the removed `UedPreviewDX` typed driver and the `inputs/edit/` hUCC toolchain — needs the owner's yes to edit dev/docs."
+++

# [OWNER — confirm] architecture.md preview --game paragraph names removed UedPreviewDX/hUCC

The `game-preview-generic` branch removed the DeusEx typed driver (`UedPreviewDX`), the hUCC gate,
and `uedcli/game/inputs/`. `dev/docs/architecture.md` (the `level preview --game` paragraph, ~L2166)
still describes them:

> … `uscript/` — the `UedPreview` link/console/base-driver package + the `UedPreviewDX` DeusEx
> substrate driver, compiled in a mounted builder against the game's own `DeusEx.u`). The v469 UCC
> toolchain is user-supplied/gitignored at `uedcli/game/inputs/edit/` (see its README).

Editing `dev/docs/` needs the owner's yes (CLAUDE.md), so it is left as-is on the branch. Proposed
replacement for those two sentences:

> … `uscript/` — the `UedPreview` link/console/base-driver package, compiled engine-only with the
> base image's own regular UED22 UCC (no game files, no user-supplied toolchain; the base driver
> hides every substrate's frame with stock Engine fields + per-substrate `HudHideCommands`).

On a yes, apply the edit with a `Confirmed:` trailer? (architecture.md is not a `direction/` topic, so
no `direction/` trailer applies — just the owner's approval to edit `dev/docs/`.)

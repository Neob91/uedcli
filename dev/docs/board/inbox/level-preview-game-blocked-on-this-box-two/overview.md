+++
priority = "p2"
kind = "owner-question"
summary = "`level preview --game` blocked on this box: TWO independent gaps found (2026-07-21)"
+++

# `level preview --game` blocked on this box: TWO independent gaps found (2026-07-21)

Dogfooded the whole path — installed GOG Deus Ex (1.112fm) at `~/Games/DeusEx`, ran
`dev/scripts/install-deusex-assets.sh` (clean), previewed. `--native` renders brushdemo fine.
`--game` is blocked by:
**(1) The `edit/` UCC toolchain is unprovisioned.** `preview_game.py` gates on
`uedcli/game/inputs/edit/hUCC.exe`. The 9-file set is user-supplied/gitignored (uplayctl provenance)
and is NOT anywhere on this box (`../uplayctl/game/inputs/edit` absent). `hUCC` = **Hanfling's** UCC
(a community build matched to the DX **v68** engine), NOT "headless" — plain `UCC.exe` is already a
headless CLI tool; `UnrealEd.exe` is the GUI binary that wedges open. **Can `uned/UED22/UCC.exe`
substitute? Investigated in depth (harness `_scratch/ucctest/*.sh`; results `result*.log`) —
PARTIAL:**
- Run UED22's UCC **in its own dir with its own v469 DLLs**, it compiles the engine-only
  **`UedPreview.u` cleanly** (my first "it fails with `appChdirSystem`" test was mis-set-up — UED22's
  v469 `UCC.exe` against the game's v68 `Core.dll`; discount it. In its own env it works.)
- It **CANNOT compile `UedPreviewDX.u`** (the DeusEx driver): `Unrecognized member 'ShowHud' in class
  'DeusExPlayer'`. Two-sided wall: (a) UED22's committed `DeusEx.u` is a mesh/structure stub —
  **method-stripped** (the `DeusExPlayer` type resolves, but its methods `ShowHud`/`inHand`/… are
  absent); (b) the **full v68 `DeusEx.u`** (which has those methods) can't load under UED22 because it
  references `Core.Object.Sprintf` 73× — a function DeusEx added to its **v68** `Core` (verified: 3
  hits in game `Core.u`, **0** in UED22 `core.u`).
- **So UED22's UCC builds the base package but not the DX driver → Hanfling's `hUCC` (matched Core
  with `Sprintf`) is genuinely required for the driver half.**
- **Candidate unblock WITHOUT `hUCC`:** teach the stubber to preserve function **declarations**
  (empty bodies) so `UedPreviewDX` can typecheck its call paths against a fuller `DeusEx` stub under
  UED22's UCC — it needs the signatures, not the `Sprintf`-dependent bodies. Open question whether the
  stubber can emit method decls without the bodies. (Alt: provision the Hanfling `edit/` set.)
- **Precompile + COMMIT `UedPreview.u`/`UedPreviewDX.u`** still needs ONE working v68 UCC (`hUCC`, or
  the stubber fix above) to do that first compile — so it's a fix, not a bootstrap.
- Harness scripts live in `_scratch/ucctest/` (gitignored → will be wiped); promote to
  `dev/docs/spikes/` + add an engine-fact regression (the `Sprintf` v68-Core divergence, the stub
  method-stripping) if this is pursued.
**(2) DinD asset-path visibility.** This box runs Docker-in-Docker; the daemon sees the repo tree but
NOT `~/Games` — a container mount of `~/Games/DeusEx` comes up EMPTY (verified: repo path → 93 files,
home path → 0). So `~/.uedcli [games.deusex].paths` MUST point at the in-repo `dev/games/deusex/`
(fixed 2026-07-21), not `~/Games`. `--native` didn't catch this (it's in-process/host-side). Worth
deciding whether uedcli should detect/repoint or document this for the global-CLI model, since
`~/Games`-style paths are the natural user choice and silently yield empty mounts under DinD.

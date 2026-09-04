# WanChai N=2: texture GROUP-name case comes from the editor's global FName pool, not the .utx

## Context

At N=2, WanChai's one brush references `Texture=CoreTexSky.ColorStars_A` / `CoreTexSky.NY_1`
(2-part, no group). Native re-attaches the group from `CoreTexSky.utx` and emits
`CoreTexSky.Sky.ColorStars_A` — the group name **`Sky`**, which is EXACTLY how that group's name is
stored in the `.utx` name table (verified: `CoreTexSky.utx` has FName `Sky`, capital S, on both the
game and substrate copies). The UED22 reference emits `CoreTexSky.sky.ColorStars_A` — lowercase
`sky`. This is the ONLY name/import diff on WanChai N=2, and it also flips every world-surf and
brush-poly texture ref (5+ residuals downstream of one string).

UE1 `FName` is case-INSENSITIVE for comparison but case-PRESERVING: the first spelling registered in
the process-global name pool wins, and later references reuse that entry's case. The editor's pool
has `sky` lowercase before it ever loads `CoreTexSky` — registered at boot by some earlier package
(`Core`/`Engine`/`DeusEx`/a startup `.utx`) — so its save emits `sky`. Native has no global pool; it
reads the group's real stored case from the `.utx`, which is `Sky`.

So the editor's `sky` is NOT derivable from the trunk or the referenced package alone. It is a
function of the editor's boot-time package-load order — process-global state, the same class of
artifact as the owner-excluded name-table tie order (`unbuilt-name-table-tie-order-is-first-reference`)
and the per-save-random masks.

The task handoff guessed the true stored name was lowercase `sky`; measurement shows it is `Sky`.
Per the incremental-lockstep instruction ("if a divergence turns out to require a NEW exclusion —
editor-nondeterministic — STOP and report; do not self-authorize"), this is parked for the owner.

## Proposed resolution (owner's call)

Options, not exhaustive:

- **Exclude it (fold name case into the parity bar's case-insensitive name compare).** Treat FName
  case as per-save engine state like the tie order: the gate already compares export/import
  IDENTITY; make the name-table + import-path comparison case-insensitive so `Sky`/`sky` match. The
  cost: the built `.dx` carries a group name in a different case than the editor's — game-inconsequential
  (FName lookups are case-insensitive), but no longer literal-byte-identical on that string.

- **Model the editor's global FName pool.** Seed native's name interner with the canonical
  lowercase/mixed spellings the editor registers at boot (from its startup package set), so the group
  name comes out `sky`. Correct but needs the boot-time pool captured and pinned as engine evidence,
  and it is unclear which package first registers `sky`.

- **Something else.**

## Answer

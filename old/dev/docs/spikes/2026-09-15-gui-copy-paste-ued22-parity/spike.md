# GUI clipboard-copy — real UED22 `EDIT PASTE` verification

Verifies `GET /api/level/{level}/actors/t3d` (`uedcli/serve/app.py`, the GUI's Cmd/Ctrl+C
clipboard-copy) against a REAL UnrealEd 2.2 instance, driven the production way
(`editor.ensure_editor`, `Driver.set_clipboard`/`edit_paste`).

> Salvaged from the unmerged `gui-t3d-clipboard-copy` branch (fd42b107) into board item
> `gui-copy-selected-actors-as-t3d-to-clipboard`: that branch's endpoint predates the 2026-09-23
> session/staging redesign and was never merged, but the finding below (the drift is uniform
> across actor kinds) is unaffected by that redesign and still holds.

## Method

`verify.py`: built a 2-actor level (an untextured additive cube brush `VerifyRoom` at
`Location=(500,300,200)`, and a `Light` point actor `VerifyLight` at `(1000,2000,300)` with
`LightBrightness=180`/`Tag=VerifySpike`), fetched its T3D via the REAL `create_app` route (the
exact code the GUI's fetch hits), then against a fresh ephemeral editor: `MAP NEW` → `MAP GRID
X=1 Y=1 Z=1` → `set_clipboard(t3d)` → `EDIT PASTE` → `MAP EXPORT`. Committed fixtures:
`fetched_from_endpoint.t3d` (the endpoint's own output) and `ued22_export_after_paste.t3d` (the
real editor's re-export after paste).

## Findings

1. **Both actors reappear with the right class, geometry, and properties.** `VerifyRoom` keeps
   its `CsgOper=CSG_Add`, all 6 poly faces (24 verts, matching winding/`TextureU`/`TextureV`), and
   its `Brush=Model'MyLevel.Model_VerifyRoom'` ref lands after the brush block, exactly as
   `t3d.md`/`emit.py` require for a selectable brush (the export shows `bSelected=True` and
   per-poly `Link=N`, i.e. it went through real CSG). `VerifyLight` keeps `Tag=VerifySpike` and
   `LightBrightness=180` verbatim.
2. **`Class=` re-exports bare, as `t3d.md` already documents.** The endpoint sends
   `Class=Engine.Brush` (uedcli's own qualified spelling); UED22 re-exports `Class=Brush`. Not a
   defect — `t3d.md` "`Class=Package.ClassName` binds on import ... export is always bare" already
   covers this; a naive class-string compare in this spike's own test script tripped on it before
   the fixture was read closely.
3. **NEW finding: the `EDIT PASTE +32uu drift` applies to EVERY actor in the pasted clipboard, not
   only brushes.** `quirks.md`'s existing "How brushes enter the level" section states the drift
   in a brush-only context (uedcli's own `writes._re_add` only ever pastes brushes — point actors
   go via `MAP IMPORTADD`, which does not drift — so this generalization was never exercised
   before). Measured here: `VerifyRoom` moved `(500,300,200)` → `(532,332,232)`, `VerifyLight`
   moved `(1000,2000,300)` → `(1032,2032,332)` — the identical `+32,+32,+32` on both a brush AND a
   plain point actor pasted together in one `Begin Map` blob.

## Why this settles the endpoint's design (no compensation)

The GUI endpoint (unlike `writes._re_add`) does not split a mixed selection into a `MAP IMPORTADD`
batch (points) + an `EDIT PASTE` batch (brushes) — a real human's Ctrl+C/Ctrl+V is ONE paste over
whatever mix of actors was selected, and `writes._re_add`'s split exists for uedcli's OWN
automated-materialize use case (exact placement), not because a mixed clipboard fails to paste.
This spike confirms a mixed clipboard pastes correctly as one operation, and that the endpoint
should NOT pre-shift by -32uu (`writes._shift_for_paste`'s trick): every actor in a real UED22
`EDIT COPY`/`EDIT PASTE` round trip already drifts by the same uniform `+32uu` on all three axes,
so the whole selection lands as a rigid group offset by that amount, preserving every actor's
position RELATIVE to the others — exactly the behavior a real UED22 user already gets from any
paste, and what "compatible with real UED22" means here (reproduce the native behavior, not mask
it). Pre-compensating would make a GUI-sourced paste behave differently from every other paste in
that editor, which would be the actual surprise.

## Flagged, not edited: `quirks.md` is incomplete on this point

Per this repo's `CLAUDE.md`, `dev/docs/unrealed/quirks.md` is not edited without the owner's
explicit yes. Proposed addition to "How brushes enter the level" → the `EDIT PASTE drift` bullet,
for the owner to approve:

> `EDIT PASTE` drift: +32uu on all three axes, on EVERY actor in the pasted clipboard — not
> brush-specific. Confirmed live 2026-09-15 pasting a mixed point-actor + brush clipboard in one
> `EDIT PASTE`: both drifted identically. `writes._re_add` never exercised this (it pastes only
> brushes; point actors go via `MAP IMPORTADD`, which does not drift).

## Regression

`uedcli/tests/test_engine_facts.py::test_edit_paste_drift_applies_to_every_actor_kind_not_just_brushes`
parses the two committed fixtures and asserts the `+32,+32,+32` drift on both actor kinds plus
brush-geometry/point-actor-property survival, so this fact can't silently regress.

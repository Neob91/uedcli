+++
priority = "p1"
kind = "implement"
summary = "actor preview: UnrealEd render parity — redefine `--faces textured` as the CSG-solved world (bspcsg core); collapse modes to wire+textured; black bg."
+++

# actor preview: UnrealEd render parity

Uses `build_geometry_bspcsg` (`uedcli-native/src/lib.rs:220`), already the default core for `native
materialize`. Not blocked on board item `incremental-bspbrushcsg-core` (byte-parity residuals, which
the owner ruled irrelevant for a visual preview) — that item chases byte-identical `UModel`; this needs
only the function as it stands, whose containment/visibility is already correct.

## Owner ruling (2026-08-01, revised 2026-08-02)

Prompted by a `--faces textured` demo that rendered three isolated add cubes floating in grey space.
The owner ruled: **the render needs UnrealEd parity.** Settled across the AskUserQuestion widget
(2026-08-01 to 08-02); the full set of build decisions is in [`spec.md`](spec.md) §Decisions:

1. **`--faces textured` is redefined to the CSG-solved textured world** (UnrealEd's PlainTex, mode 6):
   run the native CSG solve over the set, draw only the surfaces that survive, each through its real
   texture and authored UV frame — so an additive brush not inside subtracted space is invisible.
   Texture alignment across CSG splits is a hard requirement.
2. **`--faces` collapses to two values, `wire` + `textured`.** `flat` and the old CSG-free per-brush
   `textured` (UV inspector) are removed; no `uv` variant. This **revises** the 2026-08-01 wording
   above, which kept `textured` as the per-brush inspector.
3. **Black background for both modes**; the `wire` palette (`BG = 224`, `preview.py:485`) is re-tuned
   for black.
4. Movers draw as a magenta overlay; point actors keep their sprite overlay; the set is solved in
   isolation against a solid world; a zero-surface solve exits 2.

On landing this supersedes the grey-ground tuning assumed by board item
`four-actor-preview-faces-rulings-need-a-durable` (note it there), and needs an owner-approved
`direction/` home (no actor-preview topic exists yet).

## Why parity needs a real solve (evidence)

UnrealEd starts from a solid world; `Subtract` carves empty space; `Add` puts solid back **into**
empty space. A brush face renders only where solid meets empty. So "adds don't show unless inside a
subtract" is **not** a per-brush facing rule — it needs global spatial containment, i.e. a CSG solve
over the whole set, then render the resulting surfaces. Today `textured` approximates visibility
per-brush (subtract → far faces, add → near faces; `preview.py` cull) but never hides an add by
containment, because it has no world solve. The native engine that does the solve already exists
(`uedcli-native/src/bspcsg.rs`, exposed at `lib.rs`), and `level preview --native` already renders a
built world — so the mode is feasible offline; it largely reuses an existing native path.

The full design and every build decision are in [`spec.md`](spec.md). All four gate questions are
answered (see §Decisions there); their question files have been folded out.

## Not started. Spec is ruled and ready to plan; build needs a `direction/` home decision + a worktree.

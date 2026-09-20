# Spec — GUI P2 slice 1: move selected actors (staged, explicit Save)

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** Let a person move actors directly in the GUI's viewports — drag with Ctrl/Cmd held in
any of the four panes to translate the current selection — then explicitly **Save** the change into
the trunk. This is the first buildable slice of **P2 (editing)**, the phase `uedcli-human-gui/
spec.md` scopes but does not itself specify.

**Why.** P1 (read/audit) is built. The next real step toward "a person and the AI edit the same T3D
trunk interchangeably" is letting a human actually change something, starting with the simplest
possible edit (moving an actor) so the staging/Save/conflict machinery gets built and proven once,
not per edit-kind.

**Non-goals (this slice).**

- No rotate/scale — Location only.
- No property/inspector edits (typing a new value into a field).
- No actor create/delete.
- No atomic chained-verb transaction command — a single Save here commits one selection's worth of
  Location changes as one model-side write-path call; the multi-verb transaction idea stays parked
  (`uedcli-human-gui/questions/atomic-chained-verb-transaction.md`).
- No ortho grid-snap tuning beyond whatever the existing grid display already offers.

## Background — what exists, reuse

- **P1 GUI**: quad viewport, click-select, org panel, read-only inspector — all read-only.
  `web/src/scene/dragGesture.ts` already implements the tap-vs-drag threshold split and the
  perspective camera-nav button combos (LMB-drag = dolly+turn, RMB-drag = look, LMB+RMB-drag = pan).
  `e.ctrlKey || e.metaKey` is the established "additive" modifier check for multi-select
  (`dragGesture.ts:166`, duplicated in `web/src/panels/OrgPanel.tsx`) — both Ctrl and Cmd are
  accepted unconditionally on every platform; there is no `isMac`/OS-specific branching anywhere in
  `web/src/`.
- **The audit-snapshot store is DESIGNED, not yet built.** `uedcli-human-gui/spec.md`'s "Snapshots"
  section and `plan.md`'s Slice 3 table both describe it — a content-addressed dedup store under the
  gitignored `.uedcli/` (hash-keyed compressed actor blobs + a manifest `{timestamp, level,
  {actor-name → hash}, changed-count}`) — but `uedcli/serve/snapshots.py` does not exist yet; only
  Slices 1–2 of that plan have landed (`git log -- uedcli/serve/` shows no snapshot/diff work). The
  owner ruled (2026-09-14, `uedcli-human-gui/spec.md` "Deferred") that P2's staging buffer reuses
  this SAME store rather than `stash` (`stash_register.py`, a separate, user-facing, manually-named
  register) — but this item's plan must budget real work for the store's base mechanics (or wait on
  a Slice-3 dependency), not treat it as importable infrastructure.
- **The model-side write path** (`dev/docs/architecture.md` D1/D2): every CLI mutation verb is
  delete-then-readd-with-rollback — capture the actor's real block, delete, re-add, and on any
  failure restore the original plus swept neighbors. `level` only advances on success. This is the
  ONLY path a trunk write goes through, GUI included — no GUI-specific write mechanism.
- **Concurrency** (`dev/docs/direction/safety.md`): per-level `flock` around saves, plus
  detect-and-refuse (never silent loss) of a same-actor concurrent edit. The owner's principle: GUI
  and CLI share ONE concurrency behavior.
- **Why staging doesn't need a `direction/` change**: `dev/docs/rationale/gui-editing.md`.

## Interaction design

**Modifier.** `e.ctrlKey || e.metaKey` — matches the existing multi-select convention exactly, never
an OS-specific swap (confirmed 2026-09-20: this is also a better answer to "should macOS use Cmd
instead of Ctrl" than picking one — the existing code accepts both, everywhere).

**Perspective pane.** `Ctrl/Cmd+LMB`-drag / `+RMB`-drag / `+LMB+RMB`-drag — one axis per combo,
reusing the exact three button combinations camera-nav already uses, so holding Ctrl/Cmd repurposes
each existing combo from "move the camera" to "move the selection along one axis" instead. Which
combo maps to which of X/Y/Z is a build-time choice (not specified by the owner) — pick whatever
reads most naturally against the existing camera semantics (e.g. the combo that dollies the camera
forward/back moves the selection along the corresponding screen-forward axis) and document the
mapping in code once chosen.

**Ortho panes (Top/Front/Side).** `Ctrl/Cmd+LMB`-drag only — moves the selection along BOTH of that
pane's visible axes at once (an ortho pane only ever shows 2 of the 3 world axes, so no per-axis
combo distinction is needed there, unlike perspective's 3).

**Selection, not single-actor.** The drag can start ANYWHERE in the viewport, not only on a
selected actor's own rendered geometry, and moves the ENTIRE current selection together (one or
more actors), preserving each actor's position relative to the others. This mirrors how the
existing camera-nav drag is anywhere-in-viewport, not actor-anchored.

**Live preview, no per-frame write.** While dragging, the client computes and renders each selected
actor's new position optimistically (client-side only); nothing is written to the staging store or
the trunk until drag-end. Distinguishing this new gesture from (a) an unmodified camera-nav drag and
(b) a Ctrl+tap multi-select click reuses the SAME tap-vs-drag threshold `dragGesture.ts` already
uses — a Ctrl-held pointer-down that stays within the tap threshold is still a multi-select click; a
Ctrl-held pointer-down that exceeds it is an actor-move drag.

## Persistence

**Staging.** On drag-end (pointer-up), the moved actors' new Location values are staged: a snapshot
of just those actors is written into the audit-snapshot store, marked so it is distinguishable from
an audit snapshot of an external (AI or terminal) trunk change. The exact manifest shape for that
distinction (e.g. a `staged: bool` field, or a separate namespace within the same store) is left to
the implementation plan — not specified here, since it doesn't affect the interaction or Save/Load
semantics below.

**Save (explicit action) — per-property merge, mandatory explicit resolution on a real conflict
(owner ruling, 2026-09-20).** Applies every currently-staged actor into the trunk via the
model-side write path (D1/D2 — delete-then-readd-with-rollback). Before applying, `serve` re-reads
each touched actor's CURRENT trunk state and compares it PROPERTY BY PROPERTY against the state the
staged edit was based on — for this slice, the only staged property is `Location`:

- **No property overlap** (the trunk-side change, if any, touched a DIFFERENT property of that
  actor — e.g. an AI verb recoloured it while the human was dragging it) → merge automatically: the
  staged `Location` applies on top of the current trunk state, and whatever else the trunk-side
  change did to that actor survives untouched. No prompt. Clear the staged snapshot.
- **Same-property conflict** (the trunk ALSO changed `Location` for a touched actor since staging
  began) → Save does NOT proceed automatically and does NOT offer a blanket confirm-and-overwrite.
  It presents the conflicting actor(s) with BOTH values (the staged `Location` and the current trunk
  `Location`) and **requires the user to explicitly pick a resolution for each conflicting actor**
  (keep the staged move, or keep the trunk-side value) — there is no default/auto-pick. Whether a
  Save covering multiple actors applies the non-conflicting ones immediately while conflicting ones
  wait, or holds the whole batch until every conflict is resolved, is left open (see "Open" below;
  the per-actor wording in "Data flow" below describes the single-actor case only).

  **The per-property comparison itself is not yet a real mechanism.** This slice only ever stages
  one property (`Location`), so its "compare property by property" reduces to one field check — but
  no general property-diff/merge code exists yet (the closest existing building block, the semantic
  diff module, is `uedcli-human-gui/plan.md` Slice 3, also not built). Whether that narrower scope
  makes a Location-only comparison trivial to write directly, or whether it should reuse/anticipate
  the Slice-3 diff module, is a plan-time question — not decided here.

**Discard (explicit action).** Drops the staged snapshot without touching the trunk; the client
reverts the affected actors to the last-loaded trunk state.

**Load (existing P1 action, symmetric treatment).** `uedcli-human-gui`'s explicit Load action (per
`gui-explicit-rebuild-pinned-build-state-mode`) gets the same per-property-merge +
mandatory-explicit-resolution-on-conflict treatment in the other direction: if Load would pull in an
external `Location` change for an actor with an unsaved staged `Location` edit, it does not silently
overwrite the staged edit — it presents both values and requires an explicit pick per conflicting
actor. A trunk-side change to any OTHER property merges in automatically, same as Save.

## Data flow

1. User holds Ctrl/Cmd and drags in any pane → client computes new Location(s) for the current
   selection, previews locally (no network call yet).
2. Drag-end → client posts the new Location(s) to `serve` → `serve` writes a staged snapshot into
   the audit-snapshot store → responds ok. The viewport keeps showing the staged (moved) positions.
3. User clicks **Save** → `serve` re-checks each touched actor's `Location` against the current
   trunk:
   - no `Location` overlap (trunk-side change, if any, touched a different property) → merges
     automatically via the model-side write path, clears the staged snapshot, responds ok.
   - `Location` conflict → responds with the conflicting actor(s) and BOTH values; client shows a
     REQUIRED resolution UI (not a dismissible confirm) — the user must explicitly pick staged-or-
     trunk per conflicting actor. Once a given actor is resolved, its chosen value applies and its
     stage clears (single-actor case; whether a multi-actor Save applies non-conflicting actors
     immediately or waits for every conflict to resolve is open, see "Open" below).
4. User clicks **Discard** → `serve` clears the staged snapshot; client re-fetches/reverts to the
   last-loaded scene.
5. User triggers **Load** with a staged edit outstanding → same conflict check, symmetric UI.

## Error handling

- Same rule as P1: no Python exception reaches the user. A solve/write/staging failure returns a
  structured error naming the offending actor/value, never a bare traceback.
- A Save/Load conflict is not an error condition — it is an expected outcome with its own
  warn-and-confirm flow, distinct from a hard failure.

## Testing

- **Backend**: staged-edit write/read round-trip in the snapshot store; a no-overlap Save (trunk
  changed a DIFFERENT property while staged) applies the staged `Location` AND PRESERVES the
  trunk-side change to that other property — this is the specific silent-loss failure mode
  per-property merge exists to prevent, so it must be asserted explicitly, not just "Save applies
  cleanly"; a same-property (`Location`) conflict is reported, not auto-resolved, and does not apply
  until an explicit resolution is supplied; Discard clears the stage without touching the trunk;
  Load's symmetric no-overlap-merges / same-property-blocks behavior. Reuses the existing D1/D2
  rollback test pattern the CLI verbs already have — no second write-path implementation to test.
- **Frontend**: modifier detection (`ctrlKey || metaKey`) for the 3 perspective combos and the 1
  ortho combo; drag-to-preview math for a known input in each pane kind; the tap-vs-drag threshold
  correctly separates a Ctrl-held click (multi-select) from a Ctrl-held drag (move); Save/Discard UI
  wiring against a mocked backend, including the required-resolution dialog path (distinct from a
  dismissible confirm — verify it cannot be dismissed without an explicit staged-or-trunk pick).
- Scope tests to the touched module while iterating (`bin/test -k serve`, `web/`'s vitest run); full
  suite once before merge, per `dev/docs/rules/tests.md`.

## Open (resolve at plan time, not blocking this spec)

- Exact staged-snapshot manifest shape distinguishing a staged edit from an audit snapshot in the
  same store — plus, since the store itself isn't built yet (see "Background" above), whether this
  item's plan builds its base mechanics or the plan waits on that as a real dependency.
- Which perspective button combo (LMB/RMB/LMB+RMB) maps to which world axis — a build-time choice,
  document once picked.
- The existing camera-nav has a 4th combo, `Alt+LMB` = orbit-around-selection (`Viewport3D.tsx`),
  not covered by the owner's 3-combo decision. What `Ctrl/Cmd+Alt+LMB` does (nothing? a 4th
  axis-adjacent behavior?) is undecided — resolve at plan time, defaulting to "no special behavior,
  falls through to whichever of Ctrl+LMB or Alt+LMB the input layer checks first" unless that reads
  as broken in practice.
- A Save covering a multi-actor selection where only SOME actors conflict: does the non-conflicting
  subset apply immediately while the conflicting ones wait on resolution, or does the whole batch
  hold until every conflict is resolved? Not specified by the owner's ruling — resolve at plan time.

## Refs

- `dev/docs/board/to-plan/uedcli-human-gui/spec.md` (P1 spec; "Deferred" section scopes P2 and
  carries the settled persistence/conflict-handling ruling this spec builds on).
- `dev/docs/board/to-plan/uedcli-human-gui/questions/atomic-chained-verb-transaction.md` (parked,
  out of scope here).
- `dev/docs/rationale/gui-editing.md` (why P2 doesn't need a `direction/trunk-and-editor.md`
  amendment).
- `dev/docs/architecture.md` (D1/D2 write pattern); `dev/docs/direction/safety.md` (flock +
  refuse-same-actor rule; the GUI's audit-snapshot-store exemption).
- `web/src/scene/dragGesture.ts`, `web/src/scene/selection.ts`, `web/src/panels/OrgPanel.tsx`
  (existing modifier-key + tap-vs-drag conventions this slice reuses).
- `uedcli-human-gui/plan.md`'s Slice 3 table (the audit-snapshot store's design — not yet built;
  this item's plan must account for that).

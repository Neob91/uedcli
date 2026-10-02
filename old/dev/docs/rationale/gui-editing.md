# GUI editing (P2) — why it stays out of `direction/`

**Owner ruling (2026-09-20): P2 editing does not need a `direction/trunk-and-editor.md` amendment —
it folds into this spec + this file.** This file records the engineering reasoning for why that
ruling holds, the way `preview.md` separates an owner's product ruling from the engineering under
it. Revised in place — agents maintain this freely.

---

## Staging + explicit Save is not a new direction — it's one more writer on the existing trunk write path

`direction/trunk-and-editor.md`'s claim is about what the trunk IS and how it reaches a build: a
git-tracked T3D tree is the single source of truth, the real editor (or `uedcli-native`) is a build
tool invoked on demand, and merging competing edits is git's job, driven by the user in the
terminal — never orchestrated by uedcli itself. None of that changes when a human edits through the
GUI instead of the CLI.

**Why it is this way.** A GUI edit still lands in the trunk only through the same model-side write
path every CLI verb already uses (delete-then-readd-with-rollback, `architecture.md` D1/D2), under
the same standing `safety.md` flock + refuse-same-actor-concurrent-edit rule — the owner's explicit
principle that the GUI and CLI share ONE concurrency behavior, no GUI-specific mechanism. Staging
(accumulating an unsaved edit before an explicit Save) is a client-side/`serve`-side UX detail about
*when* a write reaches that path, not a different path or a different merge authority. AI edits
still hit the trunk instantly; git still stays git, driven by the user; the GUI still never creates
branches, orchestrates worktrees, or merges. Nothing `direction/trunk-and-editor.md` states is
falsified by adding a second, slower-triggered writer that funnels into the identical mechanism.

**What would have crossed the line, and didn't get proposed.** A GUI-side merge algorithm
overriding git's own merge; a GUI-driven branch/worktree/commit flow (already explicitly rejected as
its own P1 ruling — "GUI shows git, never drives it"); a separate GUI-only concurrency primitive
instead of the standing flock rule. Any of those would be a real intent change and would need a
`direction/` amendment with the owner's yes and a `Confirmed:` trailer. Staging + explicit Save,
warn-and-confirm on a save/load conflict, is not — it's the kind of routine ruling `CLAUDE.md`
describes folding into the item's own `spec.md` instead.

**Refs.** `dev/docs/direction/trunk-and-editor.md`; `dev/docs/direction/safety.md` (flock +
refuse-same-actor-edit; the GUI audit-snapshot-store exemption); `dev/docs/architecture.md` (D1/D2
write pattern); `dev/docs/board/to-plan/uedcli-human-gui/spec.md` "Deferred" (the P2 persistence
ruling this reasons about); `dev/docs/board/done/gui-p2-actor-translate-ctrl-drag/` (P2's first
slice, built on this).

---

## The GUI backend never special-cases a subset of actor properties

**Owner ruling, this spec round (`gui-builder-brushes`): `Location`/`Rotation` — or any property —
must be exposed and edited through one generic mechanism, never a dedicated field or endpoint per
property.** Recorded here because it is a standing convention for all future GUI/`serve` work, not
just the item that surfaced it.

**Why it is this way.** The model/CLI layer already treats every property uniformly: `actor prop set`
reaches `Location` through `propedit`'s typed-field registry (`uedcli/propedit/fields.py`,
`TYPED_FIELDS`) and `Rotation` as an ordinary struct-typed prop — it isn't even in that registry —
through the same plan/apply path (`uedcli/propedit/edit.py`). There is no model-side reason for the
GUI to fork them apart; doing so only duplicates validation logic (Decimal precision, the `PrePivot`
invariant D8) that already lives in one place, and makes every future property (a new struct field, a
new typed field) require its own new GUI endpoint instead of working automatically through the
existing generic path.

**What already violates this, not yet fixed.** `uedcli/serve/scene.py`'s `SceneActor` carries
dedicated `location`/`rotation` fields separate from its generic `props` list; `StagingStore`
(`uedcli/serve/snapshots.py`) stages `Location` moves specifically, with baseline/conflict machinery
keyed to that one field. Both predate this ruling and are known debt, not a pattern to copy — tracked
at `dev/docs/board/inbox/sceneactor-special-cases-location-rotation/` (p1).

**How to apply.** Any new GUI/`serve` route that reads or writes an actor property — the builder
brush's own `prop` route (`dev/docs/board/to-spec/gui-builder-brushes/spec.md`), a future inspector,
any later editing slice — goes through one generic prop path mirroring `propedit`'s plan/apply, never
a per-field endpoint or a per-field response field.

**Refs.** `uedcli/propedit/fields.py`, `uedcli/propedit/edit.py`; `dev/docs/rationale/propedit.md`;
`dev/docs/board/to-spec/gui-builder-brushes/spec.md`; `dev/docs/board/inbox/sceneactor-special-cases-
location-rotation/`.

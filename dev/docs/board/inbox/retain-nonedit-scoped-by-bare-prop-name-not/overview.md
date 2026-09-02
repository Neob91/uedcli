+++
priority = "p1"
kind = "debug"
summary = "_RETAIN_NONEDIT scoped by bare prop name, not declaring class"
+++

# _RETAIN_NONEDIT scoped by bare prop name, not declaring class

Owner asked for this at p0; board's priority vocab tops out at `p1` (highest), so filed there.

## Owner's finding

While investigating the `[[level-import-reimport-writes-non-editable-props]]` item (`MyMarker` not
editable, comes from Build Paths), the owner pointed out that `normalize.py`'s
`_RETAIN_NONEDIT = frozenset({"prepivot", "keypos", "keyrot"})` matches by BARE property name only
— across every class, not scoped to the specific classes UnrealEd's special editors (pivot tool,
keyframe tool) actually apply to. Ruling: it should key on `(Engine.Mover.KeyPos,
Engine.Mover.KeyRot, Actor.PrePivot)` — i.e. the declaring class, not just the name.

## Verified

- Confirmed via a live schema read (`classdefaults.ClassDefaults.for_class`, `dx_lum` project):
  `KeyPos`/`KeyRot` are declared by `Engine.Mover` (`owner=Engine.Mover`, `editable=False`);
  `PrePivot` is declared by `Engine.Actor` (`owner=Engine.Actor`, `editable=False`) — matching the
  owner's ruling exactly (module the `Engine.` package qualifier on `Actor`).
- The only call site of `is_authored_prop` (`normalize.py`'s `_actor_values`, the post-verify
  compare path) already computes `owner = info.owners.get(key[0])` one line above the call — the
  owner-class info was already available there, just not threaded into the match.

## Fix (implemented this session, uncommitted as of filing)

`uedcli/normalize.py`:
- `_RETAIN_NONEDIT` is now `frozenset[tuple[str, str]]` keyed on `(declaring class casefold, prop
  name casefold)`: `{("engine.actor", "prepivot"), ("engine.mover", "keypos"), ("engine.mover",
  "keyrot")}`.
- `is_authored_prop` gained an `owner_casefold: str | None = None` keyword param; the exception
  only matches `(owner_casefold, name_casefold) in _RETAIN_NONEDIT`. No owner known (`None`) ->
  exception can't match, falls through to the plain editable check (never a false positive from a
  missing owner).
- The one call site now passes `owner_casefold=owner.casefold() if owner else None`.

Tests: extended `test_edit_rule_strips_non_editable_keeps_authored_and_special_editors` with the
per-class-scoping cases (same bare name under an unrelated class -> NOT retained; no owner known ->
NOT retained), and added `test_retain_nonedit_scoping_end_to_end_via_compare_view` — a full
`compare_view`/`StubDefaults` integration test proving `Engine.Mover.KeyPos` is distinguished
(present vs. absent -> not equal) while the same bare name under an unrelated stub class is dropped
(present vs. absent -> equal, the actual bug scenario). Full suite run pending at time of filing —
see this item's own status once merged.

## Scope note

This fixes the COMPARE-side rule's precision. It does NOT by itself fix `MyMarker`-style actors
disappearing on `level import`/materialize — that's the separate, larger, NOT-yet-implemented
change tracked in `[[level-import-reimport-writes-non-editable-props]]` (wiring `is_authored_prop`
into `mapimport.py::render_actor`'s write path at all, which today applies zero filtering). This
item only makes the EXISTING exception-list mechanism precise before that larger change reuses it.

+++
priority = "p2"
kind = "implement"
summary = "GUI Inspector: editing (write-back for props + surfaces)"
depends-on = ["gui-inspector-effective-props-search-show-all"]
+++

# GUI Inspector: editing (write-back for props + surfaces)

Sketched at the design level during the 2026-09-22/23 conversation that produced
`dev/docs/board/to-plan/gui-inspector-effective-props-search-show-all/` — the read-only sibling
this item extends. Deliberately never written up as its own reviewed spec: it's not ready to spec
until the in-flight "Persistent GUI Editing Sessions" staging rewrite lands (as of 2026-09-23 that
rewrite exists only as an unmerged plan, `docs/superpowers/plans/2026-09-22-persistent-gui-editing-
sessions.md`, in a separate `gui-sessions-brainstorm` worktree not yet squash-merged — check whether
it has landed/moved to the board before speccing this for real). Parked here so the reasoning below
isn't lost to chat scrollback in the meantime.

## Scope

Real `<select>`/typed `<input>` write-back for actor properties, and — separately, with no existing
precedent at all — surface (texture) field editing. Both are explicitly out of scope in the
read-only spec; this item is where that scope goes once unblocked.

## Actor property editing — reuses existing, working machinery

- Server-side validation and mutation reuse `uedcli/propedit/edit.py`'s `plan_edit`/
  `validate_leaf_value` directly — the SAME engine `actor prop set` already uses in production
  (typed, validated: enum-name validation, numeric range/format rejection, struct-member set/unset).
  The GUI's job is to turn one Section-2-shaped edit (a typed input committing) into a `PropToken`,
  call `plan_edit`, and stage the result — not to reinvent validation.
- **Staging/conflict generalization needed.** `uedcli/serve/edits.py`'s `StagingStore`/
  `save_staged`/`check_load_conflicts` currently model ONE staged fact per actor:
  `{baseline_location, staged_location}`, and conflict detection compares the actor's whole current
  `Location` against that one baseline. This needs to generalize to a per-actor `{prop_key:
  (baseline_value, staged_value)}` dict, with conflict detection PER PROP KEY — so staging one
  property on an actor doesn't false-conflict (or silently overwrite) when a DIFFERENT property on
  the same actor changed upstream in the meantime. This is real, nontrivial rework of `edits.py`'s
  core data model, not a small addition — likely the bulk of this item's actual work, and exactly
  the layer the sessions rewrite is also replacing, hence the dependency.
- **Typed inputs**, built directly on the read-only spec's `EffectiveProp` discriminated union —
  no new type design needed, just a write affordance per variant already modeled: `enum` → a
  `<select>` populated from `ScenePayload.enums[enum_type]`; `bool` → an enabled checkbox (currently
  spec'd disabled, read-only); numeric kinds (`float`/`int`/`byte`) → an `<input>` with client-side
  numeric validation for responsiveness, but `plan_edit`/`validate_leaf_value` stays the server-side
  source of truth — never trust client validation alone. **A "reset to default" action is NOT free
  (correction, found during plan review of the read-only sibling, 2026-09-23):** the read-only
  spec's `default_value` is resolved via `propedit.edit.effective_value`'s stored→default→zero
  cascade, which returns the STORED value when the actor already states one — so on an
  already-explicit property, `default_value` is just `stored_value` again, not the true
  actor-independent class default. A real "reset to default" needs its own class-only resolution
  (the `classdefaults`/`typedprops` path the read-only spec deliberately avoided, for unrelated
  reasons — see that spec's Open Question about `ABSENT` reachability), not a field this item can
  assume is already sitting there.
- `Location`/`MainScale`/`PostScale` writes go through `propedit.TYPED_FIELDS`
  (`TypedField`/`ScaleField`) the same way the read-only spec's resolution does — not the generic
  `plan_edit` path, matching how `propedit` itself dispatches these three today.

## Surface (texture) editing — no precedent, biggest open unknown

The read-only spec's per-member struct/array design has a direct write-side analogue for actor
props (above); surfaces have nothing equivalent to extend. The natural shape mirrors actor props
(a `plan_edit`-equivalent validation step, a per-`(actor, polyIndex)` staged record generalizing
`edits.py`'s per-actor model the same way), but the actual trunk write TARGET is a brush's authored
`Polygon` list, not a top-level actor prop — needs its own design pass reading `dev/docs/unrealed/
t3d.md`'s polygon property forms and `uedcli/surface.py`'s existing `apply_surface_edit` (a working
precedent for `--texture`/flag mutation today, just not staged/conflict-aware) before this is a real
spec, not a sketch. Flagged as the biggest unknown in this item, not resolved here.

## Next step when picked up

1. Confirm the sessions/staging rewrite's actual landed shape (may have changed `edits.py`'s API
   entirely by then — don't assume the per-actor-location model described above still exists).
2. Write a real spec (this item is a sketch, not one) for actor-prop editing first — it has a clear
   existing-machinery path. Surface editing likely wants its own follow-on item once the actor-prop
   editing pattern is proven, rather than both being designed and reviewed in one pass.

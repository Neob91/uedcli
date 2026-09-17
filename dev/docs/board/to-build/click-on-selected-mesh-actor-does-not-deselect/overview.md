+++
priority = "p1"
kind = "debug"
summary = "clicking a selected mesh actor (even alone, no ctrl/cmd) should deselect it -- currently a no-op, like the already-fixed poly case"
+++

# Click on a selected mesh actor does not deselect it

Clicking a currently-selected mesh actor (static mesh) does not deselect it. Same behavior gap as
`click-on-a-selected-poly-does-not-deselect-it` (done earlier this campaign), extended by the owner
to mesh actors: a single selected mesh actor should be DESELECTED when clicked again, even without
ctrl/cmd.

## Where to look

`web/src/App.tsx`'s `onSelectActor` (around line 97-98):
```
const onSelectActor = useCallback((name: string, additive: boolean) => {
  setSelectedNames((s) => toggleSelection(s, name, additive))
```
calls `toggleSelection` WITHOUT the `deselectSole=true` fourth argument, unlike `onSelectSurface`
right below it (line ~104) which already passes `true` for exactly this behavior on polys. The
`selectionSet.ts` `toggleSelection` mechanism (the `deselectSole` param) already exists and is
already tested (`QuadLayout.test.tsx`) -- this is very likely a one-argument fix at the actor-select
call site, not new mechanism.

## Scope question worth checking, not assuming

The earlier poly fix's own doc comment says actor selection's no-op-on-reselect was "documented"
behavior at the time -- confirm there isn't a reason (a different actor-selection UX convention, a
marquee/multi-select interaction) that deliberately kept actors out of this before assuming it's a
simple oversight. If there's a real reason, ask; if it just wasn't scoped into the original poly fix,
implement it the same way (`deselectSole=true` on the actor path too), possibly scoped specifically to
mesh actors per the owner's wording ("clicking a selected mesh") rather than all actor kinds -- verify
with the owner if uncertain whether this should apply to ALL actors (point actors, brushes-as-actors,
movers, etc.) or specifically mesh actors, since only mesh actors were mentioned.

## Repro

1. Select a static mesh actor.
2. Click it again (no ctrl/cmd).
3. Expected: it becomes deselected. Actual: it remains selected (no-op).

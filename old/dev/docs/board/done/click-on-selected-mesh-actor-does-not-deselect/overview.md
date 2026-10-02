+++
priority = "p1"
kind = "debug"
summary = "clicking a selected mesh actor (even alone, no ctrl/cmd) should deselect it -- currently a no-op, like the already-fixed poly case"
+++

# Click on a selected mesh actor does not deselect it

Fixed: `App.tsx`'s `onSelectActor` now passes `deselectSole=true` to `toggleSelection`, same mechanism
the poly fix (`click-on-a-selected-poly-does-not-deselect-it`) already added. `onSelectActor` is the
single shared path for every actor kind (mesh, point, brush, mover) across both viewport panes, so the
fix applies uniformly, not scoped to mesh actors only -- checked, not assumed (`OrgPanel`'s own
batch-select uses a separate mechanism, untouched). Additive/Ctrl toggle and reselecting a different
actor are unaffected. Reviewed with real synthetic clicks (select, reselect-to-deselect, Ctrl toggle,
miss-click, different-actor reselect) against a live headless-browser instance.

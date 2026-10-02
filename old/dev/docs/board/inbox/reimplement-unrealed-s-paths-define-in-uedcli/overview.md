+++
priority = "p2"
kind = "implement"
summary = "Reimplement UnrealEd's `PATHS DEFINE` in uedcli"
+++

# Reimplement UnrealEd's `PATHS DEFINE` in uedcli

Build the AI navigation network
(reachspecs between `PathNode`/`NavigationPoint` actors) natively, the way the editor's `PATHS DEFINE`
console command does, so pathnoding is drivable offline instead of only via the editor. Needs a spike
to decode what `PATHS DEFINE` actually computes/emits (reachspec fields, connectivity/collision
probing, which actor classes participate) before it can be specced.

+++
priority = "p3"
kind = "owner-question"
summary = "N-4 light participation + radius are a HEURISTIC (no CDO read)"
+++

# N-4 light participation + radius are a HEURISTIC (no CDO read)

p3. `materialize._participating_lights` decides a light contributes to the bake by `LightType !=
LT_None` from the trunk props, falling back (when `LightType` is absent) to "carries a light prop
or is a `*Light` class"; missing `LightRadius` defaults to **64** (world radius `(64+1)*25=1625`).
The CORRECT source for both is the class **default object (CDO)** in the game `.u` — the type-only
schema (`uprops`) carries prop *types*, not default *values*. Fine for lights with explicit props
(the common case + the test maps), but a light relying on class-default `LightType`/`LightRadius`
is guessed. Fix when a CDO-default reader exists (also wanted for the materialize default-value
omission gap). Non-blocking while lit render is gated anyway (see the N-4 handoff).

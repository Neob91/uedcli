+++
priority = "p3"
kind = "implement"
summary = "native lighting backface cull assumes SINGLE-SIDED surfaces (`light.rs::light_in_front`, §20 §17)"
+++

# native lighting backface cull assumes SINGLE-SIDED surfaces (`light.rs::light_in_front`, §20 §17)

p3 native lighting backface cull assumes SINGLE-SIDED surfaces (`light.rs::light_in_front`,
§20 §17). A `PF_TwoSided` surface renders its one lightmap from BOTH faces, so the editor may
legitimately list a back-side light on it; the strict `(light-base)·normal > 0` cull would drop it,
darkening that surface vs the editor. `Test_Castle` has no such case (0/3497 back pairs), so it's a
latent generic-UE1 gap, not a castle regression. Needs an oracle map WITH a lit two-sided surface to
see what `shadowIlluminateBsp` actually does before adding a `PF_TwoSided`-bypass — do NOT guess.

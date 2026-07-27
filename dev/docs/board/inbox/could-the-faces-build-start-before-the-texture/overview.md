+++
priority = "p2"
kind = "owner-question"
summary = "Could the `--faces` build start before the texture decoder lands?"
+++

# Could the `--faces` build start before the texture decoder lands?

Decision 2.11 says the decoder item builds first, then all of the `--faces` work, and
[`plans/2026-07-27-actor-preview-faces-plan.md`](../../../plans/2026-07-27-actor-preview-faces-plan.md)
implements that ordering as ruled. **Observation only, not acted on:** of that plan's five
slices, only **S4** (`textured`) actually consumes the decoder's new accessor. S1 (a pure
refactor), S2 (`--faces` + the `flat` mode) and S3 (`--focus`) touch no texture code at all —
`flat` reads no textures. So S1–S3 could land earlier or in parallel, which would get the
subtract-cull diagram (the thing that makes a subtracted room's interior visible) into your
hands sooner. Reordering is your call, not the agent's. *(2026-07-27.)*

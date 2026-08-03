# Could the `--faces` build start (S1–S3) before the texture decoder lands?

## Context

Decision 2.11 says the decoder item builds first, then all of the `--faces` work, and this plan
implements that ordering as ruled. Observation only, not acted on: of the plan's five slices, only
**S4** (`textured`) consumes the decoder's new accessor. S1 (a pure refactor), S2 (`--faces` + the
`flat` mode) and S3 (`--focus`) touch no texture code at all — `flat` reads no textures. So S1–S3
could land earlier or in parallel, getting the subtract-cull diagram (what makes a subtracted room's
interior visible) into the owner's hands sooner. Reordering is the owner's call, not the agent's.
(2026-07-27.)

## Answer

<!-- Empty = open. Write the decision here. -->

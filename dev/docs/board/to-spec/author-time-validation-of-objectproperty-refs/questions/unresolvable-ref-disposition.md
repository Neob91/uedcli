# A bare/unqualified object ref, or one whose kind cannot be checked — exit 2 or skip?

## Context

Most object refs are qualified with a class token and package (`Sound'AmbientSounds.Machine1'`) and
validate cleanly. Two residual shapes need a ruling:

- **Bare / unqualified ref** (`AmbientSound=Machine1`, no package). `TextureResolver.exists` treats a
  bare name as "exists in ANY package on the path" (`utexture.py:890`) — tolerant, because existence
  tolerates ambiguity. Apply the same tolerance to object refs (check any package), or require
  qualification and exit 2 on a bare one?
- **A ref whose class token names a kind we cannot enumerate offline** (an obscure or embedded
  object type). Exit 2 naming it (house rule: "any `<package>.<name>` resource that cannot be
  resolved is an ERROR", `conventions.md`), or skip it as unvalidatable?

Recommendation: mirror `TextureResolver` — a bare name checks any package (tolerant), and a
qualified ref that resolves to nothing on the path is a hard exit 2. `MyLevel.*` / null are always
skipped (covered in the spec). Confirm, or tighten bare refs to a hard error.

## Answer

<!-- Empty = open. -->

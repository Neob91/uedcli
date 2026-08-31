# level materialize

**`level materialize`** is the pure build step: it drives **UnrealEd** to compile the selected
level's T3D trunk into the `.dx`/`.unr` **build artifact** — map-file output only (the T3D tree is the
source, reached via git, not a build target).

```
level materialize [--out OUT] [--overwrite] [--no-verify] [--keep-build] [--no-bsp-check]
```

- **`--out OUT`** names the destination map file (`.dx` or `.unr`). It **refuses to overwrite an
  existing file** (exit 2) unless **`--overwrite`** is given.
- A **post-build verify** (H3) confirms the rebuilt map matches the intended trunk; **`--no-verify`**
  skips it (debugging / known-buggy verify), and **`--keep-build`** copies the built map to the
  project's `.uedcli/tmp/` on a verify FAILURE instead of discarding it.
- Before any editor work, materialize checks that every package the level **references** (via a
  qualified `Class=` or a face's `Texture=`) is present on the configured package path. If any is
  missing it **exits 2 naming the complete set** and writes nothing, rather than silently dropping
  those references. This gate runs even under `--no-verify`. A composed package path that resolves to
  **0 packages** prints one advisory line but does not block a level that references nothing.
- The verify compares the built map against the trunk in UnrealEd's own terms, so it needs each actor
  class's **defaults** out of the game's `.u` packages. They are resolved *before* the editor starts,
  so an actor whose `Class=` is not fully qualified (`Package.Class`) — or whose package is missing
  from the configured paths — **exits 2 in about a second**, naming the actor and class, instead of
  failing after a full build. `--no-verify` does not need them.
- After a successful build+save, materialize runs two **advisory BSP health checks** and prints any
  findings to **stderr** — the exit code stays **0** (these report on an already-good build; they
  never fail it). The **build-output** check parses UnrealEd's own rebuild warnings (dropped faces,
  unlinked T-junction sides, sliver nodes) into counts; the **built-model** check reads the saved map
  and locates a defect the static `level doctor` cannot: **invisible walls** (near-zero-area BSP
  nodes). A check that cannot run (editor wedged, unreadable map) prints one "skipped" line and
  the build still succeeds. **`--no-bsp-check`** turns both off.
- Committing is your own `git`. Lightmaps and rebuilt BSP are **regenerable build output**, never
  part of the level's identity.

*(A native, in-process Rust build is under development, targeting byte-identity with UnrealEd's build
of the same trunk; the editor path above remains the current one.)*

See also: [`level doctor`](doctor.md), [`level photo`](photo.md).

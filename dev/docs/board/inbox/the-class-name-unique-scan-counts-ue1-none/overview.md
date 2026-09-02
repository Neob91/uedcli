+++
priority = "p?"
kind = "debug"
summary = "The class-name-unique test counts UE1 'None' exports as a class name, so it fails on any configured install"
+++

# The class-name-unique scan counts UE1 'None' exports as a class name

`test_native_materialize.test_class_names_are_unique_across_the_deusex_package_set` FAILS whenever a
`~/.uedcli/config.toml` is present, on a legitimate game-package set:

```
class name defined in multiple packages (breaks first-hit): {'none': ['core', 'fire']}
```

The scan's `class_of_export(i) in (None, "Class")` arm matches exports whose name is UE1's `None`
sentinel, not just real UClass exports, so every package carrying one collides with every other on
`'none'`. **That is a defect in the test's own scan, not in the game content — and it masks the real
assertion**, which is that no genuine class name is defined in two packages.

With no `~/.uedcli/config.toml` the test skips, so it is invisible on an unconfigured machine.

Found while running `bin/test` for the `actor diagram --faces` S1 slice; **unrelated to that slice**
(reproduced against a pristine `git archive HEAD` copy with the S1 diff absent).

**Not a finding:** an earlier draft of this item also reported
`{'allhongkongdeco': ['DeusExDeco', 'UED2_FIXM_p1']}` and treated a fix pack shadowing a game class
as a hazard to `pkgref.build_class_package_index`'s first-hit `setdefault`. That collision was an
artifact of pointing `games.deusex.paths` at `uned/UED22/` — the **UnrealEd 2.2 editor install**,
which is not a game package dir and carries editor-only packages plus the `UED2_FIXM_p1` fix pack.
Curating the path to the game packages alone makes it disappear. Recorded here so nobody re-derives
it as a resolver defect.

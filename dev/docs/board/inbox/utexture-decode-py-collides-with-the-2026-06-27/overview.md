+++
priority = "p2"
kind = "owner-question"
summary = "The god-module split's utexture_decode.py name shadows the spike harness module of the same name"
depends-on = ["refactor-god-modules-into-cohesive-units"]
+++

# `utexture_decode.py` collides with the 2026-06-27 spike harness module name

Slice 1 of `refactor-god-modules-into-cohesive-units` — moving `utexture.py`'s decoder half into
`uedcli/utexture_decode.py` — was built, measured and then REVERTED. It reddens two tests, and every
fix available touches something the item is not allowed to touch. The split itself is correct; only
the file NAME is the problem, and the name is fixed by that item's `spec.md`.

## The mechanism

Three things line up:

1. `uedcli/tests/test_preview_batch.py:17` puts the package directory `uedcli/` itself on
   `sys.path`, at import time, for the whole pytest session. It is deliberate: the baked container
   script `uedcli/game/preview_batch.py` does a bare `import preview_shots`, and
   `preview_shots.py` sits in `uedcli/`. So after collection, **every top-level module in
   `uedcli/` is bare-importable**.
2. The committed spike harness
   `dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness/utexture_decode.py` is imported by
   bare name — `dev/docs/spikes/2026-07-15-native-materialize/harness/line_check.py:45` does
   `import utexture_decode as UT`.
3. `line_check.py:42` computes its own search path from a HARDCODED absolute
   `ROOT = /home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli`. Where that path does not
   resolve (any checkout that is not the owner's own — a container, a CI box, this worktree), the
   insert at `line_check.py:44` adds a non-existent directory and the bare import falls through to
   the next `sys.path` entry.

Before the split that fall-through ended in `ImportError`, and
`test_native_materialize._load_line_check` turned it into a SKIP naming the spike env. With
`uedcli/utexture_decode.py` present it now RESOLVES — to uedcli's module, which has no
`load_package` — so `test_box_sweep_lands_on_native_floor` and
`test_point_below_floor_is_solid_after_hulls` fail at `line_check.py:67` with
`AttributeError: module 'utexture_decode' has no attribute 'load_package'`, instead of skipping.

Reproduced directly:

```
sys.path.insert(0, "<repo>/uedcli")                                    # test_preview_batch.py:17
sys.path.insert(0, "<repo>/dev/docs/spikes/2026-07-15-native-materialize/harness")
import utexture_decode          # -> <repo>/uedcli/utexture_decode.py
```

On the owner's own machine `ROOT` resolves, the spike's file wins, and slice 1 is clean — so this is
environment-dependent, in the same class as `test_driver.py`'s `/host/out/` failure. It is still a
live shadowing hazard rather than a one-off: any future top-level module added to `uedcli/` whose
name matches a spike-harness module has the same problem.

## Why it was not fixed in place

Every available fix is out of that item's scope, and two of them need a ruling:

- **Rename the new module** (`utexture_pixels.py`, `texdecode.py`, …). `spec.md` argues explicitly
  for `utexture_decode.py` over `utexture_codec.py`; picking a third name is a design change, not an
  implementer's call.
- **Fix `test_preview_batch.py:17`** to stop putting `uedcli/` on `sys.path` (e.g. load
  `preview_shots` by path the way it already loads `preview_batch`). Editing a test so the change
  goes green is exactly what the item's brief forbids, and this one is not obviously wrong on its
  own terms.
- **Fix the spike harness's dead hardcoded `ROOT`** — `dev/docs/spikes/` may not be edited without
  the owner's yes (`CLAUDE.md`).

## Answer

<!-- Empty = open. Write the decision here. -->

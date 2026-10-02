+++
priority = "p3"
kind = "debug"
summary = "GiveMeItems blocked by missing PCX texture asset"
+++

# GiveMeItems blocked by missing PCX texture asset

Follow-on to `givemeitems-blocked-by-inherited-member-access` (now `done/`, the inherited-member-
variable gap is fixed). Retried the real `GiveMeItems` package
(https://github.com/jpiedra/GiveMeItems) against the UT99 substrate via `compile_package_dir`, all
8 classes together. It no longer hits the member-variable gap — confirmed by compiling
`GMIClientWindow.uc` alone (its `#exec TEXTURE IMPORT` line stripped): it now gets all the way past
`Created()`'s `WinWidth`/`WinHeight` reads and only fails on `GMIPageWindowA`, an unresolved
same-package cross-class reference — expected for a single-class compile, not a bug.

Compiling the full 8-class package hits a different, unrelated blocker first:

```
NotImplementedError: #exec TEXTURE IMPORT: PCX file not found: 'Textures\GMIBACKGROUND.PCX' (have [])
(class 'GMIClientWindow')
```

`GMIClientWindow.uc` has `#exec TEXTURE IMPORT NAME=GMIBackGround FILE=Textures\GMIBACKGROUND.PCX
LODSET=0`, but the GitHub mirror ships no `Textures/` directory — only the `.uc` sources, the
`.int`, and the prebuilt `GiveMeItems.u`. The real PCX asset isn't in the repo to compile against.

Not attempted: synthesizing a stand-in PCX. `dev/docs/spikes/2026-09-13-texture-import-re/harness/pcx.py`
has a working encoder (`make_pcx(pixels, palette)`), so this is possible — the open question is
whether a synthesized stand-in is an acceptable substitute for the real, missing asset, since it
isn't the real source-in-source-tree case `#exec TEXTURE IMPORT` targets. Not forcing a fit; left for
whoever picks this up to decide, or whether `GiveMeItems` just isn't a usable corpus package without
its missing asset.

+++
priority = "p2"
kind = "debug"
summary = "Clean MAP IMPORT crashes the editor container regardless of level size"
+++

# Clean MAP IMPORT crashes the editor container regardless of level size

An earlier attempt (`/tmp/export-order-experiment/`) tried to answer
`board/inbox/unrealed-geometry-build-map-rebuild-bsp-rebuild/spec.md` §12.1's open question — is a
clean `MAP IMPORT`'s export/import table order deterministic and trunk-derivable? — using a real
915-export retail level (`02_NYC_Bar.dx`, 627 KB). The editor container's whole process tree died
(not a wedge — `docker exec` came back exit 128, "no such container") twice, at ~40s and ~330s into
`MAP NEW` -> `MAP IMPORT` -> `MAP SAVE`, before either clean-import save could be produced.

This round retried with much smaller real content, on the theory the crash might be size/complexity
correlated. It was not.

**Levels tried** (`dev/games/deusex/Maps/`, `uedcli.upackage.load_package` counts):
- `99_Endgame4.dx` (23,374 B, 63 exports/47 imports) -- `UCC.exe batchexport` itself fails
  (`Can't find Class in file 'Class Engine.CameraPoint'`) -- the documented v69-substrate gap
  (`dev/docs/unrealed/package-format.md` "The v69 editor cannot export every retail map"), not a
  crash. Not usable for this experiment.
- `DX.dx` (17,459 B, 59 exports/28 imports, 8 real brushes + 5 lights + 16 InterpolationPoints --
  the intro logo-cinematic map, not a bare shell) -- `batchexport` succeeded (37,727 B T3D). The
  `MAP NEW` -> `MAP IMPORT` -> `MAP SAVE` `EXEC`-script drive then crashed the container: identical
  signature to the original attempt (`docker exec ... exit 128`, "container did not run the probe").
- `Entry.dx` (13,745 B, 36 exports/17 imports) -- same result: `batchexport` succeeded (28,165 B
  T3D), the same `MAP NEW`/`MAP IMPORT`/`MAP SAVE` drive crashed the container identically.

2/2 real attempts at driving `MAP IMPORT` (excluding the CameraPoint export failure, which never
reached the drive step) crashed the container -- on levels roughly 40-90x smaller than the original
915-export level that also crashed twice. Per the task's own stop condition, no third attempt was
made.

**Reading:** the crash is not level-size- or level-complexity-correlated. Something about the
specific `MAP NEW` -> `MAP IMPORT` -> `MAP SAVE` sequence itself (as opposed to the `assemble_unbuilt`
+ `MAP LOAD` sequence production `materialize.py` actually uses) is fatal to the container
independent of content -- small enough that no OOM signature appears in `dmesg` and 17 GiB of host
memory stayed free throughout. No container-side log survives the crash (the container is gone by
the time the driver's probe fails; `stop_editor`'s `docker rm -f` in the `finally:` runs on an
already-dead container).

**Consequence for §12.1:** the clean-reimport experiment that section calls for cannot currently be
run at all via `MAP IMPORT` -- not "the answer is inconclusive" but "the drive itself does not
survive," on both a large and two small real levels. Confirms indirectly that the project's own
abandonment of `MAP NEW`+`EDIT PASTE`/`MAP IMPORT` driving in favor of `assemble_unbuilt` + `MAP
LOAD` (see `materialize.py`'s module docstring) was well-founded beyond just the previously-documented
`EDIT PASTE` GPF-on-complex-geometry reason -- `MAP IMPORT` alone (no paste, no brush CSG) is
independently unreliable.

**Not done / open:**
- Root cause of the crash is unpinned -- could be `MAP IMPORT` specifically (vs. `MAP NEW` or `MAP
  SAVE` alone), wine/Xvfb/X11 resource exhaustion inside the container, or a host-level issue
  affecting containers that happened to coincide with all three runs (three-for-three on a shared,
  possibly-loaded box is suggestive but not proof of an application-level bug).
- No attempt to isolate which of the three verbs in the script is the one that kills the container
  (e.g. drive `MAP NEW` alone, then `MAP NEW`+`MAP IMPORT` without `MAP SAVE`, watching liveness
  after each).
- No attempt with the individual typed-console form (non-`EXEC`-batched) to see if batching itself is
  implicated.
- Determinism/ordering comparison (the original goal) could not be attempted at all -- no clean-import
  `.dx` was ever produced in either round.

**Evidence:** `/tmp/export-order-experiment-2/` -- `attempt1-dx/` (stage1.py, stage1.log,
DX.original.dx, MyLevel.exported.t3d) and `attempt2-entry/` (same set for `Entry.dx`). The prior
round's evidence remains at `/tmp/export-order-experiment/`. Both are host-local scratch, not
committed.

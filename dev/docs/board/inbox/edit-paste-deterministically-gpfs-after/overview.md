+++
priority = "p1"
kind = "debug"
summary = "EDIT PASTE deterministically GPFs after importing phantom Class=Brush point actors"
+++

# EDIT PASTE deterministically GPFs after importing phantom `Class=Brush` point actors

## Finding

A retail trunk whose world is imported with `MAP IMPORTADD` of POINT actors INCLUDES any
`Class=Brush` actors that carry no polygon/brush data. Adding those phantom brushes into the map
poisons the editor's incremental CSG state so the NEXT `EDIT PASTE` — of any brush, even the first,
otherwise-harmless one — deterministically raises a real wine/UnrealEd "Critical Error" GPF dialog.

Measured on the OG-retail `DXMP_Smuggler.dx` trunk (496 real CSG brushes): 16 phantom Brush-class
actors (`Brush199, Brush206, Brush208, Brush209, Brush211, Brush212, Brush221, Brush231, Brush71,
Brush74, Brush102, Brush105, Brush111, Brush112, Brush125, Brush303`). With them imported
(`writes._re_add`'s `map_importadd`), EDIT PASTE crashed EVERY time across 7 attempts (full-set
paste, 32-chunk, 16-chunk, 1-brush at a time) with a real "Critical Error" window each time
(captured via in-container xdotool window list). Without them (skip the 16 phantom actors), 496
brushes pasted in 32-brush chunks in ONE editor boot with zero crashes, feature-complete gold.

Same-boot controls that fitted the pattern: `hk-helibase` and `paris-chateau` trunks have NO phantom
brush actors (only `LevelInfo` as the point actor) and pasted 1352/1002 brushes in the same way
without any crash. The "intermittent / bursty" appearance was a red herring: every crashing run
imported the phantoms, every passing run did not.

## Evidence

- Crash window list (each crash, fresh container): `WM_NAME = "Critical Error"` owned by
  `unrealed.exe`; empty `/opt/UED22/UnrealEd.log` (GPF at paste parse, no log line).
- `xclip` clipboard integrity: 42/42 byte-identical write/read-back at up to 136 KB payload — the
  transport is not the failure.
- Fix (measurement only, no repo change): drop `cls == "Brush"` actors with `brush is None` from the
  IMPORTADD point set. Native world-CSG also excludes them (no brush → not a CSG brush), so the
  golden stays the editor's build of the same 496-brush geometry.

## Impact

- For a partner building editor goldens from retail trunks: any trunk carrying phantom Brush actors
  will make every paste-based golden fail unless the IMPORTADD excludes them.
- Suggested hardening: in `writes._re_add` (or the golden harness), classify `brush is None and
  cls == "Brush"` actors as non-geometric and never import them; consider a regression test with a
  fabricated phantom-brush trunk.

## Files

- Golden evidence: `_scratch/golden-logs/golden{2,3,5,6,7,8,9}_smuggler.log` (crash runs),
  `resume2_smuggler.log` + `golden_smuggler_resume.dx` (success).
- Drivers (scratch): `_scratch/geo_golden_driver_chunked.py`, `_scratch/geo_golden_resume.py`,
  `_scratch/geo_flake_probe.py`, `_scratch/geo_brush0_sweep.py`.
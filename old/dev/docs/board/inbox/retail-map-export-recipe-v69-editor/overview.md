+++
priority = "p2"
kind = "chore"
summary = "Recipe for exporting a retail map with the v69 editor, for whoever runs the clipboard oracle next."
+++

# Recipe for exporting a retail map with the v69 editor, for whoever runs the oracle next

`docker build --platform linux/amd64 -t dx-lum-uned uned/`, then run with the game
substrate mounted read-only and inject `[Core.System] Paths` lines into BOTH `UnrealEd.ini` and
`unrealtournament.ini` (`Paths=/ued/*.u`, `Paths=<game>/System/*.u`, plus `*.utx`/`*.dx`/`*.uax`/
`*.umx` per dir) — a copy of `/opt/UED22` must be writable. Then
`xvfb-run -a wine /ued/UCC.exe batchexport <map>.dx Level T3D 'Z:\work\out'`. The output path MUST
be the backslash `Z:\…` form (`driver.to_z_path`); `Z:/out` fails with "Failed to make directory".
No stubbing was needed for a MAP export. *(2026-07-27.)*

*Carried over from the `installer-url` branch, whose `inbox.md` addition the board migration had already deleted.*

+++
priority = "p3"
kind = "implement"
summary = "`install-deusex-assets.sh --symlink` flag"
+++

# `install-deusex-assets.sh --symlink` flag

Spike Q20 (2026-06-23):
Docker follows host-side symlinks for bind mounts; `pathlib.Path` follows symlinks. Add a
`--symlink` flag that creates `DeusExAssets` as a symlink to the game install root instead of
copying ~1.5 GB. **Verified 2026-07-19:** the script is still copy-only (the flag is UNBUILT); a
hand-made `uned/DeusExAssets → DX` symlink already exists for the editor/game container bind-mount;
and the host-native CLI reads assets straight from the real install via config `paths` (no copy at
all) — so this is **moot for the CLI**, relevant only to the Docker editor/game container mount.
(Merged the duplicate `[spec]` inbox entry into this one.)

+++
priority = "p3"
kind = "debug"
summary = "umodel serialize spike test hardcodes an absent corpus path"
+++

# umodel serialize spike test hardcodes an absent corpus path

`dev/docs/spikes/bspspike/test_umodel_serialize.py:23` hardcodes
`_MAPS_DIR = /home/human/src/dx_lum/Tools/uedcli/uned/DeusExAssets/Maps`, which does not exist in
this checkout. With no maps, `test_every_map_serializes_byte_exact` trips `assert grand_total >
70000` (grand_total = 0) — so the committed corpus test fails wherever that machine-specific path is
absent (e.g. CI, a fresh worktree). The real retail maps live in a gitignored install dir
(this session found a copy under a sibling worktree's `dev/games/dxreal/Maps/`).

Fix options: resolve the corpus dir via an env var / the project's substrate config with a
`pytest.skip` when absent, or point it at the tracked location if one exists. The P0-gate test
(`test_umodel_p0_gate.py`) is content-independent (committed 8.6 KB golden) and unaffected.

Found during the P0 feasibility-gate verification (2026-08-03).

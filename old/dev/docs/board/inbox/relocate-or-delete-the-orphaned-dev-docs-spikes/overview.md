+++
priority = "p?"
kind = "chore"
summary = "Relocate or delete the orphaned `dev/docs/spikes/bspspike/` harness"
+++

# Relocate or delete the orphaned `dev/docs/spikes/bspspike/` harness

Bare
`bsp_csg.py`/`bsp_editorlog.py`, no markdown sibling, and nothing links it (every reference points at
`_scratch/bspspike/`). Tied to the parked offline-BSP work — move it under a
`2026-06-24-offline-bsp-engine-*` slug, or delete if `_scratch/` holds the authoritative copy (git
keeps history). (AI flag, 2026-07-11.)

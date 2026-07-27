+++
priority = "p3"
kind = "chore"
summary = "Two round-4 pinning gaps in the `core.dll` engine-facts regression"
+++

# Two round-4 pinning gaps in the `core.dll` engine-facts regression

`test_engine_facts.py` asserts only that 2 imports are present and 7 are absent, while
`spikes/2026-07-25-map-save-mechanism/README.md` states all 8 file-API imports as fact — and the
README's Q1 offset table (7 byte-exact offsets) is unpinned, so a relink rots it silently. Assert
the full file-API import set and the offsets, or stop stating them as exact. (2026-07-25, round-4
cold review.)

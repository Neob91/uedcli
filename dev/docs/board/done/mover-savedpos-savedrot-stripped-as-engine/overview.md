+++
priority = "p?"
kind = "unknown"
summary = "Mover `SavedPos`/`SavedRot` stripped as engine-stamped — FIXED 2026-07-25 03:07 UTC"
+++

# Mover `SavedPos`/`SavedRot` stripped as engine-stamped — FIXED 2026-07-25 03:07 UTC

`level materialize` (and `preview --game`'s internal build) aborted on EVERY map containing a
mover: the rebuilt map's re-export carries `SavedPos=(-12345,-12345,-12345)` and
`SavedRot=(Pitch=123,Yaw=456,Roll=789)` that the trunk never emits, and neither is a class
default. `AMover::PostLoad()` writes both unconditionally on every load of a Mover object —
disassembled BY NAME out of both shipped engines (UED22 `Engine.dll` `?PostLoad@AMover@@UAEXXZ`
RVA 0x171140; DX `Engine.dll` RVA 0xaf7e0), no guard, right after `Super::PostLoad()` — so no
authored value can survive a round trip. Fix: add the two to `normalize.COMPUTED_PROPS` beside
`BasePos`/`BaseRot`. Live-confirmed end to end: the built `.dx` holds NO sentinel, the
post-verify's own UCC re-export of that same file does, and materialize now passes. `SavedTrigger`
is excluded FOR CAUSE — `Engine.TriggerLight` declares its own, and the set is keyed by bare name
across all classes. Two adjacent suspicions from the bug report (`bDynamicLightMover`, `KeyPos[]`
echoes) were live-checked and DISPROVED — both re-export verbatim, so they are authored content.
Spike `spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/` (harness: `scan_corpus.py`,
`disasm_postload.py`); decision `decisions.md` 2026-07-25 03:07 UTC; `unrealed/t3d.md`
authored-vs-computed taxonomy; `architecture.md` "Mover support". Pinned by
`test_engine_facts.py::test_amover_postload_unconditionally_stamps_the_savedpos_savedrot_sentinels`
plus three `test_normalize.py` regressions.
**Remnant** (filed on `inbox.md`, `[chore] p2`): `level preview --game`'s internal materialize
still runs the H3 post-verify with no way to skip it, though a preview `.dx` is throwaway.

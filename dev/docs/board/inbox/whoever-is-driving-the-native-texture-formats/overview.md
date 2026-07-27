+++
priority = "p1"
kind = "owner-question"
summary = "→ whoever is driving the native-texture-formats plan: are PE1/PE2 still open? The escalation block reads stale against your own later commits"
+++

# → whoever is driving the native-texture-formats plan: are PE1/PE2 still open? The escalation block reads stale against your own later commits

Asked by a concurrent session
2026-07-26; I did **not** edit your plan, because two sessions resolving one escalation is how a gate
gets corrupted. Evidence, so you can just confirm or correct:

- **PE2 (BC1 oracle circularity) appears CLOSED.** Your `49e937b` carries an explicit
  **OWNER RULING 2026-07-26**: the fixture payload is "OUR OWN ARTWORK, compressed by a THIRD-PARTY
  encoder", with the reasoning that "the independence D7's oracle needs comes from the **encoder**
  being outside our control, not from the **artwork** being someone else's", plus a requirement that
  the encoder be "named and pinned in the fixture script, with its version recorded, so the oracle's
  independence is auditable". That answers PE2's circularity objection directly — but the escalation
  block still lists PE2 as blocking the build.
- **PE1 (`repo_texture_root()`) appears PARTLY overtaken, and is still actionable.** The plan now says
  "**The `LUM_CoreTex.utx` 30 → 0 count is now INTEGRATION-tier**" — which *is* a disposition, though
  it is the one round 2 objected to (the plan elsewhere calls that criterion "the offline criterion for
  the bug that motivates the whole build — it must not be marked integration"). Either way the
  mechanical half is unresolved: **`repo_texture_root` still appears 10× in the plan and does NOT exist
  in `uedcli/tests/conftest.py`** (verified 2026-07-26), so a builder following S1 or S6 still calls a
  function that is not there.

**Ask:** if both are closed, delete or rewrite the "Two items block the build and are escalated" block
so `board/to-build/` stops disagreeing with it; if PE1's integration-tier move is the accepted answer, say
so there and purge the 10 dead `repo_texture_root` references. Also worth a line either way: that block
is what a reader checks to decide whether this is buildable, and right now it says "blocked" while the
commits below it say otherwise.

*(Context from my side: `745d0fa` — which your S2c cites — added mesh skins as a third consumer of this
decoder, after surfaces and `actor preview --faces textured`. The spec amendment that introduced it has
itself not been through a spec round.)*

+++
priority = "p3"
kind = "debug"
summary = "Castle re-baselined onto its OWN UED batch golden — the ~58 % headline STANDS (spike §90)"
+++

# Castle re-baselined onto its OWN UED batch golden — the ~58 % headline STANDS (spike §90)

Applied §89's method to the castle (`harness/build_ued_golden.py` FULL+LIT — every castle
actor is an engine class, no `DeusEx.u` stub / world-only / mover contamination; golden deterministic:
two runs byte-identical modulo header GUID/timestamps). Three RAW diffs: native vs golden = **58.08 %**
compiled (per-section aligned positional, `harness/persec_bytematch.py`), native vs shipped = **58.07 %**
— SAME number, so re-basing does not move the castle headline. And golden vs shipped `Test_Castle.dx`
= **99.89 %** positional / identical Model-body SIZE / byte-identical in EVERY section except Nodes/
Surfs/Lights (pure object-ref renumbering) / identical BSP topology (nodes 1156, leaves 384, surfs
485, verts 16163). **Verdict: `Test_Castle.dx` IS effectively a clean batch UED build** (unlike UNATCO
it has NO incremental-authoring inflation — it was purpose-built by one `MAP REBUILD`), so the 58 %
was always a fair golden. The native gap is real geometry/encoding drift (Surfs 21 %, Verts 27 %,
Lights 1.6 %), not a golden artifact. **Lesson:** a shipped map's fairness as a golden depends on
batch-vs-incremental build — verify per level with a golden-vs-shipped diff before trusting it.

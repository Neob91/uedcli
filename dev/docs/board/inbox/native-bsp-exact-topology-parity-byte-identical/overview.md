+++
priority = "p2"
kind = "unknown"
summary = "Native BSP exact-topology parity → byte-identical `.dx`. NOW SPECCED:"
+++

# Native BSP exact-topology parity → byte-identical `.dx`. NOW SPECCED:

p2 **Native BSP exact-topology parity → byte-identical `.dx`. NOW SPECCED:**
`spec.md` (2026-07-17) sequences the port foundation-first with a byte-diff gate
per phase (topology → FVert/point pool order → surfs → render Bounds+LeafHulls → lightmaps →
package wrapper), deletes the synthetic leaf-bounding scaffold, and settles the FP-determinism
question (provisionally ACHIEVABLE — decoded routines are SSE-scalar, not x87 — gated on a Phase-0
per-site characterization). **Blocked on:** (1) the two review-gate subagents, (2) Andrzej's calls
on spec Q1-Q5 (byte-identity scope incl. package GUID; canonicalization fallback if a site is
x87/rsqrt; effort ceiling; oracle-regen authority; trunk brush-flag round-trip). **Phase 0 is a
BLOCKING decode+FP spike** (instruction-level `bspBrushCSG`/`FilterFPoly`/`bspBuildFPolys`/
`bspMergeCoplanars`/`bspOptGeom`, FP x87-vs-SSE per hot site, editor-determinism diff). Context:
castle nodes 909 vs **1156**, FVerts 3604 vs **16163**, surfs 438 vs 485, Bounds 0 vs 484. Once
reviewed + Andrzej's calls land, move to `board/to-plan/`. N-3+.
**UPDATE 2026-07-17: Phase 0 DONE — verdict GO** (`81-phase0-feasibility.md` +
`re-raw-zones/fp-classification-sites.md`, decision 2026-07-17 18:00). FP is SSE-scalar (the DLLs
are a 2022 MSVC/SSE2 rebuild — MD5-identical to the golden-building container, NOT 1999/x87), input
identity holds (castle = pure translation), normal provenance = PRESERVE, pool order/`NumSharedSides`
reproducible. The FP crux is resolved FAVORABLY; remaining blockers are the review gates + Andrzej's
Q1–Q5, and the port-prerequisite decodes (`FilterFPoly` leaf funcs + bevel planes, `bspBuildFPolys`,
`bspMergeCoplanars`, `FindBestSplit` score op-order) — these gate the port, not the GO verdict.

+++
priority = "p3"
kind = "chore"
summary = "Two Phase-0 corroborations"
+++

# Two Phase-0 corroborations

p3 **Two Phase-0 corroborations** (cheap, non-blocking): (a) xref `FVector::Normalize`
(core `0x24940`, the one x87 `fdivrp` reciprocal near geometry) against the CSG-build call graph to
confirm no build-path caller reaches it (CalcNormal uses the SSE `NormalizeSlow`, so surf normals
are safe); (b) run the editor materialize on the castle trunk **twice** and byte-diff masking the
16-byte GUID (offset 36) — empirical editor-determinism corroboration (static argument already PASS).

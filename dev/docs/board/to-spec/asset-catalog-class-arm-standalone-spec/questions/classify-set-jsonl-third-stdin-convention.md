# `classify set -` JSONL is a third `-` convention — land the conventions.md carve-out first?

## Context

Spec §8.5, marked **[CARRIED — do not resolve]**; the carve-out text lives verbatim in board item
`conventions-md-needs-a-calibrated-carve-out`. Recorded here because it blocks slice C3.

`direction/conventions.md` (lines 107–109, 221) says "**Exactly TWO stdin conventions**, disambiguated
by verb … never add a third." The JSONL row set that `classify set -` reads (§5, §7) is a third stdin
shape. It was ruled "it's fine" (2026-07-26) but the protected direction doc still forbids it, and
agents may not edit `direction/` without an explicit yes.

- **At stake:** C3's batch path (`classify set -`) cannot ship while the doc forbids the third
  convention. The per-ref `classify set` path is unaffected.
- **Direction default:** the doc as written forbids it; the carve-out must land to authorise it.

**Recommendation:** land the carve-out (fold board item `conventions-md-needs-a-calibrated-carve-out`
into `direction/conventions.md` with the owner's yes), then build C3. Do not ship the third convention
while the doc forbids it. Resolve in that board item, not here.

## Answer

<!-- Empty = open. -->

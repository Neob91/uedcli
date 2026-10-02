+++
priority = "p?"
kind = "docs"
summary = "RESOLVED — live-confirmed 2026-07-19"
+++

# RESOLVED — live-confirmed 2026-07-19

level materialize
**RESOLVED — live-confirmed 2026-07-19.** The whole cascade is fixed: `qualify` off-by-one FIXED (regression-tested), semisolid-MAP-SAVE proven NOT-a-bug (5/5 spike), and the two texture-package CRITICALs (H3 re-export; symlink-outside-repo drop) LIVE-CONFIRMED fixed — a real materialize of the 161-actor castle trunk referencing three external packages (`LUM_CoreTex`, `CoreTexWater`, `CoreTexSky`) built clean (448858-byte `.dx`, exit 0 ⇒ H3 verify passed, zero "Can't find file", all three packages present in the import table). The only survivor is the defensive-warning residual below.

<!-- ── boot-flake retry follow-ups (from the 2026-07-19 review gate on the bounded-retry change) ── -->

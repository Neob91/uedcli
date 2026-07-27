+++
priority = "p?"
kind = "unknown"
summary = "SP-E warm-editor materialize spike"
+++

# SP-E warm-editor materialize spike

— RAN 2026-07-19 (2-reviewer cold-gated), findings folded
into the spec §8 + `quirks.md`; harnesses committed under
`spikes/2026-07-18-warm-editor-materialize/harness/`. Answered SP-E.1 (reused successful builds are
canonically == a fresh build), SP-E.3 (resident `OBJ LOAD` = harmless re-read), SP-E.5 (timing:
warm saves ~16 s/build ~20%; verify ~42 s > boot ~15 s), SP-E.6 (RSS flat, no cap needed). **Remnant
→ the spike surfaced a BLOCKER now parked in `inbox.md` as an open design decision:** the H3 verify
run against the warm editor breaks ~50% of reused builds (`MAP SAVE` silently lost); needs a fix
(separate verify editor vs idle barrier) + an SP-E re-run before the build. SP-E.2 (possible real
cross-level residue) + SP-E.7 (colliding names) deferred behind that fix.

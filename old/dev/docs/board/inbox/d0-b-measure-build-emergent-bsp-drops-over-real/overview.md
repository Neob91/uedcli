+++
priority = "p3"
kind = "implement"
summary = "Run the build-output BSP check over real maps to size build-emergent drops the static doctor misses"
+++

# D0-b: measure build-emergent BSP drops over real maps

The measurement half of the original D0 plan, left out of the materialize BSP-check work
(`done/bsp-issue-detector`). Over real semisolid/portal maps (gitignored install content), compare
the build-output check's drop counts (`bsp.editorlog.parse_build_log`) to the static `level doctor`'s
predicted `degenerate`/`watertight` ERROR count. The excess is a fuzzy upper bound on build-emergent
drops the static tier misses — it tells us whether more located detection (D1-b) is worth building.

Content-blocked here (no install content in this env). Does NOT gate the deferred D2 offline engine
(silent-absence is unmeasurable offline). Needs the gitignored maps present.

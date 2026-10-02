+++
priority = "p3"
kind = "implement"
summary = "LOW: `project show` reports \"0 package(s)\" while the path actually resolves"
+++

# LOW: `project show` reports "0 package(s)" while the path actually resolves

p3.
  Printed "0 packages" in-container (dangling DeusExAssets symlink — see the materialize texture bug)
  while a host check saw 56, with nothing tying them together → chased a non-issue. Count should
  reflect the resolved/composed set, and warn (not silently show 0) on a dangling in-container glob.

<!-- ── castle moat/expansion round (2026-07-12): more dogfooding ── -->

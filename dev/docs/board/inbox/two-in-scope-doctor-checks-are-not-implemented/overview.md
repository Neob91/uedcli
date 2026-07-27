+++
priority = "p2"
kind = "implement"
summary = "Two IN-SCOPE `doctor` checks are not implemented"
+++

# Two IN-SCOPE `doctor` checks are not implemented

Both fall inside the
intent-independence bound ruled 2026-07-26, and both were named by the owner as things doctor should
catch:
(a) **a light buried inside solid geometry** — it lights nothing; the DiveBar polish pass found
**five of 40 lights** strictly inside solid brushes (two inside their own door mover, one in a
structural column, two in a floor dais), whose visible symptom was pure-black doors and an unlit
cellar, and point-in-brush-bbox over `Engine.Light` found all five in seconds
(`spikes/levelbuild-friction/agent-reports.md`);
(b) **an `Event` matching no actor's `Tag`** — this already EXISTS as `eventgraph.py`'s
`dangling_event` (`eventgraph.py:223`, *"fires into the void"*) but is surfaced only by
`event graph`, so a `doctor` run misses it. Decide whether doctor absorbs the eventgraph lint or
calls it; `doctor.CATEGORIES` is currently `degenerate,watertight,convex,planar,solidity,csg_order,
scale` with no reference-integrity category at all. *(2026-07-26.)*

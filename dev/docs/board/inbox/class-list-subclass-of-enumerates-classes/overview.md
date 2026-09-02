+++
priority = "p1"
kind = "unknown"
summary = "`class list`/`--subclass-of` enumerates classes from packages with NO loadable v69 stub, and two package views disagree"
+++

# `class list`/`--subclass-of` enumerates classes from packages with NO loadable v69 stub, and two package views disagree

Deliberately left out of the 2026-07-26 unified-asset-catalog
spec revision (owner's call) — recorded here because it is real and the spec now says so in §14.
The friction log calls it *"the worst-shaped defect I hit"*
(`spikes/levelbuild-friction/agent-reports.md`, two independent entries):
- `class list --flat --subclass-of DeusEx.DeusExDecoration` lists `Endemia.Ashtray`,
  `Endemia.GlassBottle`, `Endemia.WoodStool1`, `TNM.NapalmCanister` … interleaved with usable
  `DeusEx.*` classes, **unmarked**. Every `actor build | actor add` of one printed `added 1 actor(s)`
  and exited 0. The level then failed EVERY materialize with `level references v68 code package(s)
  with no v69 stub: Endemia`, i.e. the trunk was poisoned and the only clue was the package name in
  an error twenty minutes downstream.
- The failure has an **opposite, worse shape under stderr suppression**: a previous session's helper
  redirected stderr, so ~15 props were a silent no-op — the bar shipped with no stools and no
  bottles and nobody noticed until a render.
- **REFUTED, with the check recorded:** the log's "two views of one catalog disagree about whether
  `Endemia` exists" is **not** a defect. Measured 2026-07-26 in the LUM project: bare
  `class list --flat` returns **42** classes, because it is the documented depth-1 view of *the direct
  children of `Engine.Actor`* (`classindex.list_classes` docstring, `classindex.py:245-261`) — those
  42 happen to span 4 packages, so `cut -d. -f1 | sort -u` prints `DeusEx DXOgg Engine TNM`.
  `--depth all` returns **1,345** classes across **12** packages including **65** `Endemia.*`, and
  `--subclass-of DeusEx.DeusExDecoration` returns **52** `Endemia.*`. Same function, different depth,
  all as documented. The log's agent read a depth-1 category listing as a corpus listing.
- **The real residue is a HINT, not a bug** (`p3` `[chore]`): bare `class list --flat` prints 42 bare
  class names with no count, header, or "these are categories — drill in with `--subclass-of`" note,
  so it is indistinguishable from a complete listing — which is precisely the misreading that
  produced the false conclusion above, in an agent that then acted on it.
The log's suggested fixes, in its own order of value: (1) reject the class at `actor build` with the
message materialize already produces; (2) mark or omit unstubbed packages in `class list`; (3) a
`level doctor` check for "trunk references a package with no v69 stub", catchable offline in a second.
The spec mentions stub/v68/v69 **zero times**. *(2026-07-26.)*

+++
priority = "p1"
kind = "owner-question"
summary = "OWNER ruling: every native-decode spike finding written before 2026-08-14 is invalid — treat the July editor-disassembly decodes as unreliable (the agent was drunk)"
+++

# OWNER ruling: native-decode spike findings older than 2 weeks are invalid

Ruled 2026-08-28, emphatically and twice: ignore any native-decode finding written down earlier
than ~2 weeks ago (today = 2026-08-28, so cutoff = 2026-08-14). The agent that produced the July
spikes `dev/docs/spikes/2026-07-15-native-materialize/` and `re-raw-zones/` was unreliable — "the
agent must've been drunk when he did these spikes."

## What this invalidates

The entire pre-2026-08-14 editor-disassembly decode body: `bspMergeCoplanars` (0x36200),
`bspRepartition` (0x49fc0), `TryToMerge` (0x34b10), `RemoveColinears` (0x151090),
`FindBestSplit`/`SplitPolyList` stride/GOOD-mode, the `sub_49380` collector, the two
`bspRepartition(Model, iChild, 2)` loops at `0x1004aa3f`/`0x1004aa90`, the point/vert-pool pool
oracles, and every causal label built on them (e.g. "GOOD-mode stride sensitivity", the "+2 soup
traces to the points/verts residual"). These are NOT ground truth for the current tree.

## What still stands

- Commit history from 2026-08-25 onward (`7f4a773`, `9e38d8d`, `b3609ea`) was implemented against
  CURRENT-tree live evidence and verified by measurement on OG retail levels; those code facts hold.
- Current-tree MEASUREMENTS (e.g. the Wanchai +20 tree walk: one repartition splitter-pick at node
  9843, root soups differ by +2, committed trees identical, surf-exactness) are valid as
  measurements, but any CAUSAL story attached to them that cites the old spikes is not.

## Consequence for the open geometry gaps

- UNATCO Verts/Points residual ("~209 missing sub-BSP repartitions, port `sub_49380`") is
  diagnosed ONLY from the old spikes → **not portable from the written spec**; must be re-pinned
  from fresh live capture before any port.
- Wanchai +20: the measurement is sound, the cause is not "known" in a way we can rely on.
- Any future port must re-establish facts on the current tree from fresh live editor capture, not
  from these written decodes. A subagent doing this MUST be told to ignore the pre-2026-08-14
  spikes, or it will misread correct behavior as a bug (and vice-versa) using stale authority.

## Why it matters

Building the sub-BSP repartition port on the drunk decode would encode the same errors into native
and send us chasing phantom divergences. Re-decoding costs editor runtime + gdb time but is the
only evidence the owner accepts.

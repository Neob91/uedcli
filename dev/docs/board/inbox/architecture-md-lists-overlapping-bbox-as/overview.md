+++
priority = "p3"
kind = "owner-question"
summary = "architecture.md lists --overlapping-bbox as unbuilt (now shipped)"
+++

# architecture.md lists --overlapping-bbox as unbuilt (now shipped)

`dev/docs/architecture.md:133` reads "`--within-bbox` slice landed;
`--near`/`--overlapping`/`--overlapping-bbox` remain unbuilt." `--overlapping-bbox` shipped
(`actor find --overlapping-bbox`, `writes.aabb_intersects`). Left untouched during that build —
`architecture.md` edits are owner-gated. Proposed: drop `--overlapping-bbox` from the unbuilt list.

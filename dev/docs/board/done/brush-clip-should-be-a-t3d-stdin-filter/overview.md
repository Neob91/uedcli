+++
priority = "p2"
kind = "implement"
summary = "`brush clip` should be a T3D-stdin FILTER (`-`), not only a by-name trunk edit"
+++

# `brush clip` should be a T3D-stdin FILTER (`-`), not only a by-name trunk edit

Done. `brush clip` is now a stateless T3D-stdin filter (`-`|FILE → clip every brush by one world
plane → stdout), matching `brush build`/`intersect`/`deintersect`; the by-name in-place form is
deleted outright (no alias). Spin-offs filed: `architecture-md-tree-rider-list-still-names` (stale
`--tree` doc ref), `brush-clip-filter-clips-a-mover-in-the-set` (owner-question).

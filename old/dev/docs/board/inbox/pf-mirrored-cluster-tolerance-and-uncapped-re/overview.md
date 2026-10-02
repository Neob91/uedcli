+++
priority = "p3"
kind = "unknown"
summary = "PF_Mirrored cluster tolerance and uncapped re-render cost"
+++

# PF_Mirrored cluster tolerance and uncapped re-render cost

Surfaced by a `code-review high` pass run against the lighting-in-photo branch (which had merged
master's PF_Mirrored work in) — not lighting-related; logging instead of fixing there. Both in
`uedcli-native/src/render.rs`.

- **`group_mirror_clusters`'s coplanarity tolerance (normal dot > 0.999, plane distance < 0.5uu,
  line 196) can split one CSG-fragmented mirror face into two clusters** under floating-point
  drift. Each cluster's reflection render then includes the OTHER cluster's mirror poly as ordinary
  (non-excluded) scene geometry, forced opaque at `mirror_depth+1` instead of contributing to the
  reflection — a visibly seamed reflection across one continuous mirror. Measured real content
  (`Terraniux.unr`) lands its fragments on the exact same plane, so this is plausible-but-unconfirmed,
  not demonstrated.
- **The mirror pass (line 447) runs one full recursive `render_impl` re-render of the entire scene
  per mirror cluster, with no cap on cluster count.** `group_mirror_clusters`'s own doc comment
  states real content already produces 2 clusters from 8 brushes and that this is "not bounded in
  general" with "no cap, no warning" — documenting the limitation doesn't mitigate the cost. A level
  with several differently-oriented mirrors triggers that many full-scene re-renders per
  `level photo --native` call.

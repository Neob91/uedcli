+++
priority = "p3"
kind = "debug"
summary = "Native preview: black speckles on tower-roof CONES at some angles (castle acceptance, `spikes/2026-07-16-native-preview-anchor/perf.md`)"
+++

# Native preview: black speckles on tower-roof CONES at some angles (castle acceptance, `spikes/2026-07-16-native-preview-anchor/perf.md`)

— looks like coplanar-fragment
z-fighting (the N-2 un-merged coplanar residuals) between abutting cone facets. p3,
draft-acceptable; revisit after `bspMergeCoplanars` lands (the b-case residual).

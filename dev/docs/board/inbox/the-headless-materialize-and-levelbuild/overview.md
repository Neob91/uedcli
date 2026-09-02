+++
priority = "p3"
kind = "chore"
summary = "The `headless-materialize` and `levelbuild-friction` spikes are UNCOMMITTED"
+++

# The `headless-materialize` and `levelbuild-friction` spikes are UNCOMMITTED

Both are
untracked; the warm-editor spec's decision 6, its whole §5, its leak measurements and its scope
limits all cite them, and `rules/spikes.md` requires harnesses committed under
`dev/docs/spikes/<slug>/`. Until they land, a `git clean` destroys the evidence base. (Owned by
whichever session ran them.)

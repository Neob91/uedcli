+++
priority = "p?"
kind = "unknown"
summary = "schema-cache `class show` seed-drop (remaining half)"
+++

# schema-cache `class show` seed-drop (remaining half)

— BUILT 2026-07-20 (2-reviewer cold-gated,
built in a subagent). Dropped `class show`'s `shared` full-`Package` seed so its prop walk takes the
`load_package_schema` warm-cache path — measured ~2.1–2.4× warm, output byte-identical. Reviewers
confirmed it's actually MORE divergence-safe than the seed (chain + props now share one memoized
disc). `dispatch._dispatch_class` + coupled test (`_cache is None`) + `architecture.md`; decision
2026-07-20 00:30 UTC. Pre-existing non-category degrade-test gap flagged to inbox. Commits
`72e00f9d9`, `2b7be0e19`.

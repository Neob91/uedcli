+++
priority = "p?"
kind = "implement"
summary = "Texture catalog redesign (lazy native decode, content-addressed cache, similarity) — superseded by the unified asset catalog"
+++

# Texture catalog redesign — superseded

A 2026-07-19 redesign of the whole texture catalog: lazy native decode, a content-addressed pixel
cache, git-tracked classifications and visual-similarity search. Its scope was superseded by the
unified asset catalog work; parts of the workflow half shipped inside `texture list`/`search`/
`classify`. Kept as design history.

Holds two specs: the redesign, and the narrower `texture show` spec it had itself superseded.
Neither was owned by a board entry.

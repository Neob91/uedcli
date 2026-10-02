+++
priority = "p3"
kind = "implement"
summary = "`actor folder rename OLD NEW` — whole-subtree re-parent/rename"
+++

# `actor folder rename OLD NEW` — whole-subtree re-parent/rename

Built. One model-side pass rewrites the folder prefix on every actor filed at OLD or under it
(segment-boundary match, case-insensitive; NEW stored as authored). OLD matching no actor exits 2
naming OLD (owner, 2026-08-02).

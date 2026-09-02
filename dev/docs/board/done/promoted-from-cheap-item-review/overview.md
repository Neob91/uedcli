+++
priority = "p?"
kind = "docs"
summary = "Record of the 2026-07-24 cheap-item triage, including the two items that deliberately did not land here."
+++

# Promoted from the cheap-item board review (2026-07-24)

Andrzej triaged the ten-item cheap shortlist in chat; his calls are recorded in `direction/conventions.md`,
2026-07-24 21:58 UTC. Three items changed shape rather than just queue (class-show, the ditched
stash-`CalledProcessError` item, and `--png`). Two items did NOT come here: the `ensure_editor`
`CalledProcessError` leak was **ditched** (native intersect/deintersect deletes that code path), and
nothing was sent to `board/to-spec/`.

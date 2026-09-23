+++
priority = "p?"
kind = "implement"
summary = "actor survey and actor relation: CSG-resolved spatial facts"
spikes = ["dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/"]
+++

# actor survey and actor relation: CSG-resolved spatial facts

Two changes, one design: `brush relation` is renamed to `actor relation` (broadened for non-brush
actors) and a new standalone verb, `actor survey <name>`, reports the full set of raw and
CSG-resolved spatial facts about one named actor.

The goal, stated at the start of this design: let an LLM reason about a level's spatial
relationships despite being notoriously bad at spatial reasoning. `level graph` already gives a
cheap, whole-level, raw-geometry graph. This item adds the per-actor, authoritative counterpart —
real CSG/BSP resolution via the native engine — without re-merging the two into one graph, since
they answer genuinely different questions (spatial layout vs. did-I-actually-clip-something).

Full design in `spec.md`.

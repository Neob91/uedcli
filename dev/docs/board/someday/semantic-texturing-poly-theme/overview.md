+++
priority = "p?"
kind = "unknown"
summary = "Semantic texturing: `poly theme`"
+++

# Semantic texturing: `poly theme`

Classify every face by role (floor/ceiling/wall/trim
from its normal + position) and assign textures by catalog tag query ("floor←stone, walls←castle
brick") in one command, instead of dozens of `poly set --texture` calls. Composes the texture
catalog's tags with a face-role classifier; deterministic and reviewable (prints the plan first).
**SEQUENCED AFTER the texture-catalog redesign** (`to-plan.md`) — its tag-query half rests on that
work; fold it into that work's follow-on rather than speccing independently. (AI brainstorm 2026-07-16.)

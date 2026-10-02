+++
priority = "p3"
kind = "docs"
summary = "README brush clip example is stale (verb now takes -|FILE, not an actor name)"
+++

# README brush clip example is stale (verb now takes -|FILE, not an actor name)

Fixed: README quickstart now shows the in-place pipe `actor show Brush41 | brush clip - --axis z
--offset 128 --keep below | brush replace Brush41 -`, matching `docs/usage.md`. The old
`brush clip Brush41 …` form failed (`brush clip` is a stdin→stdout T3D filter).

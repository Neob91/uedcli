+++
priority = "p1"
kind = "implement"
summary = "`actor move` over a SET (`-`/stdin), `--by`-only for multi-actor"
+++

# `actor move` over a SET — DONE

`actor move` takes the `names…|-` set contract (`actor rotate`/`brush scale` sibling): `--by`
translates every target by a world delta (any count), `--to` still one actor (set >1 → exit 2).
Dedupe on canonical names, empty-stdin no-op, PRODUCER stdout + `moved N actor(s)` stderr.

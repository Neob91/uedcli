+++
priority = "p2"
kind = "unknown"
summary = "Name-taking verbs accept actor names from STDIN (`-`)"
+++

# Name-taking verbs accept actor names from STDIN (`-`)

p2. `actor find` already prints
  matching names one-per-line for piping, but the mutate/query verbs take names only as CLI args, so
  the pipe doesn't close: you copy-paste or `$(...)`-substitute. Let `actor set -` / `actor prop -` /
  `actor delete -` / `actor rotate -` / `brush poly set -` etc. read the newline-separated name list
  from stdin, so `actor find --group castle.tower | actor prop - --set Texture=…` composes end-to-end
  (mirrors `actor add -`'s stdin convention). Andrzej, 2026-07-12.

<!-- ── uplayctl in-game screenshot dogfood: PlayerStart-in-solid (2026-07-12, Andrzej) ── -->

<!-- ── castle detail-pass dogfood: semisolid materialize bug (2026-07-13, Andrzej) ── -->

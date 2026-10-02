# What repo URL hosts the uedcli plugin marketplace, and is publishing it approved?

## Context

The plugin's install path is `/plugin marketplace add <repo-url>` — a public, outward-facing
distribution act, which the box rules put behind an explicit owner yes. Everything else about the
plugin is already decided (see board item `level-design-best-practices-docs-ai-skills`); this is the one open owner-only fork.

Blocked behind `extract-uedcli-into-its-own-standalone-git-repo`, so it cannot be actioned yet, but the
answer shapes the extraction's remote setup:

- Which host/URL is the standalone CLI repo (and is it public, so `/plugin marketplace add` works for
  users)?
- Once it exists, is publishing the marketplace approved, or does the owner want to run the first
  `/plugin marketplace add` themselves?

Recommendation: name the intended public repo URL now so the extraction targets it; hold the actual
publish for an explicit yes after the repo is live and the skills (deliverables A/B/C) have landed.

## Answer

<!-- Empty = open. -->

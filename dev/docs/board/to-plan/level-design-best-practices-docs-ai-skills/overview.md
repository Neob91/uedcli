+++
priority = "p2"
kind = "implement"
summary = "Level-design best-practices docs + AI-skills plugin"
+++

# Level-design best-practices docs + AI-skills plugin

Spec written +
cold-review-gated + revised: [`../specs/2026-07-19-leveldesign-docs-skills.md`](../../../specs/2026-07-19-leveldesign-docs-skills.md).
Three deliverables: (A) verb-first rewrite of the `leveldesign/` guides (GUI-equivalent notes
retained, per-guide retention checklist); (B) a measurement spike for DeusEx human-scale numbers
(offline class-defaults + a MAP-EXPORT map-geometry corpus + player collision cylinder + object
sizes); (C) a Claude Code skills plugin at `claude/plugins/uedcli/` (repo-as-marketplace;
distribution blocked on the uedcli-own-repo move — interim dev via a `.claude/skills` symlink). Needs
a build plan sequencing A+B then C, with the two cold-reviewer gates. (Andrzej, 2026-07-19.)

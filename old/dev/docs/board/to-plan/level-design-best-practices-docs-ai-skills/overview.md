+++
priority = "p2"
kind = "implement"
summary = "Level-design best-practices docs + AI-skills plugin"
+++

# Level-design best-practices docs + AI-skills plugin

Spec written +
cold-review-gated + revised: board item `review-gate-round-2-findings-left-standing`.
Three deliverables: (A) verb-first rewrite of the `leveldesign/` guides (GUI-equivalent notes
retained, per-guide retention checklist); (B) a measurement spike for DeusEx human-scale numbers
(offline class-defaults + a MAP-EXPORT map-geometry corpus + player collision cylinder + object
sizes); (C) a Claude Code skills plugin at `claude/plugins/uedcli/` (repo-as-marketplace;
distribution blocked on the uedcli-own-repo move — interim dev via a `.claude/skills` symlink). Needs
a build plan sequencing A+B then C, with the two cold-reviewer gates. (Andrzej, 2026-07-19.)

## Folded from levelbuild-friction (owner, 2026-08)

Owner findings #1 and #8 fold into deliverable A as explicit requirements:

- **Swinging-door recipe** — the built levels' doors all slid, none swung; the mover-door recipes
  (`general/recipes/mover-door.md`, `deusex/recipes/deusex-door.md`) teach no swing default. Add a
  swinging-door recipe (PrePivot at the hinge edge, `KeyRot` yaw) and state that a swing door is the
  interior default. The mechanism is checkable, safe to write with A.
- **Mover guidelines** — consolidate the day-to-day mover craft (`general/movers.md`) so agents don't
  reach only for `ElevatorMover`.
- **Trim / high-fidelity detail** — finding #8: levels lacked doorframe trim and edge detail. Add a
  worked doorframe example (a cube minus a smaller cube, a few-uu protrusion) and realism/fidelity
  guidance. This is judgment-heavy craft: gate it on the measurement spike (B) + owner accuracy review
  before writing, per `CLAUDE.md` "new level-design craft knowledge needs the owner's approval."


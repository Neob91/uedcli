# Approve adding this user-facing workflow doc — and is it tool-behavior or craft?

## Context

The output is new content under `docs/` (user-facing), which needs the owner's explicit yes before
it lands (`CLAUDE.md` "Documentation"; `dev/docs/rules/documentation.md:24-28`). Two things to
confirm:

1. **Approve the doc at all**, with the home and outline in `spec.md` (branch → edit trunk → preview
   → materialize → commit/merge). If yes, the exact prose will be proposed for a second yes before
   writing — this question only unblocks the item.

2. **Which approval bar applies.** The rule: documenting how uedcli tools BEHAVE (verbs, flags,
   output, the loop chaining them) needs no craft approval; new level-design KNOWLEDGE
   (best-practice, human-scale numbers, engine/design claims) does. This doc is mostly the former —
   the tool loop — so the recommendation is: treat it as tool-behavior, no craft-review needed,
   PROVIDED it makes no craft or engine claims (no "commit at these milestones", no performance
   numbers). If the owner wants any best-practice guidance in it, that part crosses into craft and
   needs the review + approval treatment.

Recommendation: approve as a tool-behavior how-to; keep craft/best-practice OUT (or split it to a
separate approval).

## Answer

<!-- Empty = open. -->

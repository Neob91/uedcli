# uedcli plugin — session handoff

Branch: `worktree-geometry-alignment-skills`. Not merged to master.

## What's here

A Claude Code plugin with two skills for using the `brush relation find/measure/set` family:

- `skills/verifying-brush-relations/SKILL.md` — sweep every face of a room-shaped brush before/after
  a `brush vertex move`/`scale`/`apply-transform`, to catch collateral changes on faces you didn't
  touch.
- `skills/positioning-a-brush/SKILL.md` — use `measure`/`set` to place a new or moved brush flush
  against a reference face instead of hand-computing `Location`.
- `references/brush-relation-basics.md` — shared `find`/`measure` mechanics referenced by both.

Separately, `uedcli/relation.py` and its CLI (`uedcli/cli/commands/brush/relation.py`) were
redesigned and fixed this session — already merged to master (`adc21b67`, `76a3f8a4`), not part of
this branch's diff.

## Testing

Both skills were pressure-tested against 12 real design requests, run twice each (no skill / skill
loaded), against real chunks extracted from three original Deus Ex maps (`level import` from the
retail `.dx` files, not synthetic geometry): UNATCO HQ (Manderley's office), NYC_Bar, WanChai
Market. 24 of 24 runs completed; one run (WanChai corridor-widen, no-skill) took ~55 minutes and
finished after the consolidated artifact below was already published — it hit the same
worktree-isolation shell-wedging bug several other agents hit this session, recovered via a
freshly spawned proxy agent, and is not reflected in the artifact's wc_widen scenario.

That late run is also not a clean comparison against its skill-equipped counterpart: the request
("widen the corridor") was ambiguous over which of two corridor-shaped voids in this chunk it
meant, and the two runs picked different ones. The no-skill run picked `Brush1239` (a stairwell
shaft) and widened it along with the two stair flights and landing that share its walls (6 brushes
moved together); verified clean (`level doctor` clean, flush contacts preserved exactly, no other
brush touched), modulo two acknowledged unknowns — no BSP build was run, and the moved wall sits
exactly on the extraction chunk's boundary, so collision with geometry outside this chunk is
unknowable from here. The skill-equipped run picked `Brush1159` (a separate upper corridor) and
found it collides with a support column — see the finding below. Full report:
`/tmp/claude-501/-workspace-uedcli--claude-worktrees-brush-relation-family-plan/92851c21-4f9f-4362-a013-350eb0f22f3f/tasks/a6d9abf07823291d9.output`
(session-local, may not survive past this session).

Full agent transcripts, working project copies, and rendered diagrams are preserved under
`/home/agent/.claude/jobs/92851c21/tmp/` (`batch2/`, `manderley_office/`, `bar_room/`,
`wanchai_area/`, `final_gallery/`) — not part of this repo, session-local.

Consolidated results, with before/after images and a verdict per scenario:
https://claude.ai/code/artifact/a4517d3b-1e91-485e-b52e-3bedb96893c5
(published before the late run above finished — its wc_widen scenario still shows the no-skill
side as incomplete).

## What the testing changed in the skills

Two bugs in the skill text were found and fixed as a direct result of these runs:

1. **`positioning-a-brush`'s mating-face rule.** Originally stated unconditionally: pick the face
   whose normal is anti-parallel to the reference's. This is wrong whenever the reference is a
   subtractive room brush (its stored normal points out of the void, into the solid — inverted
   from an additive brush's convention), which is the common case for an interior wall. 6 of 6 runs
   that mated against a subtractive reference hit this and had to override the skill's own
   instruction, verifying by hand which face was actually correct. Fixed to key off the reference's
   `CsgOper`.

2. **`verifying-brush-relations`'s default footprint filter.** `find`'s default filter drops any
   pair with no footprint overlap. On one run (Manderley office floor lowered 32uu), 3 of 8 brushes
   that ended up detached from the moved face were only visible with the full `--footprint
   none,vertex,edge,partial,contains,coincident` set — invisible under the default filter, before
   and after the edit. The full sweep was promoted from an optional aside to the pattern's default,
   a stated pass criterion was added, and `footprint_2d` (not raw `distance`) was named as the
   primary signal — a wall widening moves corners within its own plane, so faces perpendicular to
   it show no distance change at all, only a footprint-category change.

## What the testing found about end states, independent of the skills

Across the 6 "reshape an existing room" scenarios (ceiling raises ×3, a floor lower, room
widens ×2), 4 ended with real defects left uncorrected in the trunk, regardless of whether the
skill was used: two runs left brushes/fixtures detached from the face that moved (floating
48–64uu away from where they used to sit flush); one run's edit put the floor 32uu below three
adjoining floors, exceeding this project's own documented max step height of 25uu at two
doorways; one run's edit sliced through a support column and left it that way. In every one of
these cases the agent (baseline or skill-equipped) detected and reported the problem accurately,
then stopped and asked rather than fixing or reverting it — no run went back and resolved what it
found. Widening the bar's main room and all 6 "add a new brush" scenarios ended in a finished,
defect-free state. The late-finishing WanChai corridor-widen no-skill run (see above) also ended
defect-free by its own verification, on the different brush it chose to widen.

None of the flagged defects in those real-level working copies were fixed as part of this
session — they remain as agents left them, under the job-tmp paths above.

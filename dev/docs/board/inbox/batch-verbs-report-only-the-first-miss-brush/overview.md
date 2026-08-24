+++
priority = "p3"
kind = "debug"
summary = "batch verbs report only the first miss (brush clip/scale/transform, classify set|unset)"
+++

# batch verbs report only the first miss instead of aggregating

Several set-operating verbs raise on the first failing element instead of collecting all failures,
so a user fixing one bad element only discovers the next on a re-run. No partial writes reach disk
(saves commit after the loop), so this is a UX/consistency defect, not corruption. `snap()` in
`brush/edit.py` and `docs.py:75-85` show the correct aggregate-then-error pattern in-tree.

- `cli/commands/brush/edit.py:245-250` (`clip`) — raises on the first failing actor, DESPITE its own
  loop comment (lines 225-228) promising "all-or-nothing across the set... decided over the whole set
  before any stdout." Highest-priority of this cluster because it contradicts a documented contract.
- `cli/commands/brush/edit.py:403-404,436-437` (`_scale`), `:483-487` (`_apply_transform`) — same
  first-miss shape, no all-or-nothing comment.
- Batch classify: `audio.py:208-224,246-251`; `classes.py:415-431,453-459`;
  `texture.py:316-330,361-367`; plus `audio.py:54-59` (`--package` validation).

Fix: aggregate misses into one value-naming `CommandError` per verb (mirror `snap()`/`docs.py`).
Tests asserting all bad names are reported.

Reported with exact line quotes by the CLI-conventions lens; `clip` contract mismatch confirmed by
direct read of the sibling `snap()`.

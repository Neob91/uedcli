+++
priority = "p?"
kind = "owner-question"
summary = "Board-hygiene 2026-07-18: pruned stale session-store / editor-screenshot items — do any capabilities want re-framing for the git-native world?"
+++

# Board-hygiene 2026-07-18: pruned stale session-store / editor-screenshot items — do any capabilities want re-framing for the git-native world?

Removed from the board because their
entire design premise (the deleted event-sourced session store `session.py`/`replay.py`/`merge.py`/
`reconcile.py`/`integrity.py`, or the deleted editor-screenshot preview renderer `preview_render.py`)
no longer exists (direction/trunk-and-editor.md, 2026-07-05 14:58 git-branches-replace-sessions; 2026-07-16 12:13
two-backend preview). Deleted items: `session stop` removal (verb already gone); `level preview` =
one-shot editor screenshot (now two-tier `--game`/`--native`); Scale support spec (SHIPPED
2026-07-18); `session verify --deep` (command-log replay of the deleted store); `merge --sessions
A B → C` (now a plain `git merge` of two feature branches); field-level 3-way non-geometry merge (was
`reconcile.py`/`plan_apply` — per-actor `.t3d` now merge natively via git); derive-`packages`-set
(there is no stored package manifest anymore — `direction/README.md`). The genuinely-dead ones are simply
gone; the two whose *capability* might still be wanted in git terms are flagged here: (a) combining
two in-flight work units before merge, and (b) smart per-property merge when git's line-merge is too
coarse for non-geometry props. Keep/drop your call.

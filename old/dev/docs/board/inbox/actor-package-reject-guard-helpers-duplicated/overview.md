+++
priority = "p3"
kind = "chore"
summary = "actor package: reject-guard helpers duplicated in routes.py and edit.py"
+++

# actor package: reject-guard helpers duplicated in routes.py and edit.py

Slice 10 moved the actor family into `uedcli/cli/commands/actor/`. Two trunk-only surface guards,
`_reject_nonlevel_target_for_folders` and `_reject_nonlevel_target_for_labels`, now exist as
byte-identical copies in both `routes.py` (the source-free pre-resolution guards) and `edit.py` (the
CARRIER check inside `_ingest_actor_t3d`, a distinct post-parse rejection).

The duplication is deliberate: a feature module never imports the family route (`edit` importing
`routes` would be the wrong direction and risk an intra-family cycle the final AST rule forbids). The
guards are 3 lines each, so a copy was cheaper than a new shared module.

If a shared home is wanted later, a docstring-only `actor/_guards.py` imported by both `routes` and
`edit` would remove the copies without breaking feature isolation (it is not a feature module, so the
route matrix is unaffected). Not done now to keep this slice a literal move. No behavior change either
way.

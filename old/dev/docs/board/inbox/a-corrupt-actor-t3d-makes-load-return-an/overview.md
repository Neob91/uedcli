+++
priority = "p1"
kind = "debug"
summary = "A trunk actor.t3d with git conflict markers makes every GUI Reload answer 500 internal error, naming the offending file only in the server log, so the level is unusable in the GUI with no diagnosis"
+++

# A corrupt actor.t3d makes Load return an unnamed 500

Found by code review while landing `changes-available-banner-dies-after-a-serve`, reproduced
through the real app. Pre-existing (`read_level` has always raised here) and wider than that
change, so filed rather than fixed there.

`t3dtree.load_actor_body` raises a bare `ValueError` for a body it cannot parse — the common git
text-merge shape, conflict markers around a property with no `Begin Actor` in the hunk:

    actors/Merged/actor.t3d: no parseable actor (corrupt, truncated, or unresolved merge markers?)

`serve/errors.py`'s `error_to_status` does not classify a bare `ValueError`, so
`_domain_error_handler` turns it into `500 {"error": "internal error"}`. The message naming the
file reaches the server log only, which a GUI user never sees.

What the user gets: the banner is up (correctly — `stamp_actor_tree` stamps the file, so the disk
digest really has moved), every Reload click answers "internal error", and nothing says which actor
or why. The level is unusable in the GUI with no route to a diagnosis.

This is the same wedged-banner symptom `changes-available-banner-dies-after-a-serve` closed, reached
by a RAISE rather than a reject — not a regression of that fix, which made the stamped-and-rejected
set agree on both sides. A raise never reaches the comparison at all. A non-UTF-8 `actor.t3d`
(`UnicodeDecodeError` out of `read_text`) is the same shape.

Likely fix: classify a corrupt-trunk read as a domain error so the response names the offending
file, per CLAUDE.md's "never let a Python exception reach the user" and "error messages include the
offending value". Whether ONE bad actor should fail the whole Load or be reported and skipped is a
real design question: the no-silent-half-answers rule points at failing, but a trunk the user cannot
Load at all is also how they lose access to 2000 good actors. Needs a ruling before building.

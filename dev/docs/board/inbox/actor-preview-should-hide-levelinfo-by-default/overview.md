+++
priority = "p3"
kind = "implement"
summary = "actor preview should hide LevelInfo by default"
+++

# actor preview should hide LevelInfo by default

`actor preview` renders the `LevelInfo` actor (a management/singleton actor, not level
geometry) as a sprite/marker in the middle of the frame, cluttering the view. It should be
hidden by default (or excludable via a flag).

Owner ruling (2026-08-24): LevelInfo should be hidden from the preview.

Workaround in use: the MegaGrant demo pipes `actor find | grep -v LevelInfo | actor preview -`
to drop it. That's demo-side only — the real fix belongs in `actor preview` (skip `LevelInfo`,
and likely other non-geometry singletons, by default; add `--show-management`/`--all` if a caller
ever needs them).

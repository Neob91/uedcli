+++
priority = "p?"
kind = "implement"
summary = "Subtractive CSG: remaining CLI surface"
+++

# Subtractive CSG: remaining CLI surface

Round-trip + carving verified live;
the first-class intersect/deintersect verb is superseded by `stash intersect`/`stash deintersect`.
REMAINING: (2) wire `--solidity` flags through a live verification; (3) expose CSG order /
select-by-type as CLI verbs. See `unrealed/quirks.md` "CSG model". ALSO unify the fragmented brush namespace (2026-07-19 probe): add `brush find`/`brush list`, and note CSG-reorder lives on `actor order` + intersect on `stash`.

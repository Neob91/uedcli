+++
priority = "p2"
kind = "implement"
summary = "Author-time validation of ObjectProperty refs (AmbientSound/Song/OpeningSound/mesh/…)"
+++

# Author-time validation of ObjectProperty refs (AmbientSound/Song/OpeningSound/mesh/…)

A typo'd object-property ref currently exits 0 and ships a silently-broken level — the same class of gap `class`/`texture` validation already closed for class + texture refs. Spec author-time existence-validation of object-valued props against the composed package set. Rides the unified asset catalog's ENUMERATION layer for the reference set (specced 2026-07-25, `specs/2026-07-25-unified-asset-catalog.md` §8) — it needs enumeration only, NOT classification, so it is not gated on the catalog being populated. (Surfaced 2026-07-19 usability probe.)

+++
priority = "p2"
kind = "docs"
summary = "The residual 29 tail nodes — `zones.rs` `TestVisibility` Pass D fragment-splits — are now PORTED; native node count 1156 = editor, plane multiset (fp-tolerant) 1156/0/0"
+++

# The residual 29 tail nodes — `zones.rs` `TestVisibility` Pass D fragment-splits — are now PORTED; native node count 1156 = editor, plane multiset (fp-tolerant) 1156/0/0

RESOLVED` **The residual 29 tail nodes — `zones.rs` `TestVisibility` Pass D
fragment-splits — are now PORTED; native node count 1156 = editor, plane multiset (fp-tolerant)
1156/0/0.** DONE 2026-07-18 (`sections/70` §9 rewritten + `sections/82` §10.11 follow-up).
`zones.rs` Pass D now faithfully ports `AssignAllZones` (`0xa7400`): each node's polygon is
re-filtered through the chain head's back-then-front subtrees, and a face whose landings disagree
per side is split into one fragment node per surviving zone (moat/water outer walls `w=±500/±410`
fan out — surf 354→10 nodes, 355→10, 349/350→8). Replaces the never-split centroid sampler. Bonus:
the filter-based Pass D also drops the old `(0,0)×2` solid-solid nodes to `×0` (exact editor
match) and the whole iZone distribution now matches the editor under the zone-number permutation
(native 1↔editor 2). `test_case_f_portal_full_compare` un-xfailed (now full parity).

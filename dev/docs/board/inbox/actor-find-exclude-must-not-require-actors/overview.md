+++
priority = "p1"
kind = "unknown"
summary = "`actor find --exclude` must NOT require actors on stdin (refinement of the composable-`find` item above, 2026-07-24)"
+++

# `actor find --exclude` must NOT require actors on stdin (refinement of the composable-`find` item above, 2026-07-24)

`--exclude` used WITHOUT a piped-in set should not error/no-op — it should
simply SUBTRACT the actors that match the filters from the whole level and return everything else (the
complement over all actors), i.e. `find <filters> --exclude` = `all-actors ∖ (matched-by-filters)`. With
stdin it subtracts from the piped set (`piped ∖ matched`, per the item above); without stdin the implicit
set is the whole level. This makes plain NOT a single command (`find --label hero --exclude` = every actor
that is NOT `hero`) instead of forcing the two-stage `find <all> | find --label hero --exclude -` pipe.
Fold into the composable-`find` spec — it's the same `-`/`--exclude` design, just fixing the default input
set when stdin is absent. Andrzej flagged.

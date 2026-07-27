+++
priority = "p?"
kind = "unknown"
summary = "Review-gate rounds 2 and 3 on the same batch — resolved 2026-07-25"
+++

# Review-gate rounds 2 and 3 on the same batch — resolved 2026-07-25

Round 2 (two cold
reviewers) withdrew the round-1 "the move is a COPY" inference (see the round-1 entry below),
tightened `container_stat`/`container_file_head` so a `stat`/`od` FAILURE no longer reads as "file
absent", added the minimum-table-size rule, hoisted `brush scale --pivot-actor` above the class
resolver, and corrected the `is_solid`/seven-verbs/caller-name claims. Round 3 (**three** cold
reviewers — load-bearing code) found the fixes' own defects: three quoted measurements were wrong
(the corpus is 264 packages on the composed path, not an ad-hoc 230; the offsets-only worst case is
99.0 %, not 99.8 %; the tightest per-entry margin is 4 bytes in `Quotes_Music.umx`, not 22 in
`MPCharacters.u`), the per-entry minimums contradicted their own derivation (now the true bounds
5/7/12, which also shrinks the blind window), the header-verdict cache was permanent and justified
by the very hypotheses round 2 had withdrawn (now bounded by `recheck=30 s` and reset when the file
vanishes), the pre-save-stat signal had two surviving mutations, and the `core.dll` extraction had
landed with **no committed harness and no regression** — the one rule that keeps a spike from
rotting. That is now `spikes/2026-07-25-map-save-mechanism/` (two harnesses + write-up) plus
`test_engine_facts.py`, which re-asserts both the string-run order AND the "no `ReadFile` ⇒ the
import table settles nothing" negative so the retracted inference cannot be re-derived silently.
**Left standing, with reasons:** `preview.classify_brush`'s name-suffix predicate (logged in
`board/to-spec/` as part of the open scoping decision — pre-empting it is Andrzej's call, not the
batch's), and the unpushed commits (the orchestrator owns pushing this branch). **A round-3
finding was dismissed as a false positive:** `--pivot`/`--pivot-actor` are already an argparse
mutually-exclusive group on both `brush scale` and `actor rotate`, verified by running both.

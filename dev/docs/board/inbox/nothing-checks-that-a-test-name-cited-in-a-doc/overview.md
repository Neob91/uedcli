+++
priority = "p3"
kind = "implement"
summary = "Nothing checks that a TEST NAME cited in a doc still exists"
+++

# Nothing checks that a TEST NAME cited in a doc still exists

, so a rename
silently orphans the citation. `test_doc_links.py` already verifies every markdown link and anchor
in the tracked tree, but a citation like
`` `test_surface.test_apply_rotate_absolute_branch_brackets_...` `` is prose, not a link, and is
invisible to it. Live instance, 2026-07-27: renaming a test from `..._accepts_...` to
`..._brackets_...` while resolving a review finding left `rationale/surface.md` citing a name that
matched nothing — a future agent grepping for it would find no test and could reasonably conclude
the behaviour is unpinned. Caught by a reviewer, not by the suite.

These citations are load-bearing precisely where `rationale/` is: an entry's `Refs` is how a later
session checks whether a claim is still pinned. A check would be small — collect
`` `test_<module>.test_<name>` `` and `` `..._<name>` `` tokens from the tracked docs and assert
each resolves to a `def` in `uedcli/tests/` — and it extends an existing test file rather than
adding a subsystem. Worth doing when something next touches `test_doc_links.py`.

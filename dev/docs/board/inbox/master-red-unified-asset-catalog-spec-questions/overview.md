+++
priority = "p2"
kind = "debug"
summary = "master suite red: unified-asset-catalog spec/questions cite four-open-catalog-decisions.md, tripping the deleted-decisions.md substring check."
+++

# master red: unified-asset-catalog trips the deleted-doc check

Two `test_doc_links` cases fail on `master` (seen at `fb5d190`), both from the in-flight
`unified-asset-catalog` texture-arm edits:

- `test_no_citation_of_a_deleted_doc` — `decisions.md` was retired, and the check flags any tracked
  file containing the substring `decisions.md`. `spec.md` and `questions/texture-rekey-across-a-pixel-edit.md`
  reference the question file `four-open-catalog-decisions.md`, whose name ends in `decisions.md`, so
  the substring check false-positives.
- `test_markdown_links_resolve[.../unified-asset-catalog/overview.md]` — one markdown link in that
  `overview.md` does not resolve.

Not caused by the to-build run — left untouched because `unified-asset-catalog` is owner-active in a
parallel session. Fix options: whitelist those paths in `_MAY_NAME_DELETED`, or tighten the check to
word-boundary/link matching so `four-open-catalog-decisions.md` no longer matches `decisions.md`.
The overview link is a real dangling ref to fix.

+++
priority = "p1"
kind = "chore"
summary = "The `uedctl`→`uedcli` rename shipped UNGATED — it never had its build review"
+++

# The `uedctl`→`uedcli` rename shipped UNGATED — it never had its build review

The whole-repo rename (777 files, 5383±5383 lines, all three case variants, plus 12 doc filenames
and the `uedctl/`→`uedcli/`, `uedctl-native/`→`uedcli-native/`, `bin/uedctl`→`bin/uedcli`,
`2026-06-27-decontainerize-uedctl/` path moves) was committed on the owner's explicit instruction
to "commit and worry about reviews later", so the `build` round CLAUDE.md "Review gates" requires
was deliberately skipped, not passed. `bin/test` was green (3345 passed, 16 skipped, 64 deselected,
1 xfailed, + 58 cargo goldens) and `git grep -i uedctl` is empty, but no cold reviewer ever read
the diff. What a reviewer would have been asked to check, and what therefore remains unverified:
a substring that merely *contained* `uedctl` but denoted something external (docker image/tag
names, registry names, anything crossing a repo or machine boundary) and now points at nothing;
word-boundary damage; cross-doc links into the 12 renamed filenames; and whether the diff is
purely mechanical. Run a `build` round over `git show <rename-commit>` when convenient.
*(2026-07-26.)*

+++
priority = "p1"
kind = "docs"
summary = "no quickstart / first-level walkthrough exists in docs/"
+++

# no quickstart / first-level walkthrough exists in docs/

No page walks an agent through creating and building its first level end-to-end. `docs/README.md`
sends the reader straight to skimming the full ~2000-line `usage.md`. The closest thing that exists
is `docs/leveldesign/README.md`'s "The composing pattern" intro section, which is a snippet, not a
walkthrough.

Minor addendum (fold into this item, not a separate one): `docs list` prints bare topic keys with no
titles unless `--json` is passed, and link targets inside served docs are relative file paths while
the actual addressing surface for `docs show` is topic keys — no doc states the conversion rule
between a relative link and the topic key `docs show` expects.

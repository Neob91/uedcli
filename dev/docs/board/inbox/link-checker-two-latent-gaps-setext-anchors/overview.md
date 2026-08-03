+++
priority = "p3"
kind = "chore"
summary = "Link checker: two latent gaps (setext anchors; exemption over-collection)"
+++

# Link checker: two latent gaps (setext anchors; exemption over-collection)

Recorded here before the retired migration ledger (which held the original review record) was
deleted. Both are latent — neither reddens the suite today.

1. **Setext headings are invisible to the anchor check.** `_HEADING` in
   `uedcli/tests/test_doc_links.py` matches ATX headings (`# …`) only, so an anchor into a setext
   heading (a line over `===`/`---`) reads as missing. Only a couple of instances exist, both in
   spike docs. Pinned as a code comment at `_HEADING`.
2. **Exemption over-collection (historical).** The old `_on_deck` exemption collector over-collected
   ~28 entries, including non-ephemeral files. It could only ever ADD checking, never remove it — the
   safe direction. `_on_deck` has since been replaced by the `_EPHEMERAL_SHAPE` path test; the
   conservative-direction principle it embodied is stated in that module's docstring.

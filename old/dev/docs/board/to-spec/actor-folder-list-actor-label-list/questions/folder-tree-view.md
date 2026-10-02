# A `folder tree` hierarchical view — build it here, or defer?

## Context

The overview floats a `folder tree` view that renders the folder hierarchy indented (labels are
flat, so there is no label equivalent). It is a different verb and a different output shape from the
flat `folder list`.

- **A — defer to its own item (recommended).** Ship the two flat `list` verbs now; file a separate
  board item for `folder tree` if the indented view is actually wanted. Keeps this item small and
  single-purpose.
- **B — include `folder tree` in this item.** One more parser, a tree-rendering formatter (indent by
  dotted-segment depth), and its own tests, alongside the two `list` verbs.

Recommendation: **A**. The stated need — "what folders/labels exist" — is the flat `list`; a tree
renderer is additive craft that shouldn't gate the enumeration verbs.

## Answer

<!-- Empty = open. -->

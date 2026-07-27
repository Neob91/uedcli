+++
priority = "p3"
kind = "implement"
summary = "Reconcile `level doctor --category` to the `class show --category` shape"
+++

# Reconcile `level doctor --category` to the `class show --category` shape

Surfaced
in the `class show --category` spec review (2026-07-18). `level doctor --category` is comma-split +
case-sensitive with a bare `print;return 2` on a bad value; `class show --category` (specced) is
repeatable-append + case-insensitive + `_SelectionExit`-listing. Two same-named flags that parse/fail
differently is a wart — migrate `level doctor --category` to the append + case-insensitive + listing
shape (keep accepting comma-lists for back-compat if cheap). Spec:
`spec.md`.

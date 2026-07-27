+++
priority = "p3"
kind = "debug"
summary = "A positive-but-degenerate `--angle` builds a NON-MANIFOLD revolve at exit 0"
+++

# A positive-but-degenerate `--angle` builds a NON-MANIFOLD revolve at exit 0

`brush build revolve --angle 1 --segments 1 --point 64,0 --point 192,0 --point 192,128
--point 64,128` exits 0 with only the off-grid advisory, and `level doctor` then reports
`edge … is shared by 4 faces (non-manifold)`. Confirmed IDENTICAL on `master`, so the profile
generators did not introduce it — a 1-uu sweep collapses the near and far rings to within
`WELD`. Same family as the degenerate-dimension item below, but that one names only
`--depth`/`--height`, so this instance would otherwise go uncaptured. The fix likely belongs
with it: a minimum representable sweep, named per flag. (Round-2 build review, 2026-07-26.)

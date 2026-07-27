+++
priority = "p3"
kind = "unknown"
summary = "Fitting a texture to an OPEN run — the sibling `--fit-perimeter` does not cover"
+++

# Fitting a texture to an OPEN run — the sibling `--fit-perimeter` does not cover

board item `the-per-surface-verb-split` restricts `--fit-perimeter` to CLOSED runs, because "fit an
integer texel count so the loop closes" needs a loop. But "snap the density so a whole number of
texels spans this wall run / this staircase stringer" is a legitimate and probably more common
request, and it has no verb. It wants a different flag name (perimeter implies closure) and a
decision about which end absorbs the residual. Raised by spec review round 2, which correctly
pointed out the restriction was asserted rather than argued; recorded here rather than folded into
that spec, whose gate had already run.

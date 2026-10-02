#!/usr/bin/env python3
"""Settle the `order_value` encoding (spec 2026-07-05 §5/§13).

The concurrent "insert between two neighbours" op subdivides a gap. The question is only whether the
encoding hits a FIXED-WIDTH precision floor. This proves the principle:
- fixed-width float64 midpoint EXHAUSTS after ~52 subdivisions of one gap;
- a variable-length key (here exact Fraction; LexoRank strings are the git-friendly string form of the
  same idea) does NOT — it just grows.
So the encoding must be variable-length. Recommendation: LexoRank-style lexicographic strings.
"""
from fractions import Fraction


def float_exhaustion():
    lo, hi, n = 1.0, 2.0, 0
    while True:
        mid = (lo + hi) / 2
        if not (lo < mid < hi):          # can no longer fit a value strictly between
            return n
        hi = mid                         # repeatedly insert just above lo (worst case)
        n += 1
        if n > 100000:
            return n


def fraction_no_exhaustion(iters=5000):
    lo, hi, n, maxdig = Fraction(1), Fraction(2), 0, 0
    for _ in range(iters):
        mid = (lo + hi) / 2
        assert lo < mid < hi, "variable-length key exhausted (should be impossible)"
        hi = mid
        n += 1
        maxdig = max(maxdig, len(str(mid.denominator)))
    return n, maxdig


if __name__ == "__main__":
    fe = float_exhaustion()
    fn, digits = fraction_no_exhaustion()
    print(f"float64 midpoint: EXHAUSTED after {fe} subdivisions of a single gap "
          f"(cannot insert between neighbours past that)")
    print(f"variable-length key: {fn} subdivisions with NO exhaustion "
          f"(exact; denominator grew to {digits} digits — a LexoRank string grows in length instead)")
    print("VERDICT: fixed-width float is unusable for concurrent insertion; use a variable-length "
          "encoding (recommend LexoRank-style strings — git-diff-friendly, rebalance-free).")

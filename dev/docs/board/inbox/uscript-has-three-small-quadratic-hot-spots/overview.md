+++
priority = "p3"
kind = "implement"
summary = "uscript has three small quadratic hot spots fixable mechanically"
+++

# uscript has three small quadratic hot spots fixable mechanically

Three independent, small, low-risk fixes found in the same 2026-09-12 audit pass as
`uscript-compile-package-dir-is-o-n-2-in-classes` and `uscript-resolve-class-has-no-memoization-and`.
Bundled here because each is a one-line/mechanical change, none touches serialization order or
byte-parity-sensitive logic:

1. **`ordering.py::_gather_names`** (227-274) — `seen: list[str] = []` with
   `if n not in seen: seen.append(n)` (243-245) is O(n) per insert, O(n²) over the gathered name
   count. Runs once per `order_package` call, scaling with package name-table size. Fix: keep a
   parallel `set()` for the membership test, keep the list for order (order-preserving, no behavior
   change).

2. **`compile.py::_function_positions`** (587-638) — `crlf.count("\n", 0, k)` (616, 636) recounts
   newlines from position 0 for every function instead of continuing from `cur` (already tracked as
   the previous function's end). O(n·F) instead of O(n) for a class with F functions over n
   characters. Fix: maintain a running line counter, only count newlines in `crlf[cur:k]`.

3. **`compile.py::_super_field_order`** (831-850) — walks up to 64 ancestors, re-decoding each
   ancestor's full field list from scratch, with no cache keyed by super-class name. Sibling classes
   sharing a deep ancestor each redo the identical chain. Fix: memoize by casefolded class name for
   the lifetime of one package compile.

Found by: 2026-09-12 performance audit (subagent-driven, uscript-compiler scope).

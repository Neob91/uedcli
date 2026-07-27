+++
priority = "p3"
kind = "debug"
summary = "`parse_decimal` admits an INFINITY by another spelling — `1e999999999` is finite as a `Decimal` and infinite as a `float`"
+++

# `parse_decimal` admits an INFINITY by another spelling — `1e999999999` is finite as a `Decimal` and infinite as a `float`

Reproduced 2026-07-26:

```
parse_decimal('1e999999999')  → Decimal('1E+999999999'), .is_finite() is True
float(that)                   → inf
brush clip --axis z --offset 1e999999999  → plane ((0.0, 0.0, inf), (0.0, 0.0, 1.0))
actor move --to 1e999999999,0,0           → the same, per component, via parse_coord
```

**Mechanism.** `parse_decimal` rejects the *literal* non-finite spellings (`nan`/`snan`/`inf`)
with `Decimal.is_finite()`, and that check is correct: `Decimal` has arbitrary exponent range, so
`1E+999999999` genuinely IS a finite decimal. The infinity is created later, by the
`Decimal`→`float` conversion at the geometry boundary (`clip.axis_plane`, and every computed-
geometry module that finalizes through floats), where the value overflows IEEE-754 double.

**Nothing observable breaks today**, which is why this is logged rather than fixed: with an
infinite plane offset, `--keep below` is a clean no-op ("clip plane did not intersect brush …",
exit 0) and `--keep above` or a negative offset is a clean `GeometryError` → exit 2. No traceback,
no silent wrong geometry.

**Why it is deferred rather than fixed in the 2026-07-25 chore batch:** the hole is not in the
validator, it is in where `Decimal` is allowed to lose range on its way to `float`. Fixing it
properly means deciding that boundary — a float32/float64 representability bound on every
coordinate entering the geometry layer, not one more `is_finite()` call in `cli.py` — and that is
wider than a chore. It also overlaps the specced "uniform Decimal map coordinates" work. The two
places that claimed the validator prevents an infinite value reaching the model
(`cli.parse_decimal`'s docstring, `rationale/cli.md`) were corrected 2026-07-26 to state this gap
instead of asserting it away. (Build-review round 2, 2026-07-26.)

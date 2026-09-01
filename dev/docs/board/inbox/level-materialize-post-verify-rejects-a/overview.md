+++
priority = "p?"
kind = "unknown"
summary = "level materialize post-verify rejects a negative poly Pan that round-trips as its 16-bit-wrapped positive equivalent"
+++

# level materialize post-verify rejects a negative poly Pan that round-trips as its 16-bit-wrapped positive equivalent

Hit live 2026-09-01 on `demo/showcase-bar.sh`'s `BarStatementSign` (`brush poly pan --to 256,-64`).
`level photo --game` (→ `materialize`) failed with:

```
post-verify mismatch: ... actor 'BarStatementSign_wrdu91' differs in GEOMETRY at line 34:
    built:    Pan      U=256 V=65472
    intended: Pan      U=256 V=-64
```

`65472 == -64 mod 65536` — the editor stores/re-exports a poly `Pan` component as an unsigned
16-bit field (same family as the FRotator mod-65536 behavior in `dev/docs/unrealed/quirks.md`
"Rotation (FRotator) trig"), but the trunk keeps the authored value signed. Post-verify
(`uedcli/verify.py`) diffs the built and intended actors as exported T3D text, line by line, so a
signed `-64` and its wrapped `65472` render as different text and read as a geometry mismatch —
not an integer compare specifically, just no unwrap step before the text diff. Worked around in
the demo by panning to a positive equivalent (`256,192` = `-64 mod 256`, the texture's tile
period) instead of fixing the comparison — out of scope for the demo-rework task this was found
during.

Likely fix location: wherever poly `Pan` is compared in `normalize.py`'s post-verify path (see
`dev/docs/unrealed/t3d.md` "Polygon sub-fields reference" — `Pan` has no class default, unlike the
FRotator case, so this needs its own fix, not reuse of the rotator rule). Not yet verified whether
`brush poly pan` accepts/stores a value outside a signed range, or whether the demo's positive
value is coincidentally safe only because it stays within [0, 65535).

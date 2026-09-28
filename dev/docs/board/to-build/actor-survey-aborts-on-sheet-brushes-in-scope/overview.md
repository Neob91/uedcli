+++
priority = "p1"
kind = "debug"
summary = "actor survey aborts on sheet brushes in scope"
+++

# actor survey aborts on sheet brushes in scope

`actor survey <NAME>` exits non-zero with:

```
actor survey: Brush197: brush does not bound a valid solid (a decomposed cell has no volume)
```

whenever a **sheet brush** falls within the surveyed neighborhood.

## Repro (level 19_Multiport, dx_scratch project, uedcli @9bac057f)
- `actor survey RecD_114_4_0_ybbp5h` → aborts on `Brush197`.
- `actor survey Brush330` (on the far side of the map from Brush197) → also aborts on `Brush197`.

`Brush197` is a valid, intentional **sheet**, not a broken solid:
`Group="Sheet"`, polygon `Item=Sheet`, a single two-sided face (`Flags=264`),
`Texture=UNATCO.Stone.UN_Wall_White`, bbox size `(768, 0, 256)` — zero thickness, no
enclosed volume (a sheet is not supposed to have one).

## Impact
Survey cannot complete for any actor whose neighborhood contains a sheet. On 19_Multiport it
fails even for distant target actors, so `actor survey` is currently unusable on the whole
level. Sheet brushes are common (decoration panels), so this blocks survey broadly.

(No fix direction recorded here — owner's call.)

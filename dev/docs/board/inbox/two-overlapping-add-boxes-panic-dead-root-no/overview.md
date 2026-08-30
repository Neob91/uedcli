+++
priority = "p3"
kind = "bug"
summary = "build_geometry_bspcsg panics (debug_assert, bsp_cleanup) on two overlapping ADD boxes: box(256,256,256 @0,0,0) + box(256,256,256 @200,0,0), both CsgOper::Add -- 'cleanup: dead root with no iPlane successor (unhandled Case B root)' at bspcsg.rs:450. Found incidentally while writing an unrelated TDD test; not investigated or fixed."
+++

# Two overlapping ADD boxes panic in `bsp_cleanup`

Found incidentally in `emptymodel-worldlevel-repartition-live-verify` while writing a TDD test that
needed two overlapping brushes. Not investigated — filed so it isn't silently dropped.

## Repro

In `uedcli-native/src/bspcsg.rs`'s test module:

```rust
let brushes = [
    box_brush(256.0, 256.0, 256.0, Vec3::new(0.0, 0.0, 0.0), CsgOper::Add),
    box_brush(256.0, 256.0, 256.0, Vec3::new(200.0, 0.0, 0.0), CsgOper::Add),
];
build_geometry_bspcsg(&brushes).unwrap();
```

Panics (debug build only — `debug_assert!`):

```
thread '...' panicked at src/bspcsg.rs:450:9:
cleanup: dead root with no iPlane successor (unhandled Case B root)
```

A less axis-aligned overlap (`box(192,160,224 @ 180,90,40)` instead of the second box above) does
NOT panic — so this looks geometry-specific (likely a coincident-plane / degenerate-split edge case
in `bsp_cleanup`'s root handling), not a universal two-brush-CSG bug.

## Not done

No live-editor comparison, no root-cause trace, no fix. Whether this is reachable from any of the 11
OG levels already measured in the breadth corpus is unknown — none of those crashed, so if it's real
it's rare, but `bsp_cleanup`'s debug_assert firing at all on a plausible two-box union is worth
someone's attention eventually.

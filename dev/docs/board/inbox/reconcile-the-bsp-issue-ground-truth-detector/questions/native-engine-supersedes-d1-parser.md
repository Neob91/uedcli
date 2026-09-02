# Does the shipped native CSG/BSP engine replace D1's planned editor-drop-warnings + new-UModel-parser design?

## Context

The spec's D0 drives the editor (`MAP REBUILD`) and parses drop-warning counts; D1 gates on building
a from-scratch binary `UModel` parser (P0-a) to read a saved `.dx`. Both are overtaken: the native
Rust engine builds the Model offline with no editor (`uedcli-native/src/bspcsg.rs`,
`lib.rs:503-504`), and a `UModel` reader already exists (`uedcli/native/umodel.py`), validated
surf-for-surf against editor goldens (`tests/test_csg_native_differential.py`). So the detector no
longer needs a new parser, and it can read the built Model directly.

Options:
- (a) Keep D0/D1 exactly as specced — a separate editor drive plus a new parser. Redundant with what
  exists.
- (b) Re-scope the located-issue detector to run over the native build's `Model` (Surfs/PolyFlags/
  leaves/zones it already produces). No editor at analysis time; reuses the validated path.
- (c) Keep only D0's editor drop-warning pass as a cheap CI tripwire, and drop the D1 parser
  entirely — the native build subsumes the "read the saved model" half.

Recommendation: (b), optionally plus (c). Build the detector on the native `Model`; keep D0's
editor drop-warnings only where the editor confesses something the native build cannot yet reproduce
(e.g. channels the native path doesn't emit). This makes the from-scratch D1 parser unnecessary.

## Answer

<!-- Empty = open. -->

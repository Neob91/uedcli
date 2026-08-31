"""Native (editor-free) `.dx`/`.unr` codec + brush marshalling.

The proven byte-exact UE1 package serializers/parsers kept in Python, shared by
`level import` (`mapimport`), the built-model health check (`bsp.builtmodel`), and the
native `level photo` path. The BSP/CSG compute itself lives in the Rust `uedcli_native`
extension.

Module map:
  codec.py         - FCompactIndex + primitive read/write (shared)
  pkg_write.py     - UE1 package container: header/names/imports/exports/layout + parse
  umodel.py        - UModel body parse + write-from-arrays (Python dev oracle)
  actor_write.py   - StateFrame + FPropertyTag property list + struct layouts + UPolys/FPoly
  props.py         - N-3 typed-property conversion + late-bound import refs
  brush_marshal.py - brush actor -> CSG BrushTuple; world-CSG selection (used by brushcsg/preview)
  csg_golden.py    - editor-golden CSG differential capture harness (tests)
"""

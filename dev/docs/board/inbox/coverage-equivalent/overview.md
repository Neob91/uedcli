+++
priority = "p?"
kind = "unknown"
summary = "coverage-equivalent"
+++

# coverage-equivalent

Native has 438 surfs vs editor 485 (over-consolidated coplanar fragments from the un-ported
`bspOptGeom` trim, documented in `build.rs::find_best_split`) — but this is **coverage-equivalent**
(rasterizer proves it) and does NOT cause black. No fix made: nothing in the sky/zone/geometry
scope (`zones.rs`/`materialize.py`/`assemble.py`) is wrong. **Redirect to the lighting line.**

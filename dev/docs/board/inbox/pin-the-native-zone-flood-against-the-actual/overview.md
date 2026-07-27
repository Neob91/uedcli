+++
priority = "p3"
kind = "chore"
summary = "Pin the native zone flood against the actual RUST (not just the Python oracle), and test multi-zone Connectivity"
+++

# Pin the native zone flood against the actual RUST (not just the Python oracle), and test multi-zone Connectivity

The zone-flood BlockPortal fix (§70 §13) is validated editor-exact
via the harness oracle, and the shipped Rust is confirmed to reproduce the oracle on the native
UNATCO/Catacombs trees (45=44+1, 43=42+1) — but `tests/test_zone_flood.py` runs the Python oracle,
not the Rust; the only Rust-path zone tests (castle build, water-portal) are on NON-discriminating
topology. Add a `uedcli_native` FFI entry that runs `assign_leaves_and_zones` on an externally
supplied Model so a test can feed a shipped map's tree through the REAL Rust flood and assert
editor NumZones — or a synthetic map through the materialize path where the infinite-quad and
real-poly rules differ. Also: Pass F `Connectivity` (the zone adjacency bitmask) is untested on any
multi-zone map, and it iterates the `MIN_AREA`-filtered `portals` list while barriers are not
area-filtered, so a barrier pair whose only portal face is sub-`MIN_AREA` would lose its
connectivity edge (empirically clean: castle byte-identical; flagged, not observed). (Cold-review
findings, 2026-07-19.)

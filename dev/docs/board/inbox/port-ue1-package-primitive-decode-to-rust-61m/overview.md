+++
priority = "p1"
kind = "implement"
summary = "Port UE1 package primitive decode (read_compact_index/read_name/read_fstring/_parse_package) to Rust -- 61M-call hot loop"
+++

# Port UE1 package primitive decode to Rust

`level photo --native` on a real, actor-heavy level (original Unreal `IsvKran32.unr` / Vortex
Rikers: 1705 brushes, 1439 mesh actor instances) took ~75s wall clock, cProfile-scoped to
`build_scene` alone (2026-09-11). `bake_radiance` (this session's new lighting code) was 0.04s of
that -- not the bottleneck. The dominant cost is pure-Python UE1 package parsing, all in
`uedcli/upackage.py`:

| Function | Calls | Cumulative | Own time |
|---|---|---|---|
| `read_compact_index` (line 40) | 61,205,527 | 19.76s | 19.76s (leaf) |
| `read_fstring` (line 56) | 6,428,912 | 12.98s | 7.04s |
| `read_name` (line 208, inside `_parse_package`) | 6,428,452 | 15.23s | 2.25s |
| `_parse_package` (line 201) | 3,404 | 69.97s | 28.90s |
| `parse_package_bytes` (line 189) | 3,404 | 69.99s | 0.02s |
| `load_package` (line 177) | 3,404 | 78.40s | 0.59s |

These are small, self-contained, pure binary-format decoders (`FCompactIndex` varint, `FString`,
the name/import/export table walk) with no Python-object-graph side effects beyond building simple
tuples/dicts -- a natural, low-risk Rust port: same shape as `uedcli-native/src/light.rs`'s own
UE1-format decoding, callable via a `#[pyfunction]` returning the parsed `Package` (or its raw
tables) across the FFI, mirroring `serialize_model`'s existing pattern.

3,404 calls to `load_package`/`_parse_package` for ONE photo of ONE level is itself suspicious --
see the companion finding `upackage-load-package-has-zero-caching-3404` (a caching fix might cut
the CALL COUNT before this item cuts the PER-CALL cost; both are real, independent wins).

Repro: `dev/docs/spikes/` (none committed yet) -- the profile was a one-off `cProfile` run against
`preview_native.build_scene` on a freshly-imported `IsvKran32.unr` trunk, not yet turned into a
committed regression/benchmark harness. Do that as part of this item's spike/plan step.

+++
priority = "p3"
kind = "debug"
summary = "Native Model ships `bbox=(0,0,0)` — the Python parser drops the prefix bbox"
+++

# Native Model ships `bbox=(0,0,0)` — the Python parser drops the prefix bbox

p3.
Found 2026-07-15 (pre-existing, not lighting). `_build_level_model` does Rust-build → Rust-serialize
→ `umodel.parse_model_body` → assemble → `umodel.write_model_body`; the parser starts at
`pos=_PREFIX` and never captures the 42-byte UPrimitive prefix (FBox bbox + FSphere), so the parsed
Model defaults `bbox_min/max=(0,0,0)` and the final written map's Model bbox is zeroed (confirmed:
`NativeCSG.dx` prefix bbox = all zeros). Tolerated live (both lit + unlit native maps render / walk
with it — the engine recomputes/uses node bounds), but it IS a lost field. Fix: have
`parse_model_body` capture the prefix bbox (+ FSphere) and retain it, so the round-trip preserves it.
Low priority (harmless so far). The Rust serializer itself writes the correct bbox — it's only lost
on the Python re-parse round-trip.

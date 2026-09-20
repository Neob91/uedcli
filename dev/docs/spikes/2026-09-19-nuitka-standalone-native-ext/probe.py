"""Nuitka --mode=standalone + uedcli_native bundling probe (dev/docs/rules/spikes.md).

Proves or refutes that Nuitka auto-discovers and bundles a pyo3/abi3 compiled extension module the
same way it already handles Pillow's `_imaging` -- the single biggest unverified assumption in
docs/superpowers/specs/2026-09-19-standalone-binary-build-design.md. `build_brush_model([])` is a
real uedcli_native entry point (editor's csgPrepMovingBrush; uedcli-native/src/lib.rs) that needs no
level/project context, just an empty poly list -- a minimal but genuine call into the compiled Rust
core, not a stub.
"""
from uedcli.native_ext import import_native

native = import_native()
built, links = native.build_brush_model([])
print(f"OK: build_brush_model([]) -> links={links!r} built={built!r}")

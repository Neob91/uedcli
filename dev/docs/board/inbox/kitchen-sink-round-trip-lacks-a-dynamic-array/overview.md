+++
priority = "p3"
kind = "chore"
summary = "Kitchen-sink round-trip test lacks a dynamic-array case"
+++

# Kitchen-sink round-trip lacks a dynamic-array case

`uedcli/tests/test_native_roundtrip.py` covers nested struct, static-array struct props (mover
KeyPos/KeyRot), None ref, enum byte, over-range FRotator, PrePivot, grouped/2-part textures, and CSG
brush order — but no DYNAMIC array. No editable dynamic-array property was found in the committed
`uned/UED22` schema (Engine + DeusEx classes) to drive one via T3D; a scan of curated candidate
classes found none. Dynamic-array serialization is unit-covered by
`test_native_props.test_dynamic_array_is_count_then_elements`.

If integration-level dynamic-array coverage is wanted, find a class with an editable `array<...>`
settable via T3D (or synthesize one) and add a case.

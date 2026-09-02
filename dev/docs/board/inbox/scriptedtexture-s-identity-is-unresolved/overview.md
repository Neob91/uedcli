+++
priority = "p2"
kind = "owner-question"
summary = "`ScriptedTexture`'s identity is unresolved (50 of 326 procedural exports)"
+++

# `ScriptedTexture`'s identity is unresolved (50 of 326 procedural exports)

Falls out of the 2026-07-26 parameter-hash ruling (spec §3c): a procedural texture is keyed on the
properties that make it distinct, but a `ScriptedTexture` is drawn by UnrealScript at runtime, so its
appearance may not be a function of its stored properties at all. Its declared property set could be
empty, which would collapse every `ScriptedTexture` in a package to ONE identity. Acceptable (they are
canvases, arguably interchangeable) or does it need a different key? Flagged OPEN in the spec rather
than picked silently. *(2026-07-26.)*

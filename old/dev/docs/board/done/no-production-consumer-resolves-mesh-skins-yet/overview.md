+++
priority = "p3"
kind = "implement"
summary = "Mesh skins are resolved only by two spike harnesses, so no test can render one end to end."
+++

# No production consumer resolves mesh skins yet

Resolved: `class preview` calls `meshrender.resolve_skins` in production
(`uedcli/cli/commands/classes.py:210`), found stale while reviewing board item
`native-mesh-rendering-in-level-photo-native`.

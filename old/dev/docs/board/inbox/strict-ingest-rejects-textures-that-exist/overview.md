+++
priority = "p1"
kind = "debug"
summary = "Strict ingest validation rejects textures that DO exist, blocking level import of retail maps end to end."
+++

# Strict ingest validation rejects textures that DO exist, blocking `level import` of retail maps end to end

`level import DXMP_Cathedral.dx` exits 2 with `texture not found:
Effects.water.drtywater_a` while `Effects.utx` IS on the configured path (56 `.utx` present,
`Textures/Effects.utx` among them). So either `utexture.TextureResolver.exists` mishandles the
three-part `Package.Group.Name` form for this package, or the texture is stored under a name it does
not derive. Earlier it rejected `CoreTexMisc.Marker_sky` when only `System/` was configured, which
was correct; this one is not. The decode itself is fine — `import_map` produces the map's T3D — the
refusal is downstream, in the shared author-time gate. Reproduce: substrate at
`_scratch/dx/substrate`, `[games.deusex] paths` = its System:Textures:Sounds:Music.
*(2026-07-27, found while importing the retail corpus.)*

*Carried over from the `installer-url` branch, whose `inbox.md` addition the board migration had already deleted.*

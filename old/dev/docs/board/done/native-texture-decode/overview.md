+++
priority = "p1"
kind = "implement"
summary = "Decode every measured UE1 texture layout natively, reading the layout off the DATA rather than a format table."
spikes = ["dev/docs/spikes/2026-07-25-native-texture-formats/", "dev/docs/spikes/2026-07-26-ucc-texture-fixture/"]
+++

# Native texture decode for any UE1 package

**BUILT 2026-07-27** — three spec rounds and three plan rounds, 2026-07-25 to 2026-07-27; the spec
and plan were ephemeral and are deleted. `utexture.py` decoded one layout and stopped after the
first mip array, so a `UTexture`'s second array (`CompMips`) made the body parse overrun: **30
textures in the project's own `LUM/Textures/LUM_CoreTex.utx` were invisible and rendered as a
checkerboard**, 207 across the whole Deus Ex tree.

**What shipped, in eight slices.** Both mip arrays parsed, with `Mips` preferred over the lossy
compressed copy. A **typed decode result** — `DecodedTexture` or `TextureError` naming one of twelve
cases — replacing `None`-for-everything, with `resolve_masked` merged into `resolve`. The mip
pyramid and the `bMasked` flag on that result, the flag read as *the export's tag if present, else
the resolved class default*. **Layout detection from the mip chain**, where the format code breaks
ties and vetoes unverified slots but never contradicts the data and never sizes a chain. **BC1, BC2
and BC3** decode, byte-exact against Pillow. A two-tier corpus sweep with the three
`ETextureFormat` dumps pinned.

**The one documented limit:** a BC2/BC3 texture that stores no format code does not decode. The two
are byte-identical in size and differ only in how each block encodes transparency, so only a code
separates them and uedcli reports `ambiguous-alpha` rather than guessing. **Zero** of the 18,176
texture exports measured here hit it. A tagless BC1 file, whose 8-byte blocks are unique, decodes
normally.

**Durable record:** `dev/docs/unrealed/package-format.md` (the `UTexture` body and the arbitration
rule), `dev/docs/rationale/texture-decode.md` (why the code is shaped this way),
`dev/docs/architecture.md` (what it does), and the two spikes above for every measurement.

**Remnants, each filed separately:** `the-remaining-ue1-texture-layouts` (the unsampled linear slots
and `BC4` upward, which produce `unverified-format` today);
`bc2-bc3-graded-alpha-is-flattened-to-a-binary`; `no-production-consumer-resolves-mesh-skins-yet`;
`bmasked-with-no-reachable-class-default-source`; and an `[OWNER — confirm]` item proposing the
`direction/asset-catalog.md` wording for the limit above.

**One question in `questions/` is still open** — two design calls made on the owner's behalf, both
shipped as proposed and both cheaply reversible.

**Unblocked:** slice `S8a` of board item `unified-asset-catalog`.

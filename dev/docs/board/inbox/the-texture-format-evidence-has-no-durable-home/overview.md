+++
priority = "p1"
kind = "chore"
summary = "The texture-format evidence has NO durable home and will die with an ephemeral spec"
+++

# The texture-format evidence has NO durable home and will die with an ephemeral spec

`spikes/2026-07-25-native-texture-formats/` contains only `pkgfixture_proto.py` and no
write-up. The measured facts — the three dumped `ETextureFormat` enums and where they disagree,
the 18,176-export sweep, the 8,327 ambiguous chains, the 11 stored `Format` properties,
`CompMips` as the true trailing-bytes cause — live **only** in
board item `three-design-calls-the-native-texture-formats`, which is ephemeral and gets deleted when the work
lands. Nothing under `unrealed/` mentions `TEXF`/`ETextureFormat`/`CompMips`/`DXT1`. Land them in
`unrealed/package-format.md` (or a new `unrealed/texture-format.md`) BEFORE that spec is deleted.
`rules/spikes.md`: pin the finding, or it rots. *(Surfaced by the packages + asset-catalog
drafters, 2026-07-26.)*

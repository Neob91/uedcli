+++
priority = "p1"
kind = "owner-question"
summary = "One word in the texture-arbitration decision decides whether ~46 % of every texture corpus decodes — please confirm the reading I recorded"
+++

# One word in the texture-arbitration decision decides whether ~46 % of every texture corpus decodes — please confirm the reading I recorded

Andrzej's AD1 (2026-07-25) says
*"data fits several → a **stored** `Format` code breaks the tie; data fits several and no stored
code → named error (never guess)"*. Read strictly — "stored" = the property is physically present
in the export's tagged-property list — that second clause would turn **8,324** ambiguous chains
into errors, because a `Format` property is stored on only **11 of 18,176** texture exports across
the four corpora here. Concretely that is **1,137 of `uned/UED22`'s 1,998** textures, **1,362 of
Deus Ex `System`+`Textures`'s 5,018**, and **5,826 of Unreal Gold's 10,742** — all of them ordinary
P8 textures that decode correctly today and would stop, and the native preview would checkerboard a
quarter of Deus Ex. **What I recorded instead:** an absent property is *not* an absent code — by
UE1's serialization rule (a property is written only when it differs from the class default, and
`Engine.Texture` declares no `Format`) an absent property IS the byte 0, which is `TEXF_P8` in all
three enums measured, so it breaks ties exactly as a written 0 would. Under that reading the only
files that stop decoding are the ones AD2 names (a code-less BC2/BC3), which matches AD2's framing
of *the* limit. The strict reading is a one-line change in the detection function plus its tests if
you meant it. `decisions.md` 2026-07-25 17:45 UTC records both the reading and this flag; spec §0b
/ plan §0d are written to the recorded reading. *(Measured 2026-07-25 by sweeping all four
corpora.)*

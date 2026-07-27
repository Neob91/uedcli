+++
priority = "p1"
kind = "owner-question"
summary = "Three design calls the native-texture-formats review round made on Andrzej's behalf — please confirm or overrule"
+++

# Three design calls the native-texture-formats review round made on Andrzej's behalf — please confirm or overrule

All three are recorded in
`spec.md` + its plan, and each is cheaply reversible (one
branch in the detection function plus its test), but none of them was his call and none is in
`decisions.md` yet. The build's S7 is supposed to append them; flagging here so they are not
silently inherited.
1. **A four-slot `{Format code → layout}` map exists after all:** `{0: P8, 3: BC1, 6: BC2,
   7: BC3}`, everything else "recognised but unsampled". His steer was "make it work WITHOUT
   USING ANY SUCH TABLE"; the map is scoped so decoding never *requires* it (data-decisive chains
   decode with it unconsulted; an unknown code over an ambiguous chain is a named error, not a
   guess) and it is justified by all three dumped `ETextureFormat` enums agreeing on those four
   slots. But it IS an assumption about slot semantics, and it is the only one.
2. ~~**A `Format` code that was never stored is treated as WEAKER than one that was.**~~
   **RESOLVED 2026-07-25 by Andrzej — nothing to confirm here any more.** He deleted both the
   `format-disagreement` case and the stored-vs-defaulted axis outright: a code breaks ties and
   vetoes a layout we cannot decode, but never contradicts the data, so a stored 0 and an absent 0
   now behave identically. Recorded in `decisions.md` 2026-07-25 17:45 UTC ("Texture layout
   arbitration is a tiebreak-and-veto"). Item 1 below survives him and is *strengthened*: the
   four-slot map is now also what vetoes (227 slot 8 = `TEXF_BC4` fits `bc8` identically to BC1),
   so it is load-bearing in a second way.
3. **Detection and decodability are reported separately**: a chain that fits `linear4` uniquely
   *detects* successfully (`layout_source: data`) and then *fails to decode* with
   `unverified-format` naming the detected layout — rather than either decoding a guess or
   reporting "unknown".

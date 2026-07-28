# Three native-texture-decode design calls made on your behalf — confirm or overrule

## Context

**These are now SHIPPED, exactly as described below** *(built 2026-07-27)*. They were built as
proposed because the work could not proceed without picking one way; each remains cheaply reversible
— one branch in the detection function plus its test. Confirming costs nothing; overruling costs one
small change. Neither was your call to begin with, which is why it is still here.

The durable write-ups are `dev/docs/unrealed/package-format.md` ("Which pixel layout is it?") for
the format facts and `dev/docs/rationale/texture-decode.md` for the engineering reasoning; the
measurements are in `dev/docs/spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md`.
The item's own spec and plan were ephemeral and are gone.

**1. A four-slot `{Format code → layout}` map exists after all:** `{0: P8, 3: BC1, 6: BC2,
7: BC3}`, everything else "recognised but unsampled". Your steer was "make it work WITHOUT USING ANY
SUCH TABLE". The map is scoped so decoding never *requires* it — a chain the mip sizes settle on
their own decodes with the map unconsulted, and an unknown code over an ambiguous chain is a named
error rather than a guess — and it is justified by all three dumped `ETextureFormat` enums agreeing
on those four slots. But it IS an assumption about slot semantics, and it is the only one. It is
also load-bearing in a second way: the same four slots are what **vetoes** a code we cannot decode
(227's slot 8 is `TEXF_BC4`, whose 8-byte blocks fit the BC1 size rule identically, so without the
veto a BC4 texture would be drawn as BC1 — a confident wrong image).

**2. Detection and decodability are reported separately.** A chain that fits `linear4` uniquely
*detects* successfully (`layout_source: data`) and then *fails to decode* with the named error
`unverified-format`, which names the detected layout — rather than either decoding a guess or
reporting "unknown". In practice the error now reads *"detected linear4 (from the data) and there is
no verified decoder for it (16x16, 4 bytes/px)"* instead of *"unknown"*.

*(A third call — that a `Format` code never stored is treated as weaker than one that was — you
resolved yourself on 2026-07-25: you deleted both the `format-disagreement` case and the
stored-vs-defaulted axis outright, so a stored 0 and an absent 0 now behave identically. Nothing is
open there. It is noted only because it is what strengthened call 1 into the veto above.)*

## Options

Two independent rulings, not a menu. Either can be confirmed as-is, or overruled — overruling
call 1 means the tool refuses every ambiguous chain and every BC2/BC3 file instead of resolving it
by the code, which would leave roughly half the corpus undecodable; overruling call 2 means a
`linear4` chain reports "unknown" rather than naming what it is.

## Recommendation

Confirm both. Call 1 is the narrowest form of the assumption that makes the feature work at all, and
its scope is written down and pinned by a test; call 2 costs nothing and makes the error message
say what the file actually is.

## Answer

<!-- Empty = open. Write the decision here. -->

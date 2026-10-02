+++
priority = "p2"
kind = "debug"
summary = "GetVisibleSurfs self-occlusion regresses missed pairs 7->1110, kept disabled"
+++

# GetVisibleSurfs self-occlusion regresses missed pairs 7->1110, kept disabled

Resolved `9c148d4`: root cause was `SpanBuf` being a boolean pixel grid where the real
`FSpanBuffer` (disassembly-decoded, `render.dll 0x1001dd10`/`0x1001df70`) is a per-row sorted
interval list. Rewritten to match; `SUBTRACT_OCCLUSION` shipped ON. UNATCO: byte-identical
2518→2628/3345. Wanchai: roughly flat (3229→3228/4530), errors shift extra→missed, plausibly
`merge_into`'s fidelity to the still-undecoded `MergeWith` (`0x1001e3b0`).

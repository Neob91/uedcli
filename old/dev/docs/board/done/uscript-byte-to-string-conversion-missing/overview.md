+++
priority = "p2"
kind = "implement"
summary = "uscript: byte -> string conversion (string(SomeByteVar)) not lowered"
+++

# uscript byte -> string conversion missing

FIXED: `("byte", "string")` = `0x52`, live-probed against UED22 UCC (one free slot before
`int->string` 0x53). Added to `lower.py`'s `_CONV`; regression `test_uscript_bytetostring.py`.
Re-attempting `IpServer` with the fix hits a new, separate gap —
`dev/docs/board/inbox/uscript-static-through-instance-member-call-p/`.

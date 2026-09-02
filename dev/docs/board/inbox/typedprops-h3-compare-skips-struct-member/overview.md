+++
priority = "p2"
kind = "debug"
summary = "typedprops H3 compare skips struct-member static arrays — name-vs-ordinal false mismatch"
+++

# typedprops H3 compare skips struct-member static arrays

`typedprops.py:339-373` (`_struct_value`) / `classdefaults.py:195-214` (`_struct_field`). A struct
member that is itself a static array gets one `Field` keyed by the bare member name, with no
`array_dim` encoding. But T3D spells an indexed member-array element as `Marks(0)=…`. In the
known-layout loop the lookup `name in parsed` (bare name) never matches the indexed key `marks(0)`,
so the member falls to `zero_value`; a second pass re-admits the indexed key as UNTYPED raw text,
bypassing the member's declared enum/int `Field`.

Effect: for a struct-member array of an enum type, `Axes(0)=SHEER_ZX` (name) and `Axes(0)=5`
(ordinal) — the exact spelling the typed compare exists to normalize — compare as DIFFERENT. Can
abort `level materialize` post-verify with a false PROPERTY mismatch, or (if spellings coincide) let
a real diff pass as a false match.

Credible but not verified against a concrete currently-reachable class; consistent with the indexed
member-array handling in `structtext.py` / `uprops.values._decode_struct_bin_at`. Needs a concrete
class with a struct-member enum static array to pin.

Fix: encode member `array_dim` in `_struct_field` and match indexed keys in `_struct_value` through
the typed `Field`. Regression test.

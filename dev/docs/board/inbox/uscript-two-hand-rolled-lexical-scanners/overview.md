+++
priority = "p4"
kind = "simplify"
summary = "uscript: two hand-rolled lexical scanners duplicate real lexer rules"
+++

# uscript: two hand-rolled lexical scanners duplicate real lexer rules

`compile.py` has two independent hand-rolled scanners that each re-derive comment/string/name-literal
skipping rules already implemented correctly in `lexer.py`'s `_Lexer` (`_skip_line_comment`/
`_skip_block_comment`/`_scan_string`/`_scan_name`): `_skip_defaultproperties_block` (finds the end of
a `defaultproperties {...}` block) and `_mask_lexical_noise` (blanks comments/strings for
`_function_positions`'s regex scan). Both are now correct (verified against live UCC, each pinned by
regression tests) but a future fix to the real lexer's rules (an escape-handling edge case, say) would
need to be replicated by hand in up to three places instead of one.

Not fixed here — `lexer.py`'s `_Lexer` produces a `Token` stream with line/col, not absolute source
offsets, so reusing it directly needs either adding offset tracking to `Token` or converting line/col
back to an index; a real but non-trivial refactor, not a quick fix. Worth doing if a fourth scanner is
ever needed, or if the real lexer's rules change and the duplication becomes a proven cost.

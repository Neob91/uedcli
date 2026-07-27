+++
priority = "p3"
kind = "chore"
summary = "`test_zoom_does_not_highlight` does not test its own claim"
+++

# `test_zoom_does_not_highlight` does not test its own claim

`uedcli/tests/test_actor_preview.py` — the comment says "a zoom target is NOT bolded/highlighted",
but the assertion (`_CSG_PALETTE["subtract"][0] in _colors(...)`) only proves the brush drew in its
normal CSG hue, which holds with or without highlighting. Pre-existing; #10.1 only swapped its
pixel reader from PPM-header parsing to a Pillow decode. A real test would compare against a
`--highlight`ed render and assert the vivid/bold run is ABSENT.

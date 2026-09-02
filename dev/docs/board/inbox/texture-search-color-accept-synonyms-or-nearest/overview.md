+++
priority = "p3"
kind = "implement"
summary = "texture search --color rejects common color words outside its closed 12-word vocab (teal, cyan); accept synonyms or nearest-match."
+++

# texture search --color accept synonyms or nearest-match

Source: `dev/docs/spikes/levelbuild-friction/` finding §5. `texture search --color` takes a closed
12-word palette and rejects near-synonyms an agent naturally reaches for (`teal`, `cyan`), so a
reasonable query fails outright.

Change: map common color synonyms onto the palette, or resolve to the nearest palette entry, rather than
rejecting. Keep the canonical palette as the stored/output form.

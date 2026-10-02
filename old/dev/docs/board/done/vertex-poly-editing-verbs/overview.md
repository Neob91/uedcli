+++
priority = "p?"
kind = "implement"
summary = "Vertex / poly editing verbs (text surface)"
+++

# Vertex / poly editing verbs (text surface)

VERTEX MOVE + surface
texture/flags/pan editing (`poly set`) are DONE (`vertex.py`, `surface.py`, offline-tested).
Surfaces addressed model-side by `(brush Name, poly index)`, with `poly list` + the
numbered-wireframe `preview` for picking; flags addressed by NAME, never raw bit values.
**Deferred remnant:** `poly scale | rotate` (surface edits, same model-side pattern); live
verification of vertex move on the editor (offline-only so far).

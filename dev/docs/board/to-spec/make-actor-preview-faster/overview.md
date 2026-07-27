+++
priority = "p3"
kind = "implement"
summary = "Make `actor preview` faster"
+++

# Make `actor preview` faster

The offline wireframe renderer is a pure-Python
stdlib rasterizer (`preview.py` — `render_brushes_pgm`/`render_quad_pgm`, per-pixel/per-poly loops);
it's the model-side build-loop viewer, so its latency is felt on every iterate-and-look cycle. Spec
should **profile first** (which stage dominates — poly rasterization, text/label drawing, PPM/PNG
encode, `--size` scaling — the default `--size` was just bumped 512→1024, which quadruples fill), then
pick the lever(s): vectorize hot loops (NumPy is not a current dep — decide), cache/skip offscreen
polys, cheaper text, faster encode, or a resolution/quality knob. Set a target (e.g. a quad of a
~20-brush selection under Xms). Keep output byte-comparable where tests pin it. (Andrzej, 2026-07-24.)

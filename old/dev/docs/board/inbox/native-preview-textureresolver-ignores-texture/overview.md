+++
priority = "p2"
kind = "debug"
summary = "native preview TextureResolver ignores Texture subclasses (WetTexture/FireTexture render as checkerboard)"
+++

# Native preview TextureResolver ignores Texture subclasses

`preview_native.py:270` builds `TextureResolver(search_files)` with **no `class_index`**, so it
resolves only the exact `Engine.Texture` class and misses every `Texture` **subclass**
(`WetTexture`, `FireTexture`, `ScriptedTexture`, `WaveTexture`). Those faces render as the
unresolvable-ref magenta/black checkerboard even though the texture is present.

Observed: the `--native` NYC Bar render checkerboarded `Effects.water.drtywater_a` (a `WetTexture`,
60 brushes) and warned `unknown-texture`. The object is really in `Effects.utx`; the resolver just
can't see a subclass without a class index.

Same class-blindness root as `level-preview-game-fails-qualify-level-textures` (a regex there, a
missing `class_index` here). Fix: thread a `ClassIndex` into the native-preview `TextureResolver`
(preview already resolves a mover index, so a class index is available), or teach the resolver to
accept `Texture`-descendant classes. Surfaced by that item's spike (2026-08-24).

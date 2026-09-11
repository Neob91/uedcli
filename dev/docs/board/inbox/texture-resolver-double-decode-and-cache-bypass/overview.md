+++
priority = "p3"
kind = "unknown"
summary = "texture resolver double-decode and cache-bypass inefficiencies"
+++

# texture resolver double-decode and cache-bypass inefficiencies

Surfaced by a `code-review high` pass run against the lighting-in-photo branch (which had merged
master's texture-caching work in) — not lighting-related; logging instead of fixing there.

- **`uedcli/cli/commands/texture.py`'s `_ref_facts` (line 41) calls both `resolver.dimensions(ref)`
  and, for every non-procedural ref, `resolver.resolve(ref)`** — they maintain separate caches and
  each independently parses the full tagged-property list and mip byte arrays via
  `decode_texture()`, doubling parse cost. Bulk enumeration paths (`texture list --json`/
  `--classified`/`--masked`) now pay to parse every ordinary texture's body twice.
- **`uedcli/utexture.py`'s `TextureResolver._source_of` (line 1151) decodes via
  `self._decode_export()` directly instead of `self.resolve()`, bypassing `resolve()`'s cache** —
  a deliberate tradeoff per its own docstring (avoids a name-collision correctness bug on
  re-addressing by name), but real cost when several procedural textures (WetTexture/IceTexture)
  in one package share one source: each `_paint_procedural -> _source_of` call fully re-decodes it.

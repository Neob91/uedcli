# Texture

The `texture` verbs carry the same family as `class` — `list`, `show`, `preview`, `search`,
`classify`, `prewarm` — over every texture on the composed package path (`Engine.Texture` and its
descendants: `FireTexture`, sprites, and the rest). The tool enumerates, reports the file facts,
produces the picture, and stores the classification it is handed; it never infers meaning — the
one exception is colours, pre-filled from the texture's own pixels. Every verb takes
`--catalog-dir DIR` (default: the resolved project's catalog dir — the `uedcli.toml` `catalog`
key, or `<root>/texture-catalog/`).

| Command | What it does |
|---|---|
| [`texture list`](list.md) | enumerate every texture, one ref per line (sorted); filter and shape as needed |
| [`texture show`](show.md) | a texture's facts (size, format, group, masked) + content identity + stored classification |
| [`texture preview`](preview.md) | write a texture's mip-0 bitmap as a PNG |
| [`texture search`](search.md) | ranked discovery: textures whose name / stored tags / description match the terms, best first |
| [`texture classify`](classify.md) | record / inspect what a texture IS — one git-tracked shard per content identity |
| [`texture prewarm`](prewarm.md) | decode every texture ahead of an offline session |

See also: [`class`](../class/README.md) (same catalog shape over actor classes),
[Textures & surfaces](../../leveldesign/general/textures-and-surfaces.md) (the level-design craft).

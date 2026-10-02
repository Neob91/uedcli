# texture search

`texture search <term>…` is RANKED discovery over the texture corpus: textures whose name /
stored tags / description match the terms, best first.

```bash
uedcli texture search <term>… [--tag T] [--color C] [--package P] [--group G] [--masked]
                      [--classified | --unclassified] [--json]
```

- **Terms are required** — a term-less `search` **exits 2** pointing at [`texture
  list`](list.md). Ranks by exact `Name` > exact tag > ref substring > tag substring > description
  substring; a texture must match **every** term (AND).
- `--tag T` (repeatable) keeps only textures carrying that exact stored tag.
- `--color C` (repeatable, OR) keeps only textures whose colours include `C` — stored colours for
  a classified texture, else derived live from pixels; see [`texture classify`](classify.md) for
  how colours are pre-filled. `C` must be a palette name.
- `--package`/`--group`/`--masked` restrict the corpus the same way as [`texture
  list`](list.md)'s.
- `--json` emits one JSON object per match (JSONL), best first: `{ref, score, classified, tags,
  description, colors}`.

See also: [`texture list`](list.md), [`texture classify`](classify.md).

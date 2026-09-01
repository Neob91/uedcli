# texture list

`texture list` enumerates every texture on the composed path (`Engine.Texture` and its
descendants — `FireTexture`, sprites, …), one ref per line, sorted.

```bash
uedcli texture list [--package P] [--group G] [--masked]
                    [--classified | --unclassified] [--json]
```

- Filter with `--package` (a bare package stem), `--group G` and `--masked` (see [`texture
  show`](show.md) for what `group`/`masked` mean), `--classified` / `--unclassified` (keep only
  textures whose content identity does / doesn't have a shard).
- `--json` emits one object per texture: `{ref, identity, classified, group, masked, preview}`;
  `preview` is an already-cached thumbnail path or `null` — `list` never renders; only [`texture
  preview`](preview.md) does.
- `--catalog-dir DIR` overrides the default catalog dir (see the [family
  overview](README.md)).

See also: [`texture show`](show.md), [`texture search`](search.md).

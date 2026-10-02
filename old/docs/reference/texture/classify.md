# texture classify

set / unset / status / tags

Records / inspects what a texture IS — one git-tracked shard per content identity (tags +
description + colours). The tool stores it, never infers it (colours are pre-filled from the
pixels as the one exception).

```bash
# record / inspect what a texture IS — one git-tracked shard per content identity
uedcli texture classify set <Package[.Group].Name> --tags metal,wall \
    --description "riveted metal wall panel" [--colors grey] [--force]
uedcli texture classify set -             # read JSONL rows {ref, tags?, description?, colors?} from stdin
uedcli texture classify unset <ref>… | - (--tags[=A,B] | --description | --colors | --all)
uedcli texture classify status [--json]   # how many textures on the path are classified, of the total
uedcli texture classify tags [--json]     # the tag vocabulary in use, with counts
```

- **`set` refuses over an existing classification** (exit 2); `--force` replaces it wholesale (no
  tag union, an omitted description is wiped). The stored `ref` is write-once — the first
  classifier's spelling.
- **Colours are pre-filled** from a fixed palette by descending share, so [`texture
  search`](search.md)'s `--color brown` works on a fresh clone before anything is classified; an
  LLM-supplied `--colors` overrides them.
- The classification shards live under the tracked `catalog` dir (`classified/texture/`).

See also: [`texture list`](list.md), [`texture search`](search.md).

# texture

The `texture` verbs carry the same family as `class` — `list`, `show`, `preview`, `search`,
`classify`, `prewarm` — over every texture on the composed package path (`Engine.Texture` and its
descendants: `FireTexture`, sprites, and the rest). The tool enumerates, reports the file facts,
produces the picture, and stores the classification it is handed; it never infers meaning — the one
exception is colours, pre-filled from the texture's own pixels. Every verb takes `--catalog-dir DIR`
(default: the resolved project's catalog dir — the `uedcli.toml` `catalog` key, or
`<root>/texture-catalog/`).

```bash
# enumerate every texture, one ref per line (sorted); filter and shape as needed
uedcli texture list [--package P] [--group G] [--masked]
                    [--classified | --unclassified] [--json]

# a texture's facts (size, format, group, masked) + content identity + stored classification
uedcli texture show <Package[.Group].Name>… | -  [--json]

# write a texture's mip-0 bitmap as a PNG (native P8/BC1/BC2/BC3 decode, mask NOT applied)
uedcli texture preview <Package[.Group].Name>… | -  [--out FILE] [--skeleton]

# RANKED discovery: textures whose name / stored tags / description match the terms, best first
uedcli texture search <term>… [--tag T] [--color C] [--package P] [--group G] [--masked]
                      [--classified | --unclassified] [--json]

# record / inspect what a texture IS — one git-tracked shard per content identity
uedcli texture classify set <Package[.Group].Name> --tags metal,wall \
    --description "riveted metal wall panel" [--colors grey] [--force]
uedcli texture classify set -             # read JSONL rows {ref, tags?, description?, colors?} from stdin
uedcli texture classify unset <ref>… | - (--tags[=A,B] | --description | --colors | --all)
uedcli texture classify status [--json]   # how many textures on the path are classified, of the total
uedcli texture classify tags [--json]     # the tag vocabulary in use, with counts

# decode every texture ahead of an offline session
uedcli texture prewarm [--package P]
```

- **Identity is the content, not the ref.** A texture's classification is keyed by
  `sha256(width, height, RGB)` over its mip-0 pixels — so two identically-pixelled textures (even in
  different packages, or one masked and one not) are one classifiable thing, sharing one shard. A
  procedural texture (`FireTexture` and friends) has no pixels, so it is keyed by its casefolded
  `Package.Name` instead. `show` and `list --json` print the identity.
- **`group` and `masked` are per-ref facts**, read live from the package, not part of identity:
  `group` is the texture's Outer (e.g. `Ladder`), `masked` its effective `bMasked` flag. Filter on
  them with `--group`/`--masked`.
- **`set` refuses over an existing classification** (exit 2); `--force` replaces it wholesale (no tag
  union, an omitted description is wiped). The stored `ref` is write-once — the first classifier's
  spelling.
- **Colours are pre-filled** from a fixed palette by descending share, so `search --color brown`
  works on a fresh clone before anything is classified; an LLM-supplied `--colors` overrides them.
- **`preview --skeleton`** emits a ready-to-fill JSONL row per ref (the preview path + pre-filled
  colours) — pipe it straight into `classify set -`. `list` and `search --json` never render; they
  report only an already-cached preview (null until the preview cache lands).

The classification shards live under the tracked `catalog` dir (`classified/texture/`).

See also: [`class`](class/README.md) (same catalog shape over actor classes),
[Textures & surfaces](../leveldesign/general/textures-and-surfaces.md) (the level-design craft).

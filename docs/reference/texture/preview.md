# texture preview

`texture preview <Package[.Group].Name>… | -` writes a texture's mip-0 bitmap as a PNG (native
P8/BC1/BC2/BC3 decode, mask NOT applied).

```bash
uedcli texture preview <Package[.Group].Name>… | -  [--out FILE] [--skeleton]
```

- The bitmap is the opaque Layer-1 image; the mask is **not** applied. Prints
  `<ref><TAB><path>`.
- **`--out PATH`** names the PNG (relative paths join the cwd; the extension is always replaced by
  `.png`); with no `--out` a unique temp file is minted. With several refs the **last** written
  path wins a fixed `--out`.
- **`--skeleton`** emits a ready-to-fill JSONL row per ref `{ref, preview, tags:[], description:'',
  colors:[…]}` (colours pre-filled from the pixels) instead of the `<ref><TAB><path>` line — pipe
  it into `classify set -`. [`texture list`](list.md) and `search --json` never render; they
  report only an already-cached preview (null until the preview cache lands).
- A **procedural** texture — `FireTexture`, `WaveTexture`, `WetTexture`, `IceTexture`, which the
  engine paints every frame and stores no bitmap for — previews as ONE representative static frame,
  drawn from what the package does store (its palette, its saved sparks or drops, the source texture
  a wet/ice one distorts). It is a draft approximation of the effect, not the engine's own pixels,
  and it never animates. A procedural class nothing draws, and any undecodable ref, still **exits 2**
  naming the case.

See also: [`texture list`](list.md), [`texture classify`](classify.md).

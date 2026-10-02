# texture show

`texture show <Package[.Group].Name>… | -` prints a texture's Layer-2 facts (size, format, group,
masked) + its Layer-1 content identity + any stored classification (tags, description, colors).

```bash
uedcli texture show <Package[.Group].Name>… | -  [--json]
```

- **Identity is the content, not the ref.** A texture's classification is keyed by
  `sha256(width, height, RGB)` over its mip-0 pixels — so two identically-pixelled textures (even
  in different packages, or one masked and one not) are one classifiable thing, sharing one shard.
  A procedural texture (`FireTexture` and friends) has no pixels, so it is keyed by its casefolded
  `Package.Name` instead. `show` and `list --json` print the identity.
- **`group` and `masked` are per-ref facts**, read live from the package, not part of identity:
  `group` is the texture's Outer (e.g. `Ladder`), `masked` its effective `bMasked` flag. Filter on
  them with [`texture list`](list.md)'s or [`texture search`](search.md)'s `--group`/`--masked`.
- `--json` prints one JSON object per ref `{ref, width, height, format, group, masked, identity,
  colors, classification}` instead of the text block.
- A procedural texture shows no bitmap size; a bad/undecodable ref **exits 2** naming the case.

See also: [`texture list`](list.md), [`texture classify`](classify.md).

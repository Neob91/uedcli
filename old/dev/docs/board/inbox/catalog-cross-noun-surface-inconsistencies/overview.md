+++
priority = "p3"
kind = "chore"
summary = "catalog cross-noun surface inconsistencies (untracked polish set)"
+++

# catalog cross-noun surface inconsistencies (untracked polish set)

Found by a usability sweep driving all four catalog nouns (texture/class/sound/music) from
`--help` only. The big divergences are already filed separately (re-classify semantics
`align-class-classify-set-to-refuse`; `class show`/`preview` no stdin
`class-show-multi-ref-stdin-reads-a-ref-set`, `class-arm-c2-remainder-angles-multi-ref-stdin`;
prewarm no-op `texture-prewarm-force-is-a-no-op-today`; 60s search
`texture-search-derives-colours-for-the-whole`; colour vocab
`texture-search-color-accept-synonyms-or-nearest`). This item collects the smaller,
untracked surface nits so the shared verb family reads as one tool.

Output-hygiene bugs (concrete):
- **Re-set refusal leaks a Python dict repr.** `sound/texture/music classify set` on an
  existing shard prints `... Stored: {'kind': 'sound', 'ref': ..., 'tags': [...]}` — internal
  structure, single-quoted, inconsistent with the clean human blocks `show` prints.
- **`texture preview` temp PNG is named `/tmp/uedcli-class-preview-*.png`** — the `class`
  prefix on a texture path, a copy-paste leak. Both default and `--skeleton` do it.

Surface divergences (consistency):
- **`--json` field sets differ per noun for the same verb.** `class list --json` omits
  `identity`/`group` that texture/sound/music include; `show --json` shapes differ (expected
  for class facts, but list/search could align). A script reading `.identity`/`.group` breaks
  moving between nouns.
- **`list` count-to-stderr asymmetry.** `sound`/`music list` print `N sounds` to stderr;
  `texture`/`class list` print nothing. (`search` is consistent — all print `N matches`.)
- **Empty filtered `list` is silent.** `texture list --group Ladder` with no hits prints
  nothing, no "0 matches" — indistinguishable from a misfire; `search` says "no matches".
- **`--catalog-dir` exists only on `texture`.** class/sound/music can't point classify at an
  out-of-project shard dir.
- **`show` text block casing/indent differs:** texture prints un-indented `Classification:`;
  sound/music print indented lowercase `  classification:`.
- **"0 musics" / "6 sounds" pluralization** reads awkwardly for a mass noun.

Clarity (not a bug, but confusing):
- **`texture list` reports 1906 but `classify status` denominator is 1879.** Likely
  identity-dedup / procedural exclusion; the two denominators should be reconciled or the
  gap explained so classification-coverage tracking makes sense.

No `classify get`/inspect-one member exists on any noun — you write with `classify set` but
read back only via `show`. Minor, but the set/unset/status/tags family has no single-asset
inspect verb.

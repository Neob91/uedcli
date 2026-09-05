+++
priority = "p2"
kind = "docs"
summary = "align flag rename left dev-docs refs stale needing owner yes"
+++

# align flag rename left dev-docs refs stale needing owner yes

The `per-surface-texture-verbs` steps 2-4 renamed `brush poly align --wall|--floor|--ring` to
`align wall|floor|run`, deleted `--fresh-frame`, and made `wall`/`floor` reproduce the editor's
projection family. The owner approved fixing two dev docs (`rationale/polyalign.md` created;
`unrealed/leveldesign/kb/textures.md` renamed). These further dev-docs refs went stale with the same
change but were outside that approval — each needs the owner's yes before editing (CLAUDE.md
"when a doc looks stale, ask"):

- `dev/docs/unrealed/texalign.md` ~L176, the "How uedcli differs" section — says uedcli aligns with
  `--wall|--floor` + `--fresh-frame` on the seed centroid and is "not any of the editor's rules". As
  of step 3 `wall`/`floor` REPRODUCE `WALLX`/`WALLY`/`FLOOR`, so this section is now wrong and should
  be rewritten (the measured `POLY TEXALIGN` facts above it are unchanged and correct).
- `dev/docs/architecture.md` ~L1817, ~L1861 — two `brush poly align --ring` references → `align run`.
- `dev/docs/unrealed/t3d.md` ~L485 — an example `brush poly align --floor -` → `align floor -`.

All are mechanical except `texalign.md`, which needs a real rewrite of one section. Proposed as a
follow-up so the shipped rename does not leave the dev tree describing deleted flags.

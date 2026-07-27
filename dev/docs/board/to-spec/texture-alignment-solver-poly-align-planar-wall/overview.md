+++
priority = "p2"
kind = "implement"
summary = "Texture-alignment solver (`poly align`) — planar wall/floor + curved (cylinder/sphere) alignment"
+++

# Texture-alignment solver (`poly align`) — planar wall/floor + curved (cylinder/sphere) alignment

⚠ *"Reproduce UnrealEd's TEXTURE ALIGN semantics" (as this item
used to read) is no longer a usable goal: there IS no `TEXTURE ALIGN` verb — the editor's is
`POLY TEXALIGN`, its nine modes were measured 2026-07-26 (`dev/docs/unrealed/texalign.md`), none of them
changes texel density, `ONETILE` is a no-op, and uedcli's `--wall`/`--floor` match none of them.
What to do about that is the `[OWNER — decide]` item on `inbox.md`.* The rest of this item stands:
make
pan/rotation/texture-vectors continuous across adjacent coplanar/wrapped faces (`--wall`/`--floor`)
so brickwork doesn't seam at every brush boundary — pure offline math on the PolyList texture
vectors, currently impossible via uedcli (per-face `poly set --pan` only). ALSO wanted (Andrzej
2026-07-16): alignment onto **curved surfaces** — wrap a texture continuously around e.g. a
cylinder's facet ring or a sphere (per-face U advance matching arc length), so curved builder
output doesn't seam at every facet. (AI brainstorm 2026-07-16; endorsed + extended by Andrzej
2026-07-16.) ALSO fold in `texture scale` / `texture rotate` (2 of the 4 canonical surface ops, flagged missing by the 2026-07-19 usability probe) — same per-face texture-vector math.

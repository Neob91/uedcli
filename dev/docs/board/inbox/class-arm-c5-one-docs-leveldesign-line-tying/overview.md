+++
priority = "p2"
kind = "owner-question"
summary = "class arm C5: one docs/leveldesign line tying signed extents + faces: to mounting (§8.3)"
+++

# class arm C5: the one owner-gated docs/leveldesign line (§8.3)

The class arm (C1–C4) is built and merged. Its usage.md docs are current. The only remaining piece is
§8.3's proposed **`docs/leveldesign/general/` craft line** — new level-design knowledge, which needs
your yes (`CLAUDE.md` "Documentation"). You declined the analogous actor-preview-faces leveldesign line;
this is the class-arm one, so it's a separate call.

Proposed (one line), under a mounting/placement heading in `docs/leveldesign/general/`:

> - **A decoration's mount is read from its mesh's signed local extents, not its collision cylinder:**
>   the thinnest extent axis is the face that sits against the surface, and the asymmetry locates the
>   origin relative to it — so a wall lamp with extents `x -4..4 y -32..32 z -48..16` mounts on its
>   thin (x) face. Record it once per class with `class classify set <ref> --tags mount:wall,faces:+x`.

Caveats already baked into the arm (so the line stays honest): world-facing is **UNVERIFIED** pending
the RotOrigin probe — the settled half is seating/footprint. So if you want the line, I'd drop or hedge
the "faces:+x mounts on the thin face" facing claim until that probe runs.

Do NOT assert "measured on three shipped levels" — no before/after exists yet.

## Answer

<!-- owner: yes (as-is / hedged) / none needed -->

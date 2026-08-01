# The arm's value framing, and whether a `docs/leveldesign` craft line lands now?

## Context

Spec §6, §8.3. Two parts.

- **Framing (in the spec, owner to confirm the wording):** state the arm's headline value as "props
  stop sinking into floors, floating off walls, and facing the wrong way" — the three defects in owner
  finding 7. Honest limits already in §6: the *seating* half is closed by the signed extents outright;
  *floating* and *mis-facing* are addressed only by the posed preview an agent looks at (the
  extents-based `faces:` signal stays UNVERIFIED pending the `RotOrigin` probe — Q `facing-scope-call`);
  and this fixes the *facts* half only, not whether a button belongs on *that* wall (intent).
- **Craft line (needs an explicit yes to land):** add one short line to `docs/leveldesign/general/`
  tying the thin extent axis + `faces:` to mounting.

- **At stake / direction default:** `CLAUDE.md` "Documentation" requires the owner's approval before new
  level-design knowledge lands in `docs/leveldesign/` — inaccurate craft knowledge is costly and hard to
  catch. So the craft line cannot ship on an agent's read. The "measured on three shipped levels" claim
  from the source item must **not** be stated until a real before/after exists.

**Recommendation:** keep the value framing in the spec now; land the `docs/leveldesign` craft line only
on owner yes and only once the facing signal is verified; do not assert the "three levels" measurement
until evidence exists.

## Answer

<!-- Empty = open. -->

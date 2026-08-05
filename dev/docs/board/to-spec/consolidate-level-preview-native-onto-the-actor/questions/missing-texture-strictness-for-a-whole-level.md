# Whole-level exit-2-on-missing-texture, or a laxer draft rule?

The two paths handle an unresolvable/undecodable texture ref OPPOSITELY, and consolidation forces a
choice for the offline whole-level tier:

- `level preview --native` today draws a **magenta/black checkerboard** and prints one stderr warning
  per distinct ref, then exits 0 (`preview_native._TextureTable` / `_checkerboard`). Board item
  `level-preview-native-checkerboards` flags this as a `conventions.md`-Rejected warn-and-continue.
- `actor preview --faces textured` **exits 2** naming the ref — the house rule (a needed-but-
  unreadable texture is a refusal, never a placeholder).

Adopting `actor preview`'s logic means the offline whole-level tier **exits 2 if ANY surviving
surface in the whole level references a texture that does not decode.** A retail map references many
packages; the odds that *every* surviving surface's texture decodes are lower for a whole level than
for a hand-picked actor set. So strict exit-2 could make the offline level preview refuse often.

Options:
- **Strict (adopt actor preview as-is):** exit 2 naming the first/all missing refs. Consistent, no
  half-answer. Risk: frequent refusal on real levels; also closes `level-preview-native-checkerboards`
  by making the two consistent.
- **Batch-report then refuse:** collect ALL missing refs across the level and exit 2 once, naming the
  set (the `conventions.md` batch rule). Same refusal, better message.
- **A `level preview`-only draft rule:** the whole-level draft tier is explicitly a draft, so a
  missing texture renders a flat sentinel and the *set of missing refs* is reported to stderr AND the
  command still exits 2 at the end (no silent 0). Needs owner sign-off because it reintroduces a
  placeholder the `--faces textured` spec deliberately rejected.

## Answer

<!-- Empty = open. -->

+++
priority = "p?"
kind = "implement"
summary = "level doctor: flag a subtract carving empty space, and an add fully inside another add — both no-op brushes."
+++

# Rework level doctor to flag no-op CSG brushes

Owner's first two ideas for a `level doctor` rework, both intent-independent no-ops (fits the
`level-doctor-s-scope-boundary` bound — neither has a legitimate reading, regardless of author intent):

1. **A subtractive brush subtracting from empty space** — carves nothing, makes no sense.
   `check_csg_order` (`doctor.py:434`) already flags a subtract with **no AABB overlap at all**
   (INFO, `csg_order`, "carves nothing"), but not a subtract that overlaps only already-empty space
   (e.g. entirely inside a prior subtract's cut, or never covered by any add) — that case ships clean
   today.
2. **An additive brush fully inside another additive brush** — contributes nothing to the CSG result.
   `check_csg_order` currently only catches add-inside-*subtract* (erased by the later subtract); the
   add-inside-add case (redundant, no effect either way) isn't checked.

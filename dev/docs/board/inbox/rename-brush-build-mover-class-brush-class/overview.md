+++
priority = "p2"
kind = "unknown"
summary = "Rename `brush build --mover-class` → `--brush-class`, and enforce the class descends from `Engine.Brush` (inclusive) (2026-07-24)"
+++

# Rename `brush build --mover-class` → `--brush-class`, and enforce the class descends from `Engine.Brush` (inclusive) (2026-07-24)

The flag currently names a Mover class (`brush build
--mover-class <Package.Name>`, direction.md "Generator pattern"), but the general shape is "which brush
actor class to emit" — a Mover subclass is just one case, and the value must be `Engine.Brush` itself or
any descendant. Rename to `--brush-class` and VALIDATE at parse time via the class hierarchy
(`ClassIndex.descends_from(cls, "Engine.Brush")`, inclusive — accept `Engine.Brush` and every subclass);
reject a non-Brush class with a clear exit-2 error naming the offending value, never a traceback. Update
`docs/usage.md` + `direction.md`'s generator-pattern note. Andrzej flagged.

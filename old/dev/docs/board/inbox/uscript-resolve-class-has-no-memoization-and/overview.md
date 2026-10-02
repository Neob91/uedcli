+++
priority = "p2"
kind = "implement"
summary = "uscript resolve_class has no memoization and walks each class body 3x"
+++

# uscript resolve_class has no memoization and walks each class body 3x

`InstallEnv.resolve_class` (`uedcli/uscript/env.py:139-153`) does a linear `_class_export_index` scan
(31-37) plus three separate from-scratch decodes of the same UClass body: `_self_crc` (40-58),
`_class_flags` (61-71), `_package_imports` (74-92) each independently redo the identical
Super/Next/ScriptText/.../Dependencies skip. Called repeatedly for the same class name at 8 call
sites in `compile.py` (lines 269, 576, 695, 723, 806, 998, 1750, 1773), including inside per-var/
per-type resolution loops — a class with many `var Actor` fields re-walks Engine.u's `Actor` body
from scratch per field.

`natives.py`'s `ClassGraph` already solves this correctly for the adjacent lowering path (memoizes
`class_sig`/`struct_member_type`) — use it as the reference shape for the fix here.

Fix: cache `ClassInfo` by casefolded class name in `InstallEnv` for the lifetime of one compile, and
merge the three redundant walks into one pass.

Found by: 2026-09-12 performance audit (subagent-driven, uscript-compiler scope).

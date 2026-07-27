+++
priority = "p2"
kind = "implement"
summary = "`level delete` / `rename` / `clone` — git-agnostic trunk-dir lifecycle verbs"
+++

# `level delete` / `rename` / `clone` — git-agnostic trunk-dir lifecycle verbs

The probe found no way to delete, rename, or copy a level. Spec thin verbs operating on the TRUNK DIRECTORY directly (filesystem — git-agnostic, per `direction.md`'s "uedcli never wraps version control"), NOT git wrappers: `rename` = move `<maps>/<old>` → `<new>` (+ name/rank fixups + retarget the selected pointer if it pointed there); `clone` = copy the trunk under a new name; `delete` = rm the trunk dir behind a guard (refuse if selected, or `--force`). Works whether or not the project is under git. (Surfaced 2026-07-19 usability probe; git-agnostic per Andrzej.)

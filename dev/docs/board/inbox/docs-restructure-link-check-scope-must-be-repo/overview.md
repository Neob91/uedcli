+++
priority = "p1"
kind = "chore"
summary = "Docs restructure: link-check scope must be repo-wide, not `dev/docs`+`docs`"
+++

# Docs restructure: link-check scope must be repo-wide, not `dev/docs`+`docs`

~49 citations of `decisions.md` and 5 of `direction.md` live in `uedcli/*.py`, `bin/_venv.sh`,
`pyproject.toml`; `CLAUDE.md` "New UnrealEd findings … back-reference them from code comments"
makes these load-bearing. Also: the dominant citation form is *prose* (``CLAUDE.md` "Review
gates"``), which a link checker passes — needs a string-based check too. And `bin/test` must run,
so the batch is a **build** row, not docs-only.

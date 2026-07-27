+++
priority = "p2"
kind = "chore"
summary = "Docs restructure: `rules/` must be added to the NOT-trivial list, and router lines must never be `@` imports"
+++

# Docs restructure: `rules/` must be added to the NOT-trivial list, and router lines must never be `@` imports

After Part A ~550 of `CLAUDE.md`'s lines live in
`dev/docs/rules/*.md`, which is not on the NOT-trivial list — a one-line edit there would be
gateable as trivial, an observable weakening. Separately, one `@dev/docs/rules/…` row silently
negates the entire saving while looking correct; gate on `grep -n '@dev/docs/' CLAUDE.md` empty.

+++
priority = "p3"
kind = "docs"
summary = "CLAUDE.md points at a repo-root TODO.md that has never existed"
+++

# CLAUDE.md points at a repo-root TODO.md that has never existed

`CLAUDE.md` "The repo this tool lives in" states, in the present tense, that **`TODO.md` (repo
root) holds repo-level, cross-cutting items**, and "After every change" then tells an agent to
"cross off the TODOs it completed".

There is no such file, and there never has been:

```
$ ls TODO.md
ls: cannot access 'TODO.md': No such file or directory
$ git log --all -- TODO.md      # empty — never tracked on any branch
```

It is not gitignored either. So an agent following the rule goes looking for a file that does
not exist, and the always-loaded rule file makes a false present-tense claim in the most
privileged position available.

**Pre-existing** — the claim predates the 2026-07-27 de-bloat restructure of `CLAUDE.md`, which
only reworded the bullet. **Logged rather than fixed** because both candidate fixes change a
rule rather than compress one, which was out of scope for that pass:

- **Delete the bullet** and let the board be the sole backlog — this removes the "repo-level,
  cross-cutting items" lane entirely, and something has to say where a cross-cutting item goes
  instead.
- **Keep the lane** and say the file is created on first use.

Which one is right is a call about how the backlog is organised, so it likely needs the owner
(see `CLAUDE.md` "Asking the owner"). Surfaced by the build/docs review round on that
restructure.

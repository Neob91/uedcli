# `level delete` — what guards it against destroying authored work?

## Context

A level trunk is authored work `safety.md` protects; but git is the only recovery route and uedcli
keeps no backups. `level delete` removes `maps/NAME/` from the filesystem.

Options:
- (a) **Always require `--force`** — uniform, git-agnostic, matches `safety.md`'s refuse-and-instruct.
- (b) Refuse only when the trunk has uncommitted git changes — couples the verb to git, which the
  item explicitly rejects.
- (c) Delete freely — git is recovery. Loses uncommitted work with no speed bump.

Recommend (a): one flag, no git coupling, and the message can name the git-recovery caveat.

## Answer

<!-- Empty = open. -->

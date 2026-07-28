# Config discovery and validation — why `config.py` behaves this way

Engineering decisions about `uedcli/config.py`: how a project is found from the cwd, and how the
two colon-separated directory lists (a project's `paths`, a `[games.<name>]` block's `paths`) are
validated. The user-facing shape of these files is `docs/usage.md`; the product intent is
[`../direction/projects-and-config.md`](../direction/projects-and-config.md).

## An unreadable project marker stops the walk-up, never skipped

To find the project a command operates on, uedcli walks from the current directory upwards and takes
the first ancestor containing a file called `uedcli.toml`. Nearest wins, so a project nested inside
another shadows the outer one — the same rule `git` uses for `.git`.

Any reason a marker cannot be read is a reason not to climb past it. Skipping one means "there may be
a project here and I could not tell", not "no project here". The walk would otherwise keep going and
bind the command to an outer project — no error, a successful-looking mutation of the wrong tree.

The function already applied that rule to a malformed marker (`load_project` raises) and to a
present-but-not-a-regular-file one (a dangling symlink or a directory named `uedcli.toml`). The
`except OSError: continue` around the stat did the opposite for a permission-denied directory; it now
raises a `ConfigError` naming the marker and the OS reason.

Ordinary absence does not reach that branch: `pathlib.Path.is_file()` returns `False` for
`ENOENT`/`ENOTDIR` rather than raising, so a missing marker stays an ordinary skip.

**Rejected:**

- **Skipping an unstatable marker** (the previous behaviour) — silently binds to an outer project.
- **Returning `None` (no project) on the first unreadable ancestor** — indistinguishable from "you
  are not in a project", and the fix a user needs is completely different.
- **A `--force`-style flag to climb past it** — `../direction/conventions.md` refuses flags that opt
  into a wrong answer.

## One shared "Windows-style drive?" check, run before any split

In both config files a directory list is a single string with `:` as the separator. The most likely
way a `:` gets into a value is a pasted Windows path (`C:\DX\System`). Without a dedicated check the
split is silent and the resulting message is about something the user never wrote: `C:\DX\System`
splits into `C` and `\DX\System`, and the first element trips the absoluteness check as `dir must be
absolute: 'C'`.

The dedicated error existed but only in `resolve_dirs`, which runs at COMPOSE time.
`load_user_config` validates the same string at LOAD time and runs first, so the good message was
unreachable for a `[games.*]` path. Both now call the shared `config.reject_windows_drive(paths_str,
where)` on the whole string before splitting.

The regex is anchored to an element boundary (`(?:^|:)[A-Za-z]:[\\/]`) so an ordinary separator
colon in `/a:/b` is not mistaken for a drive letter.

**Rejected:**

- **Copying the message into `load_user_config`** — two copies of one error, and the next reader of
  a dir list would add a third or none.
- **Checking after the split, per element** — the information that identifies the mistake (the
  drive letter followed by a separator) is exactly what the split destroys.
- **Accepting and translating a Windows path** — uedcli's host paths are POSIX; guessing a
  translation is a fallback, which `../direction/conventions.md` forbids.

**Refs:** `uedcli/config.py` (`walk_up_root`, `reject_windows_drive`, `resolve_dirs`,
`load_user_config`) · `uedcli/tests/test_config.py` ·
`../direction/projects-and-config.md`

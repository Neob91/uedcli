# Delete/rename of the level named by `$UEDCLI_LEVEL` — refuse, warn, or ignore?

## Context

There is no persistent "selected level" anymore — the ambient level is the per-process env var
`$UEDCLI_LEVEL`, and a uedcli child process cannot change the parent shell's env
(`level_sources.py:348`, `level.py:124`). So a verb cannot "retarget the pointer" as the overview
imagined; deleting/renaming the exported level just leaves `$UEDCLI_LEVEL` pointing at a
gone/renamed level.

Options:
- **Warn on stderr** (recommend) — e.g. `note: $UEDCLI_LEVEL still names 'X'; re-export it`. Does not
  block the common "delete the level I'm working on" case.
- **Refuse** unless `--force`/re-export — safest but blocks the common case.
- **Ignore** — silent; the next verb fails with the existing "level does not exist" error, which is
  less clear at the moment of surprise.

## Answer

<!-- Empty = open. -->

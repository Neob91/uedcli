# CLI mechanics — why the argument surface is built this way

Engineering decisions about `uedctl/cli.py` and `uedctl/dispatch.py`. The *conventions* these
serve are the owner's and live in [`../direction/conventions.md`](../direction/conventions.md);
this doc is the machinery.

## Deleting a migration shim can silently re-open a prefix-abbreviation hole

**Why it is this way:** `argparse` expands any unambiguous prefix of a **defined** option. A
migration-error shim therefore does a second, unadvertised job — it *occupies* its own name, which
blocks that name from abbreviating into a different surviving flag. Delete the shim and the
abbreviation silently starts resolving somewhere else.

Concretely: while a `--class` shim existed, `--class` was defined (and errored helpfully). Deleting
it — correct under the no-back-compat rule — let `--class` abbreviate into `--class-exact`, so an
invocation that used to fail loudly began silently meaning *exact-match only*.

The fix is to rename the **survivor** (`--class-exact` → `--exact-class`) so the prefix no longer
collides. That closes the hazard structurally. Keeping the shim to hold the name would be trading a
silent bug for permanent maintenance surface, which the no-back-compat rule exists to refuse.

**After deleting any option, check the BUILT PARSER, not the reasoning.** Whether a prefix is
ambiguous depends on the full set of options actually registered on that subparser, which is not
apparent from the diff.

**Rejected:**

- **`allow_abbrev=False` globally** — kills the whole class of hazard in one line, but it is a
  behaviour change across every flag in the CLI and removes abbreviations that work today, to fix
  one collision.
- **Keeping the `--class` shim** so the name stays occupied — a shim retained for a side effect is
  still a shim, and the next person to tidy it up re-opens the hole with no warning.
- **Accepting the new abbreviation** and documenting it — it silently changes what an existing
  invocation means, which is the one outcome the no-back-compat rule is meant to prevent.

**Refs:** `../direction/conventions.md` "No back-compat cruft" · `uedctl/cli.py`

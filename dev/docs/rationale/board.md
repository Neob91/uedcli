# Board — why the per-item shape is built the way it is

The owner's decisions about the board live in `dev/docs/direction/process.md`; this file holds the
engineering choices made underneath them. Shape and rules: `dev/docs/board/README.md`.

## TOML frontmatter, in a pinned subset

The header must be machine-readable, and `tomllib` is in the standard library on the repo's Python
3.12, so the test is a parser call with no new dependency. TOML is already a house format
(`uedcli.toml`, read by `config.py`). It always quotes strings, which matters here: 97 board titles
start with a backtick, 61 contain `: ` and 12 contain ` #`, all of which break an unquoted YAML
scalar.

The subset — single-line basic strings, one array per line, no comments — exists because `bin/board`
reads the same frontmatter in bash, where a full TOML grammar is not worth writing. `test_board.py`
enforces the constraint; `test_board_script.py` runs both readers over every item and requires
identical results.

**Rejected.** *YAML* — there is no YAML parser, `pyproject.toml` names Pillow as the only
third-party dependency, and adding PyYAML for a docs format is a real cost. *A YAML-shaped subset* —
a trap for an author who assumes real YAML. *A `·`-separated single line* — `·` already occurs 48
times in board prose, and a dependency list reads badly inline.

**Refs.** Spec §2.10, §3.4. `bin/board`, `uedcli/tests/test_board_script.py`.

## Slugs — the intent, and what the migration produced

A slug is permanent, unique board-wide and never renamed, so it should be a name, not a hash of a
sentence. The script prefers the part of a title before its first em-dash or parenthesis, strips a
leading `[tag]` and `pN` (168 titles carried one — without stripping, a permanent name bakes in a
priority and a kind the board has abolished), and drops trailing filler.

What shipped is weaker. The bulk migration derived slugs mechanically and truncated at 48
characters, which spec §3.3 rejects. 285 of 492 slugs are ≥40 characters and
`inbox/architecture-md-contradicts-direction` is the literal anti-example §3.3 gives. A handful
whose derived name was wrong (`inbox/done`, `inbox/authoring`, `to-spec/zones`) were repaired by
hand; the rest stand. Renaming is barred once a slug is referenced, so this is a permanent cost of
converting ~490 items by script. Tracked as `board item board-migration-remnants`.

A slug is not reserved forever, because `done/` is pruned to a short tail. Pruning is only legal when
nothing cites the item, which the slug-reference test enforces; otherwise a citation would silently
resolve to a later item that reused the name.

**Rejected.** *Numeric `-2` suffixing on collision* — shortened slugs collide readily (16 colliding
groups over 37 items at three words), and naming one of two different items
`per-surface-texture-verbs-2` is worse than asking the author for a distinguishing name. *Priority
in the directory name* — free sorting, but re-prioritising would rename the directory and break
every reference.

**Refs.** Spec §2.4, §3.3. `_scratch/board-migration/convert.py` (gitignored; the migration is done).

## References are slugs, never paths

An item's path contains its stage, and the stage is the field the design exists to make cheap to
change. 86 files cited a spec or plan by path across 401 lines, 76 of them durable — every one would
break on a `git mv`, and repointing them would touch shared files, destroying the disjoint-paths
property.

The reference form requires backticks around a kebab-case slug. Both constraints are load-bearing:
the bare phrase "board item" appears ~75 times as prose, and two live sites follow it with a
backticked filename rather than a slug. A slug-shaped match excludes both without exempting the
files.

**Rejected.** *Leaving specs and plans in `dev/docs/specs/` and linking them* — nothing breaks, but
the item stops being self-contained and two trees stay alive. *A stage-free item address* — nothing
could break, but `ls to-build/` would stop being the queue and advancing would become a file edit,
reintroducing the write contention.

**Refs.** Spec §2.9, §3.3. `uedcli/tests/test_board.py::test_slug_references_resolve`.

## A question never moves its item

Owner ruling: a question is filed against the item where it is, and the item keeps its stage.
Bouncing it — to the inbox, as the old board did, or back to `to-spec/`, as an earlier revision did
— shelves finished spec or plan work over one open decision. `bin/board questions` finds a blocker
wherever it lives, so the only way one can hide is by sitting in a stage the tool does not scan,
which the test checks.

What keys on the file's absence is the unblocking, not the item's position. Folding the answer into
its durable home and deleting the question file clears the blocker; a non-empty `## Answer` alone
does not, or typing a reply would clear it before any durable doc recorded the decision. So the
check needs no emptiness parsing and cannot be fooled by a malformed file.

A missing `## Answer` section is a failure, not an open question: worded the other way, a malformed
file would satisfy the gate.

**Rejected.** *Gate on a non-empty answer* — see above. *Keep answered files, marked* — item
directories accumulate dead questions and "what is open" becomes a status read.

**Refs.** Spec §2.2, §2.3, §3.5, §3.6.

## `bin/board` is bash and sources no venv

`bin/_venv.sh` hard-fails without `python3.12` on `PATH`, and there is no system `python3` on the
dev machine. Making a read-only board query depend on a Python install is a bad trade for a tool an
agent runs constantly. The cost is the second frontmatter parser, which the agreement test pins.

A malformed item is reported and skipped, not fatal: several sessions share this checkout, so an
item mid-write is normal. Exit 2 is reserved for a request the command cannot satisfy (unknown
stage, unknown slug), naming the value.

**Rejected.** *A `uedcli` verb* — `uedcli` is the level-editing tool for users; the board is
developer process and has no place in the shipped CLI surface.

**Refs.** Spec §3.9. `bin/board`, `uedcli/tests/test_board_script.py`.

## The link-test exemption boundary moved

`_on_deck()` used to read `board/to-build.md` to decide which ephemeral specs and plans were on-deck
and therefore link-checked. It fails open — a missing file returns an empty set and silently
un-checks every ephemeral doc — so it had to be repointed at `board/to-build/*/overview.md` in the
same commit that deleted the file, not later.

**Refs.** Spec §4.1. `uedcli/tests/test_doc_links.py::_on_deck`.

## The migration ran on the base branch, in batches

Owner ruling (spec §2.15): a worktree fails loudly with a modify/delete conflict, while the base
branch fails silently — the commit that removes a board file discards whatever another session
committed meanwhile. The risk was accepted and the reconciliation step declined; batches keep the
window to minutes.

`CLAUDE.md` was repointed off `inbox.md` in its own commit before the inbox batch, because other
sessions read `CLAUDE.md`, not chat, and would otherwise keep appending to a file mid-conversion.

**Refs.** Spec §2.15, §4.2.

# `userdocs.py` — serving the user-facing docs from the CLI

Why the `docs list|show|search` verbs are built the way they are. *What* they do lives in
[`../architecture.md`](../architecture.md) "Commands (namespaced)"; the user-facing reference is
`docs/usage.md`.

Context for a reader with none: uedcli's prose documentation for its **users** lives in the repo's
`docs/` directory (`usage.md` plus the `leveldesign/` guides). The `docs` verbs make that tree
readable through uedcli itself, so a consumer — a person at a terminal, or a shipped Claude skill
routing someone to the right page — reads the docs baked into the binary it has instead of
carrying its own copy that silently drifts out of date. A **topic key** is the name a page is
addressed by (its path with `.md` dropped, a `README.md` folded onto its directory).

> **Some of what follows is the OWNER's decision, not an agent's.** This tree is agent-owned and
> freely revisable, which is the wrong protection for a ruling he made. The product intent (docs
> are an asset of the tool; a shipped skill queries the tool instead of bundling copies) and the
> duplicate-key hard error are his; both are parked as `[OWNER — confirm]` items on
> [`dev/docs/board/inbox/`](../board/inbox/) with the proposed `direction/` wording, pending his yes.
> They are restated below because a reader needs them in place to follow the engineering — but
> **`direction/` is where they will live, and this file must not be treated as their home.**

## `show` resolves through the enumerated served set, never a path join

**Why it is this way:** the obvious implementation — join the user's topic onto the docs root and
read that file — makes correctness depend on a blacklist that has to anticipate `../`, an absolute
path, a symlink, a directory, a non-markdown file and the developer tree. Enumerating the served
set first and then looking the key up in it makes every one of those a plain "not found" by
construction: a file that was never enumerated has no key to hit. The same enumeration feeds
`list`, `search` and `show`, so the three cannot disagree about what is served, and there is no
second code path to keep in step.

**Rejected:** *joining the topic onto the docs root and validating the result* (`resolve()` +
`is_relative_to(root)`) — it works, but it is a check that must be remembered at every call site
rather than a property of the design, and it still needs separate rules for directories, non-`.md`
files and the `dev/` subtree. **Rejected:** *serving a bare basename when it happens to be unique*
— `human-scale` exists twice today, so the rule would resolve or fail depending on which pages
exist, and a page added later would silently change what an existing key means.

**Refs:** `uedcli/userdocs.py` (`load_docs`, `find_doc`), `uedcli/tests/test_docs_command.py`.

## The tree is walked by hand, because `rglob` turns an unreadable directory into an empty one

**Why it is this way:** `pathlib`'s glob swallows the `OSError` that `scandir` raises on a
directory the process cannot read, so it reports "nothing here" for "I could not look". With
`root.rglob("*.md")` an unreadable docs root listed as `0 topics` at **exit 0**, and an unreadable
*subdirectory* was worse still: its pages simply vanished from `list`, `search` and `show`, with a
successful-looking partial answer and no signal anywhere. That is precisely the shape
`../direction/conventions.md` "No silent half-answers" forbids, and it is not hypothetical here —
root-owned directories left behind by container runs are a recurring problem in this repo, which
`dispatch.py` already carries a filesystem-error handler for. `_markdown_files` therefore walks
with `os.scandir` and turns any `OSError` into a clean exit-2 naming the directory. It also prunes
a top-level `dev/` *as it walks* rather than filtering afterwards, so an unreadable developer tree —
which is never served — cannot fail a user's command. (That prune is **defence in depth, not the
thing that excludes the developer docs**: `dev/docs/` is a sibling of `docs/`, so it is outside the
docs root and the prune fires on nothing today. The root is the guarantee.)

Directory symlinks are still not followed, matching what `rglob` did: a link can otherwise walk the
enumeration out of the tree or into a cycle. A symlinked *file* is collected and then vetted
against the resolved root.

**Every comparison in the module is case-insensitive** — the `dev/` prune, the `README` fold, the
`.md` extension, key lookup, the duplicate-key check, and the sort order. A prune that fired on
`dev` but not `DEV` is a real hole on a case-insensitive filesystem, and Windows via Nuitka is a
stated ship target; the rest follow so the served set never changes shape with the platform.

**Rejected:** *`rglob` plus a pre-flight `os.access(root, R_OK)` check* — it covers only the root,
leaves every subdirectory silently droppable, and races the walk. **Rejected:** *reporting the
unreadable directory on stderr and serving what was readable* — the warning scrolls away and the
truncated listing is taken for the whole tree, which is the exact failure mode being fixed.

**Refs:** `uedcli/userdocs.py` (`_markdown_files`, `_in_dev_tree`), `uedcli/tests/test_docs_command.py`.

## The docs root resolves source-tree BEFORE the packaged copy

**Why it is this way:** the order is `$UEDCLI_DOCS_DIR` → `docs/` beside the installed package →
`uedcli/_docs/` inside it. A future wheel/Nuitka build will generate `_docs/` from the source tree;
if that copy won a lookup, a developer who once ran an experimental build would afterwards be
reading a frozen snapshot while editing the live `docs/` tree, with nothing on screen to say so. In
a real install no `docs/` sibling exists, so the packaged copy is what answers there. The package
is located via `importlib.resources.files("uedcli")` rather than counting `.parent`s off
`__file__`, so moving the module inside the package cannot break the resolver.

An unresolvable root — including a `$UEDCLI_DOCS_DIR` pointing at nothing — is a clean exit-2
error naming what was wrong, not an empty listing: an empty served set reads as "this build ships
no docs" when the truth is "your override is wrong". (The spec's illustrative resolver snippet
returned the override unchecked; its own error and testing sections require the clean refusal, and
that is what is built.)

**All THREE shapes of broken root are errors, including the empty one.** Nonexistent, unreadable,
and *present-and-readable-but-holding-no-pages* all exit 2 naming the root. The third was the last
hole in the promise the module makes about itself, and it is the most confusing of the three
untreated: `0 topic(s)` at exit 0 is the same output a genuinely doc-free build would produce, so
the user cannot tell a misconfiguration from a design fact and is never told where the tool looked.
uedcli always ships pages, so zero is never a legitimate answer.

**Rejected:** *softening the docstring instead* (admitting an empty listing is possible) — cheaper,
but it trades a true promise for a caveat, and the caveat is exactly the case a user cannot
diagnose unaided. **Rejected:** *erroring only when the root is the packaged `_docs`* — the
override and source-tree branches are where a wrong root actually comes from.

**Rejected:** *packaged-first, on the grounds that it is the shipping configuration* — it optimizes
for the case that cannot go wrong (an install has only one copy) at the cost of the case that can.
**Rejected:** *a committed index file* of keys and titles — the tree is ~50 files, enumeration is
already imperceptible, and an index is one more artifact that can disagree with the tree.
**Rejected:** *supporting zip-imported / zipapp installs* — uedcli ships filesystem-backed
(pipx, Nuitka), and a `Traversable`-only code path would be untested surface.

## A duplicate topic key is a hard error, not a precedence rule

**This one is the OWNER's ruling, not an engineering call** — parked as an `[OWNER — confirm]`
item on [`dev/docs/board/inbox/`](../board/inbox/) for `direction/conventions.md`. What follows is
the reasoning behind it, kept here so the code is readable; the ruling itself belongs there.

**Why it is this way:** two files can claim one key — `X/README.md` beside a sibling `X.md`, a
`docs/index.md` against the root README's reserved `index`, or two paths differing only in case
(lookup is case-insensitive). Picking one and serving it silently means `docs show X` returns a
page and the reader has no way to tell it was not the other one. Because the failure is raised
during **enumeration** rather than at lookup, it takes down every `docs` invocation and the test
suite the moment such a file is committed — so it is caught while authoring, and a user of a
shipped binary can never encounter it. That is the whole reason the strict choice is affordable
here: the cost lands on the author, not the user.

**Rejected:** *first-wins / README-wins precedence* — a silent wrong answer, and the losing page
becomes unreachable with nothing reporting it. **Rejected:** *warning on stderr and continuing* —
the warning scrolls away and the ambiguous answer is taken for a definite one.

## `show` writes bytes; `show -` is atomic and marks each page

**Why it is this way:** the pages contain UTF-8 typography (`°`, `×`, `≡`, `…`). Printing through
Python's text layer re-encodes them in whatever the terminal locale claims, so a non-UTF-8 locale
would corrupt the output; `sys.stdout.buffer` is a byte-for-byte copy of the file.

`show -` (topic keys from stdin) resolves the whole set before writing anything: if any key is
unknown it prints **nothing** and exits 2 naming the offending keys. A partial dump plus a stderr
warning is exactly the failure the house "no silent half-answers" rule exists to prevent — the
warning scrolls away and the truncated set is taken for the complete answer. On success each page
is preceded by a `<!-- topic: <key> -->` marker line, before the page rather than between pages, so
every marker names the markdown that follows it and a consumer of the concatenated stream is never
guessing. It is a markdown comment, so the stream remains valid markdown.

**Rejected:** *a separator only between pages* — the marker would have to name one of the two pages
it sits between, leaving the first page unlabelled and the association ambiguous. **Rejected:**
*skipping unresolvable keys with a warning* — see above.

## `search` is a literal substring with a fixed 10× title weight

**Why it is this way:** the score is `10 × (query in title) + (number of BODY lines containing the
query)`, ties broken lexicographically by key. A caller pipes the result into `docs show -`, so a
predictable, explainable ranking is worth more than a better-tuned opaque one. No tokenization, no
stemming and no fuzzy distance in v1 — each would need its own tuning and its own tests to earn its
place.

**State the weight, never "a title match wins".** It does not: eleven body mentions outrank a title
match, and on the shipped tree `docs search mover` really does put `usage` (73 body lines, no title
hit) above `leveldesign/general/movers` (title hit, 39 body lines). The user-facing help and
`docs/usage.md` therefore say *a title match is worth ten body lines* — the arithmetic, which is
both true and predictable — rather than promising an ordering the code does not guarantee. A doc
that overstates a ranking rule is worse than one that omits it, because the reader builds a mental
model that quietly fails.

**A page's own heading is its title, so it is not also a body line.** Counting it in both places
inflated a title match to 11 instead of 10 and, more visibly, made the reported snippet the heading
itself — a `--json` row whose `snippet` merely repeated its `title` with a leading `#` is evidence
of nothing. `_split_title` peels the title line off once, so the two can never disagree about which
line it was.

An empty or whitespace-only query is refused by name, because a blank substring is inside every
line of every page and would "match" the entire corpus in score order — a meaningless answer rather
than an empty one. This is not an invented rule: `texture search`, the other ranked-discovery verb,
already refuses a contentless query the same way (`dispatch.py`, "search needs a query or
--tag/--color"), so the two siblings behave alike.

The verb is `search`, not `find`, per `../direction/conventions.md`: this is ranked discovery over
a prose corpus, not a deterministic query over T3D-tree state.

**Rejected:** *word tokenization with AND semantics* (what `texture search` does) — deferred, not
dismissed; the texture catalog matches short structured fields where multi-term AND is the natural
reading, while these are long prose documents where a literal phrase is what a reader types.
**Rejected:** *matching against the topic key as well as title and body* — a key is derived from
the filename, which is already reflected in the title of every page that has a heading, so it would
mostly double-count.

**Refs:** `uedcli/userdocs.py` (`search`, `_split_title`), `uedcli/dispatch.py` (`_dispatch_docs`).

## The stderr counts use the house `(s)` spelling

**Why it is this way:** `docs list` and `docs search` print `N topic(s)` / `N match(es)` on stderr.
Sixteen sibling summaries in `dispatch.py` already spell it `actor(s)`, `brush(es)`, `wire(s)`,
`finding(s)`, and a reader who has seen one has seen them all. The spec's prose happened to write
`0 matches` for the no-hit case; that is one illustrative string against an established convention,
and matching the convention is worth more than matching the illustration — the alternative prints
the ungrammatical `1 matches` and `1 topics` on a one-hit query.

**Rejected:** *branching on the count* (`1 match` / `2 matches`) — grammatically nicer, but it
would be the only verb in the CLI doing it, and consistency across sibling verbs is what makes
output skimmable.

**Refs:** `uedcli/dispatch.py` (`_dispatch_docs`, and the `actor(s)` summaries it mirrors).

## The module is `userdocs.py`, and it raises `dispatch._SelectionExit`

**Why it is this way:** `docs.py` would be the obvious name and is exactly the problem — this repo
has a `docs/` tree (user-facing), a `dev/docs/` tree (developer), and a `docs` verb, so a module
called `docs` makes every grep and every import line ambiguous about which of the three is meant.
`userdocs` says which corpus it serves.

Errors use the CLI's existing `_SelectionExit` rather than a new exception class, so the top-level
`dispatch()` guard already turns them into a clean stderr message and exit 2 with no new wiring.
`_SelectionExit` lives in `dispatch.py`, which imports this module, so the import is done **inside**
the raising helper (`userdocs._selection_exit`) — a module-level import would be a cycle, while a
function-level one cannot be, since `dispatch` is fully loaded before any docs verb runs.

**Rejected:** *a dedicated `DocsError` caught in `dispatch()`* — a second exception type and a
second `except` arm for exactly the behaviour `_SelectionExit` already has. **Rejected:** *moving
`_SelectionExit` to its own module to break the direction of the dependency* — a worthwhile cleanup
in its own right, but it touches every raise site in `dispatch.py` and does not belong in this
change; the one-line lazy import is the local cost of not doing it.

**Refs:** `uedcli/userdocs.py`, `uedcli/dispatch.py` (`_dispatch_docs`), `uedcli/cli.py` (the
`docs` parser), `uedcli/tests/test_docs_command.py`.

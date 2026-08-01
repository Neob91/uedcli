# `userdocs.py` — serving the user-facing docs from the CLI

Why the `docs list|show|search` verbs are built the way they are. What they do lives in
[`../architecture.md`](../architecture.md) "Commands (namespaced)"; the user-facing reference is
`docs/usage.md`.

uedcli's user documentation lives in `docs/` (`usage.md` plus the `leveldesign/` guides). The `docs`
verbs make that tree readable through uedcli itself, so a consumer — a person at a terminal, or a
shipped Claude skill — reads the docs baked into the binary instead of carrying a copy that drifts
out of date. A topic key is the name a page is addressed by: its path with `.md` dropped, a
`README.md` folded onto its directory.

> Some of what follows is the owner's decision, not an agent's, and this agent-owned tree is the
> wrong place for it. The product intent (docs are an asset of the tool; a shipped skill queries the
> tool instead of bundling copies) and the duplicate-key hard error are his, parked as
> `[OWNER — confirm]` items on [`dev/docs/board/inbox/`](../board/inbox/) with the proposed
> `direction/` wording, pending his yes. They are restated below so a reader can follow the
> engineering, but `direction/` is where they will live.

## `show` resolves through the enumerated served set, never a path join

The obvious implementation — join the topic onto the docs root and read that file — makes
correctness depend on a blacklist anticipating `../`, an absolute path, a symlink, a directory, a
non-markdown file and the developer tree. Enumerating the served set first and looking the key up in
it makes every one of those a plain "not found" by construction: a file never enumerated has no key
to hit. The same enumeration feeds `list`, `search` and `show`, so the three cannot disagree, and
there is no second code path to keep in step.

**Rejected:** joining the topic onto the root and validating the result (`resolve()` +
`is_relative_to(root)`) — it works, but the check must be remembered at every call site rather than
being a property of the design, and it still needs separate rules for directories, non-`.md` files
and the `dev/` subtree. **Rejected:** serving a bare basename when unique — `human-scale` exists
twice today, so the rule would resolve or fail depending on which pages exist, and a page added later
would silently change what an existing key means.

**Refs:** `uedcli/userdocs.py` (`load_docs`, `find_doc`), `uedcli/tests/test_docs_command.py`.

## The tree is walked by hand, because `rglob` turns an unreadable directory into an empty one

`pathlib`'s glob swallows the `OSError` that `scandir` raises on a directory the process cannot read,
reporting "nothing here" for "I could not look". With `root.rglob("*.md")` an unreadable docs root
listed as `0 topics` at exit 0, and an unreadable subdirectory was worse: its pages vanished from
`list`, `search` and `show` with no signal anywhere. That is the shape `../direction/conventions.md`
"No silent half-answers" forbids, and it is not hypothetical — root-owned directories left by
container runs are a recurring problem here, which `dispatch.py` already carries a filesystem-error
handler for. `_markdown_files` therefore walks with `os.scandir` and turns any `OSError` into a clean
exit-2 naming the directory. It also prunes a top-level `dev/` as it walks rather than filtering
afterwards, so an unreadable developer tree — never served — cannot fail a user's command. (That
prune is defence in depth: `dev/docs/` is a sibling of `docs/`, outside the docs root, so the prune
fires on nothing today. The root is the guarantee.)

Directory symlinks are not followed, matching `rglob`: a link can otherwise walk the enumeration out
of the tree or into a cycle. A symlinked file is collected and then vetted against the resolved root.

Every comparison in the module is case-insensitive — the `dev/` prune, the `README` fold, the `.md`
extension, key lookup, the duplicate-key check, and the sort order. A prune that fired on `dev` but
not `DEV` is a real hole on a case-insensitive filesystem, and Windows via Nuitka is a stated ship
target; the rest follow so the served set never changes shape with the platform.

**Rejected:** `rglob` plus a pre-flight `os.access(root, R_OK)` check — it covers only the root,
leaves every subdirectory silently droppable, and races the walk. **Rejected:** reporting the
unreadable directory on stderr and serving what was readable — the warning scrolls away and the
truncated listing is taken for the whole tree, which is the exact failure mode being fixed.

**Refs:** `uedcli/userdocs.py` (`_markdown_files`, `_in_dev_tree`), `uedcli/tests/test_docs_command.py`.

## The docs root resolves source-tree before the packaged copy

The order is `$UEDCLI_DOCS_DIR` → `docs/` beside the installed package → `uedcli/_docs/` inside it. A
future wheel/Nuitka build generates `_docs/` from the source tree; if that copy won, a developer who
once ran an experimental build would afterwards read a frozen snapshot while editing the live `docs/`
tree, with nothing on screen to say so. In a real install no `docs/` sibling exists, so the packaged
copy answers there. The package is located via `importlib.resources.files("uedcli")` rather than
counting `.parent`s off `__file__`, so moving the module inside the package cannot break the
resolver.

An unresolvable root — including a `$UEDCLI_DOCS_DIR` pointing at nothing — is a clean exit-2 error
naming what was wrong, not an empty listing: an empty served set reads as "this build ships no docs"
when the truth is "your override is wrong". (The spec's illustrative resolver snippet returned the
override unchecked; its error and testing sections require the clean refusal, and that is what is
built.)

All three shapes of broken root exit 2 naming the root: nonexistent, unreadable, and
present-and-readable-but-holding-no-pages. The third is the most confusing: `0 topic(s)` at exit 0 is
the same output a genuinely doc-free build would produce, so the user cannot tell a misconfiguration
from a design fact and is never told where the tool looked. uedcli always ships pages, so zero is
never a legitimate answer.

**Rejected:** softening the docstring instead (admitting an empty listing is possible) — cheaper, but
it trades a true promise for a caveat, and the caveat is exactly the case a user cannot diagnose.
**Rejected:** erroring only when the root is the packaged `_docs` — the override and source-tree
branches are where a wrong root actually comes from.

**Rejected:** packaged-first, on the grounds that it is the shipping configuration — it optimizes for
the case that cannot go wrong (an install has only one copy) at the cost of the case that can.
**Rejected:** a committed index file of keys and titles — the tree is ~50 files, enumeration is
already imperceptible, and an index is one more artifact that can disagree with the tree.
**Rejected:** supporting zip-imported / zipapp installs — uedcli ships filesystem-backed (pipx,
Nuitka), and a `Traversable`-only code path would be untested surface.

## A duplicate topic key is a hard error, not a precedence rule

This is the owner's ruling, not an engineering call — parked as an `[OWNER — confirm]` item on
[`dev/docs/board/inbox/`](../board/inbox/) for `direction/conventions.md`. The reasoning is kept here
so the code is readable; the ruling belongs there.

Two files can claim one key — `X/README.md` beside a sibling `X.md`, a `docs/index.md` against the
root README's reserved `index`, or two paths differing only in case (lookup is case-insensitive).
Picking one silently means `docs show X` returns a page and the reader cannot tell it was not the
other. Raised during enumeration rather than at lookup, the error takes down every `docs` invocation
and the test suite the moment such a file is committed — caught while authoring, never by a user of a
shipped binary. The strict choice is affordable because the cost lands on the author, not the user.

**Rejected:** first-wins / README-wins precedence — a silent wrong answer, and the losing page
becomes unreachable with nothing reporting it. **Rejected:** warning on stderr and continuing — the
warning scrolls away and the ambiguous answer is taken for a definite one.

## `show` writes bytes; `show -` is atomic and marks each page

The pages contain UTF-8 typography (`°`, `×`, `≡`, `…`). Printing through Python's text layer
re-encodes them in whatever the terminal locale claims, so a non-UTF-8 locale would corrupt the
output; `sys.stdout.buffer` is a byte-for-byte copy of the file.

`show -` (topic keys from stdin) resolves the whole set before writing anything: if any key is
unknown it prints nothing and exits 2 naming the offending keys, per "no silent half-answers". On
success each page is preceded by a `<!-- topic: <key> -->` marker line — before the page, not between
pages, so every marker names the markdown that follows it. It is a markdown comment, so the stream
stays valid markdown.

**Rejected:** a separator only between pages — the marker would have to name one of the two pages it
sits between, leaving the first page unlabelled and the association ambiguous. **Rejected:** skipping
unresolvable keys with a warning — see above.

## `search` is a literal substring with a fixed 10× title weight

The score is `10 × (query in title) + (number of BODY lines containing the query)`, ties broken
lexicographically by key. A caller pipes the result into `docs show -`, so a predictable, explainable
ranking beats a better-tuned opaque one. No tokenization, stemming or fuzzy distance in v1 — each
would need its own tuning and tests to earn its place.

The weight must be stated, not "a title match wins": eleven body mentions outrank a title match, and
on the shipped tree `docs search mover` puts `usage` (73 body lines, no title hit) above
`leveldesign/general/movers` (title hit, 39 body lines). The user-facing help and `docs/usage.md`
therefore say a title match is worth ten body lines — the true, predictable arithmetic — rather than
promising an ordering the code does not guarantee.

A page's heading is its title, not also a body line. Counting it in both places inflated a title
match to 11 instead of 10 and made the reported snippet the heading itself — a `--json` row whose
`snippet` merely repeats its `title` with a leading `#` is evidence of nothing. `_split_title` peels
the title line off once, so the two cannot disagree about which line it was.

An empty or whitespace-only query is refused by name: a blank substring is inside every line of every
page and would "match" the entire corpus in score order. `texture search`, the other ranked-discovery
verb, refuses a contentless query the same way (`cli/commands/texture.py`, "search needs a query or
--tag/--color"), so the two siblings behave alike.

The verb is `search`, not `find`, per `../direction/conventions.md`: this is ranked discovery over a
prose corpus, not a deterministic query over T3D-tree state.

**Rejected:** word tokenization with AND semantics (what `texture search` does) — deferred, not
dismissed; the texture catalog matches short structured fields where multi-term AND is the natural
reading, while these are long prose documents where a literal phrase is what a reader types.
**Rejected:** matching against the topic key as well as title and body — a key is derived from the
filename, already reflected in the title of every page that has a heading, so it would mostly
double-count.

**Refs:** `uedcli/userdocs.py` (`search`, `_split_title`), `uedcli/cli/commands/docs.py` (`run`).

## The stderr counts use the house `(s)` spelling

`docs list` and `docs search` print `N topic(s)` / `N match(es)` on stderr. Sixteen sibling summaries
in `dispatch.py` already spell it `actor(s)`, `brush(es)`, `wire(s)`, `finding(s)`. The spec's prose
wrote `0 matches`, but that is one illustrative string against an established convention; the
alternative prints the ungrammatical `1 matches` and `1 topics` on a one-hit query.

**Rejected:** branching on the count (`1 match` / `2 matches`) — grammatically nicer, but it would be
the only verb in the CLI doing it, and consistency across sibling verbs is what makes output
skimmable.

**Refs:** `uedcli/cli/commands/docs.py` (`run`, and the `actor(s)` summaries it mirrors).

## The module is `userdocs.py`, and it raises its own `UserDocsError`

`docs.py` would be the obvious name and is exactly the problem — this repo has a `docs/` tree
(user-facing), a `dev/docs/` tree (developer), and a `docs` verb, so a module called `docs` makes
every grep and import line ambiguous about which is meant. `userdocs` says which corpus it serves.

`userdocs` is a service, so it raises a service-local `UserDocsError` (bad/missing docs root,
unreadable tree, duplicate key) instead of importing the CLI boundary. The `docs` handler
(`cli/commands/docs.py`, `run`) catches it and translates it to `CommandError`, which the central
`dispatch()` guard prints to stderr as a clean exit 2.

The earlier design reused a private `dispatch` exception through a function-local import to avoid a
new exception type. That import was a reverse edge — a service reaching back into the CLI — and part
of the `userdocs`/`preview_game` → `dispatch` cycle the reorg deletes; the lazy import that dodged the
cycle is gone with it.

**Rejected:** keeping the reverse import into `dispatch` — it is the edge the reorg exists to remove.
**Rejected:** a new `except` arm in the central `dispatch()` guard for `UserDocsError` — the docs
handler translates its own error locally, like the other family-local translations.

**Refs:** `uedcli/userdocs.py` (`UserDocsError`), `uedcli/cli/commands/docs.py` (`run`),
`uedcli/cli/parsers/docs.py` (the `docs` parser), `uedcli/tests/test_docs_command.py`.

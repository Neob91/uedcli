"""The user-facing documentation, served from the CLI itself (`uedcli docs list|show|search`).

**What this module is for.** uedcli's prose documentation for its *users* lives in the repo's
`docs/` directory — `docs/usage.md` (the CLI reference) and `docs/leveldesign/**` (level-design
craft). This module makes that tree queryable through uedcli itself, so a consumer (a human at a
terminal, or a shipped Claude skill routing a user to the right page) reads the docs **baked into
the binary it has** instead of carrying its own copy that drifts. Same pattern as `git help
<topic>` / `rustc --explain`.

**What is NOT served.** The *developer* documentation tree (`dev/docs/**` — architecture, specs,
spikes, the board) is a different audience and must never appear here: a uedcli user cannot open
those files and must not be sent to them.

**What actually keeps it out is the choice of ROOT.** In the current layout `dev/docs/` is a
SIBLING of `docs/`, not a subdirectory of it, so the developer tree is simply not under the docs
root and was never reachable. The `dev/` prune in `load_docs` is **defence in depth, not the
mechanism**: it fires on nothing in today's tree, and exists so that a future layout which does put
a `dev/` inside the docs root — or an operator pointing `$UEDCLI_DOCS_DIR` at the repo root —
cannot leak it. Do not treat the prune as the guarantee and relax the root resolution on its
strength; the root is the guarantee.

**Three concepts, defined before they are used:**

- **docs root** — the directory the served tree is read from (`docs_root()`).
- **topic key** — the stable name a doc is addressed by: its path under the docs root with the
  `.md` extension removed, and with a `README.md` folded to the directory it documents
  (`leveldesign/deusex/README.md` → `leveldesign/deusex`; the root `docs/README.md` → the reserved
  key `index`). `docs list` and `docs search` print topic keys; `docs show` takes one.
- **served set** — every doc under the docs root, enumerated once per invocation with its topic
  key and title. `show` resolves a request by looking a key up in this map — it never joins the
  user's text onto a filesystem path — which is what structurally rules out `../` traversal,
  absolute paths, directory reads, non-markdown dumps and dev-tree leakage.

Rationale (why a resolver order, why a hard error on a duplicate key, why this module name):
`dev/docs/rationale/userdocs.md`.
"""
from __future__ import annotations

import importlib.resources
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: Directory name, **at the top level of the docs root only**, that is never served. It is matched
#: against `parts[0]` alone, not "any path segment called dev", so a legitimately-named
#: `leveldesign/general/dev-notes.md` or a future `.../dev/` deeper in the tree is unaffected.
#: The comparison is CASE-INSENSITIVE, like every other comparison in this module: on a
#: case-insensitive filesystem (Windows/macOS — Nuitka ships there) a directory spelled `DEV`
#: is the same directory, and this is the module's one security-relevant filter.
_DEV_DIR = "dev"

#: Topic key the root `README.md` folds to. Reserved: a `docs/index.md` would collide with it and
#: is rejected by the duplicate-key check in `load_docs`.
ROOT_KEY = "index"

#: A doc's title is its first level-1 markdown heading (`# Something`).
_H1 = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)

#: Longest snippet `docs search --json` reports for a match.
SNIPPET_MAX = 120


class UserDocsError(Exception):
    """A user-facing docs failure — a broken/misconfigured docs root, an unreadable tree, or a
    duplicate topic key. This module is a service, not the CLI boundary, so it raises its own error
    rather than reaching into `dispatch`; the docs command turns it into a clean stderr message and
    exit 2."""


@dataclass(frozen=True)
class Doc:
    """One served document.

    `key` is its topic key, `path` the file it was read from, `title` its first `# ` heading (or a
    fallback, see `_title`), and `body_lines` every line of the page EXCEPT the one the title came
    from — kept so `search` can scan bodies without a second read, and body-only so a match cannot
    report the heading back as its evidence.

    `show` re-reads `path` as **bytes**, so what a user sees is never a decode/re-encode round trip
    of anything held here.
    """
    key: str
    path: Path
    title: str
    body_lines: tuple[str, ...]


def docs_root() -> Path:
    """The directory the served docs are read from, in a fixed three-step order.

    1. **`$UEDCLI_DOCS_DIR`** — an explicit override, used by the tests and by packaging.
    2. **The source checkout** — `docs/` beside the installed package directory. Anchored on the
       package itself (`importlib.resources.files`) rather than counting `.parent`s off this
       file, so moving the module inside the package cannot break it.
    3. **The bundled copy** — `uedcli/_docs/`, which a wheel/Nuitka build will generate from the
       source tree. It does not exist yet and this branch is dormant until packaging lands.

    The source checkout deliberately wins over the bundled copy: during development a stale
    `_docs/` left behind by an experimental build must never shadow the live `docs/` tree being
    edited. In a real install no `docs/` sibling exists, so step 3 is what answers.

    Every failure is a clean exit-2 error naming what was wrong — never a traceback, and never a
    silently empty served set (a docs root that does not exist would otherwise make `docs list`
    print nothing and exit 0, which reads as "this build has no docs" rather than "your override
    is wrong").
    """
    override = os.environ.get("UEDCLI_DOCS_DIR")
    if override:
        root = Path(override)
        if not root.is_dir():
            raise UserDocsError(
                f"UEDCLI_DOCS_DIR is not a directory: {override}")
        return root
    pkg = Path(str(importlib.resources.files("uedcli")))
    source = pkg.parent / "docs"
    if source.is_dir():
        return source
    bundled = pkg / "_docs"
    if bundled.is_dir():
        return bundled
    raise UserDocsError(
        f"uedcli docs unavailable (broken install): no docs directory at {source} or {bundled} "
        f"— set UEDCLI_DOCS_DIR to a docs tree to override")


def topic_key(rel: PurePosixPath | str) -> str:
    """The topic key for a served file's path **relative to the docs root**.

    Drops the `.md` extension, then folds a `README.md` onto the directory it documents — so the
    overview of a directory is addressed by the directory's own name rather than by a `/README`
    suffix nobody would guess. The root `README.md` has no containing directory inside the tree,
    so it folds to the reserved key `index`.

    The `README` test is case-insensitive, like every other comparison in this module: on a
    case-insensitive filesystem `Readme.md` and `README.md` are one name, and a fold that fired on
    only one spelling would make the served key depend on the platform.
    """
    parts = PurePosixPath(rel).with_suffix("").parts
    if parts and parts[-1].casefold() == "readme":
        parts = parts[:-1]
        if not parts:
            return ROOT_KEY
    return "/".join(parts)


def _split_title(text: str, key: str) -> tuple[str, tuple[str, ...]]:
    """Split a page into its **title** and its **body lines**.

    The title is the first level-1 markdown heading (`# Something`) whose text is not blank; the
    body is every other line. Both come out of one scan so they can never disagree about which
    line the title was — a page whose only `#` line is blank keeps that line in the body and takes
    the fallback title.

    The title fallback is the key's last segment, which is exactly what each shape of doc should
    read as: a folded `README.md` falls back to the **directory name** it documents
    (`leveldesign/deusex` → `deusex`) and never to the useless literal `README`, while a leaf falls
    back to its file basename (`.../lighting` → `lighting`). The root index falls back to `index`.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _H1.match(line)
        if m and m.group(1).strip():
            return m.group(1).strip(), tuple(lines[:i] + lines[i + 1:])
    return key.rsplit("/", 1)[-1], tuple(lines)


def _read(path: Path) -> str:
    """Decode a served file for title extraction and body search.

    Undecodable bytes are replaced rather than raising: a mis-encoded byte deep in one doc must not
    take out `docs list` for the whole tree. `show` writes the file's raw bytes, so nothing a user
    reads passes through this replacement. An unreadable *file* is a different matter and is a
    clean exit-2 error naming it.
    """
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError as e:
        raise UserDocsError(f"cannot read doc file {path}: {e.strerror or e}") from None


def _in_dev_tree(rel: PurePosixPath) -> bool:
    """Is this docs-root-relative path inside the top-level `dev/` directory (the developer tree)?"""
    return bool(rel.parts) and rel.parts[0].casefold() == _DEV_DIR


def _markdown_files(root: Path) -> list[Path]:
    """Every served `*.md` file under `root`, sorted, with the developer tree pruned as it walks.

    **Why this is a hand-written walk and not `root.rglob("*.md")`.** `pathlib`'s glob swallows the
    `OSError` from `scandir`, so a directory the process cannot read reads back as "this directory
    holds nothing". An unreadable docs root would then make `docs list` print an empty listing at
    exit 0, and an unreadable SUBdirectory would silently drop its pages from `list`, `search` AND
    `show` — a partial answer with no signal at all, which is exactly what
    `direction/conventions.md` "No silent half-answers" forbids. Root-owned trees left by container
    runs are a live, recurring failure mode in this repo, so this is not hypothetical. Here every
    unreadable directory is a clean exit-2 error naming it.

    Directory symlinks are deliberately NOT followed (`is_dir(follow_symlinks=False)`), matching
    what `rglob` did: a link can otherwise walk the enumeration out of the tree or into a cycle. A
    symlinked *file* is still collected here and vetted against the root in `load_docs`.
    """
    found: list[Path] = []
    pending: list[Path] = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError as e:
            raise UserDocsError(
                f"cannot read docs directory {directory}: {e.strerror or e}") from None
        for entry in entries:
            path = Path(entry.path)
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError as e:                       # a stat that fails mid-walk, same rule
                raise UserDocsError(
                    f"cannot read docs entry {path}: {e.strerror or e}") from None
            if is_dir:
                if not _in_dev_tree(PurePosixPath(path.relative_to(root).as_posix())):
                    pending.append(path)
            elif entry.name.casefold().endswith(".md"):
                found.append(path)
    return sorted(found)


def load_docs(root: Path | None = None) -> list[Doc]:
    """Enumerate the served set once, sorted by topic key.

    This is the ONE enumeration behind `list`, `search` and `show` — they cannot disagree about
    what is served, and `show` has no path-join of its own to get wrong.

    Two structural exclusions, neither of which is a filter over a user-supplied string:

    - the top-level `dev/` directory of the docs root is never descended (the developer tree);
    - a symlink whose real target resolves outside the docs root, or back into that `dev/`
      directory, is skipped — so a link cannot smuggle in a file the walk would not have reached.
      (Directory symlinks are not followed at all; see `_markdown_files`.)

    **A duplicate topic key is a hard error**, naming both files, not a silent precedence rule. Two
    files claiming one key make the served set ambiguous — `docs show <key>` would serve one of
    them and no reader could tell which. Because the failure happens during *enumeration*, it trips
    every `docs` invocation and the test suite, so it is caught while authoring the docs; a user of
    a shipped binary can never encounter it. Keys are compared case-insensitively, the same way
    `find_doc` resolves them, so two files whose keys differ only in case are a collision too.
    """
    root = docs_root() if root is None else root
    resolved_root = root.resolve()
    docs: list[Doc] = []
    seen: dict[str, Doc] = {}
    for path in _markdown_files(root):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if not path.is_file():
            continue
        real = path.resolve()
        try:
            real_rel = PurePosixPath(real.relative_to(resolved_root).as_posix())
        except ValueError:
            continue                      # a symlink pointing outside the docs root
        if _in_dev_tree(real_rel):
            continue                      # a symlink pointing into the developer tree
        key = topic_key(rel)
        if (clash := seen.get(key.casefold())) is not None:
            first, second = sorted([clash.path.relative_to(root).as_posix(), rel.as_posix()])
            raise UserDocsError(
                f"docs: two files claim the topic key {key!r}: {first} and {second} "
                f"— rename one (a README.md takes its directory's name; the root README.md takes "
                f"{ROOT_KEY!r})")
        title, body = _split_title(_read(path), key)
        doc = Doc(key=key, path=path, title=title, body_lines=body)
        seen[key.casefold()] = doc
        docs.append(doc)
    if not docs:
        # A readable docs root that serves nothing is a broken install or a wrong override, never a
        # legitimate state — uedcli always ships pages. Answering `0 topic(s)` at exit 0 would tell
        # a user "this build has no documentation" in the exact words it would use if that were
        # true, so the one thing they need to know (WHERE it looked) never reaches them.
        raise UserDocsError(
            f"uedcli docs unavailable: no documentation pages under {root} "
            f"— set UEDCLI_DOCS_DIR to a docs tree to override")
    # Sorted the way lookup compares — case-insensitively — so the printed order and the resolution
    # order cannot disagree. (A pair of keys differing only in case is a collision, raised above.)
    docs.sort(key=lambda d: d.key.casefold())
    return docs


def normalize_key(raw: str) -> str:
    """A requested topic as it is compared against the served set.

    Surrounding whitespace is dropped (a key read from stdin arrives with its newline) and a
    trailing `.md` is optional, so both `leveldesign/general/lighting` and
    `leveldesign/general/lighting.md` name the same doc. Nothing else is rewritten: this is a
    lookup key, never a path, so there are no segments to normalize away.
    """
    key = raw.strip()
    if key.casefold().endswith(".md"):
        key = key[:-3]
    return key


def find_doc(docs: list[Doc], raw: str) -> Doc | None:
    """The served doc a requested topic names, or `None`.

    Matching is case-insensitive on the **whole** topic key. A bare basename is deliberately NOT a
    resolver: `human-scale` names nothing, because two docs end in that segment and quietly picking
    one would be a wrong answer that looks right. `suggest` turns that miss into a hint listing
    both.
    """
    want = normalize_key(raw).casefold()
    if not want:
        return None
    for doc in docs:
        if doc.key.casefold() == want:
            return doc
    return None


def suggest(docs: list[Doc], raw: str, limit: int = 6) -> list[str]:
    """Topic keys worth naming in a "not found" message, best first.

    Three kinds of near miss, in order:

    1. **the old `<dir>/README` address** — folded away, so redirect it to the directory key;
    2. **a bare last segment** — `human-scale` lists every key ending in that segment;
    3. **a prefix or substring** — `leveldesign/deus` lists what it could have meant.
    """
    want = normalize_key(raw).casefold()
    if not want:
        return []
    keys = [d.key for d in docs]
    hits: list[str] = []

    def add(key: str) -> None:
        if key not in hits:
            hits.append(key)

    if want.endswith("/readme"):
        parent = want[: -len("/readme")]
        for k in keys:
            if k.casefold() == parent:
                add(k)
    if want in ("readme", ROOT_KEY):
        for k in keys:
            if k == ROOT_KEY:
                add(k)
    for k in keys:                                   # a bare last segment
        if k.casefold().rsplit("/", 1)[-1] == want:
            add(k)
    for k in keys:                                   # a prefix
        if k.casefold().startswith(want):
            add(k)
    for k in keys:                                   # any substring, either direction
        if want in k.casefold() or k.casefold() in want:
            add(k)
    return hits[:limit]


def not_found_message(docs: list[Doc], raw: str) -> str:
    """The exit-2 message for one unresolvable topic, with a hint when there is a near miss.

    An empty or all-whitespace topic is quoted rather than interpolated bare: the house rule is
    that an error NAMES the offending value, and `Doc not found:` followed by nothing names
    nothing — the reader cannot even tell an empty argument from a formatting bug.
    """
    shown = normalize_key(raw) or raw
    if not shown.strip():
        return (f"Doc not found: {raw!r} — a topic key cannot be empty; "
                f"`uedcli docs list` prints every one")
    msg = f"Doc not found: {shown}"
    if hints := suggest(docs, raw):
        msg += "\ndid you mean: " + ", ".join(hints)
    return msg


@dataclass(frozen=True)
class Hit:
    """One `docs search` result: the doc, its relevance score, and the line that matched."""
    doc: Doc
    score: int
    snippet: str


def search(docs: list[Doc], query: str) -> list[Hit]:
    """Rank the served docs against a literal, case-insensitive substring.

    The query is a plain substring, not a set of words: there is no tokenization, no stemming and
    no fuzzy distance, because a predictable rule is worth more than a clever one to a caller
    piping the result into `docs show -`.

    Score = 10 per title match + 1 per **body** line containing the query. The title and the body
    are counted separately and never both from the same line: the page's own heading is the title,
    so it is not also a body line. Otherwise a title match scored 11 rather than 10 and — worse —
    the reported snippet was the heading itself, giving a `--json` row whose `snippet` merely
    repeated its `title` with a leading `#`.

    The weight makes a doc *about* the query outrank a doc that merely mentions it several times,
    without ever hiding the latter. Docs scoring zero are omitted; ties break lexicographically by
    topic key, so the order is stable across runs.
    """
    needle = query.casefold()
    hits: list[Hit] = []
    for doc in docs:
        lines = [ln for ln in doc.body_lines if needle in ln.casefold()]
        score = (10 if needle in doc.title.casefold() else 0) + len(lines)
        if not score:
            continue
        snippet = lines[0].strip()[:SNIPPET_MAX] if lines else ""
        hits.append(Hit(doc=doc, score=score, snippet=snippet))
    hits.sort(key=lambda h: (-h.score, h.doc.key.casefold()))
    return hits

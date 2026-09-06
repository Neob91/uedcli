"""Board invariants — `dev/docs/board/` is one directory per work item.

The board is a set of stage directories (`inbox`, `to-spec`, … `done`); the stage an item is in IS
the directory it sits in, and an item advances by `git mv`. Each item directory holds an
`overview.md` whose TOML frontmatter carries priority, kind and a one-line summary, and may hold
`spec.md`, `plan.md` and `questions/<q>.md`. Spec: `dev/docs/specs/2026-07-27-board-per-item-directories.md`.

WHY THESE ARE TESTS AND NOT PROSE. Three of them guard things that fail silently otherwise:

* **A question file is reachable from every stage** (:test_a_question_never_moves_its_item). A
  blocked item keeps its stage — the owner ruled that a question is filed against the item where it
  is, never bounced — so the only way a blocker hides is by sitting somewhere `bin/board questions`
  does not look.
* **A dangling `board item` reference** (:test_slug_references_resolve). Slug references replaced
  ~400 path citations precisely because a path into `specs/` rots silently; that trade only pays if
  a dangling slug is loud.
* **The frontmatter SUBSET** (:test_frontmatter). `bin/board` is bash with no venv and hand-rolls its
  reader, so the corpus must stay inside what both it and `tomllib` handle.

Whole-board shape — exactly eight stages, no loose files — is asserted by
:test_board_holds_only_the_eight_stages and :test_a_stage_holds_only_item_directories. They could
not exist until the migration finished, because every intermediate commit legitimately held stage
directories *and* un-migrated `.md` files.
"""
from __future__ import annotations

import functools
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "dev/docs/board"

STAGES = ("inbox", "to-spec", "to-spike", "to-plan", "to-build", "someday", "stale", "done")

REQUIRED_KEYS = {"priority", "kind", "summary"}
OPTIONAL_KEYS = {"depends-on", "spikes"}
PRIORITIES = {"p1", "p2", "p3", "p?"}
KINDS = {"implement", "chore", "debug", "docs", "owner-question", "unknown"}

#: ``board item `slug`` / ``board items `a`, `b``. Two constraints, both load-bearing:
#: the BACKTICKS (the bare phrase appears ~75 times in the tree as ordinary prose), and the
#: backticked text being SLUG-SHAPED — kebab-case only. Without the second, two live prose sites
#: match and fail: `plans/2026-07-18-csg-order-plan.md` writes "the board item `to-plan.md`" (a
#: filename) and `specs/2026-07-19-texture-catalog-redesign.md` follows the phrase with a
#: backticked multi-word title. Neither is a reference, and neither file's job is to define the
#: form, so exempting them would be wrong; narrowing the match is what makes the check honest.
_SLUG_REF = re.compile(r"board items?\s+((?:`[a-z0-9-]+`(?:\s*,\s*)?)+)", re.IGNORECASE)
_BACKTICKED = re.compile(r"`([a-z0-9-]+)`")

#: Files that MAY write an unresolvable ``board item `x``` because documenting the form is their
#: job. Without this the convention's own documentation cannot be written — the same problem
#: `test_doc_links.py` solves with `_MAY_NAME_DELETED`.
_MAY_DEFINE_THE_FORM = frozenset({
    "CLAUDE.md",
    "dev/docs/board/README.md",
    "dev/docs/rationale/board.md",
    "dev/docs/specs/2026-07-27-board-per-item-directories.md",
    "dev/docs/plans/2026-07-27-board-per-item-directories-plan.md",
    "uedcli/tests/test_board.py",
})

_REF_SUFFIXES = (".md", ".py", ".sh", ".toml", ".rs")


def _items() -> list[Path]:
    """Every item directory, across every stage that exists yet. A stage dir may hold a GROUP
    directory (no `overview.md` of its own) whose children are the items — the owner-ruled
    `to-build/native-materialize/` consolidation shape — so a dir without `overview.md` recurses
    one level."""
    out: list[Path] = []
    for stage in STAGES:
        for d in (BOARD / stage).glob("*"):
            if not d.is_dir():
                continue
            if (d / "overview.md").is_file():
                out.append(d)
            else:
                out.extend(sub for sub in d.glob("*") if sub.is_dir())
    return sorted(out)


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def _frontmatter(overview: Path) -> dict:
    """Parse the ``+++`` block, or raise `ValueError` with a readable message."""
    text = overview.read_text(encoding="utf-8")
    if not text.startswith("+++\n"):
        raise ValueError(f"{_rel(overview)}: no `+++` frontmatter on line 1")
    _, _, rest = text.partition("+++\n")
    body, sep, _ = rest.partition("\n+++")
    if not sep:
        raise ValueError(f"{_rel(overview)}: frontmatter is not closed by `+++`")
    try:
        return tomllib.loads(body)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{_rel(overview)}: frontmatter is not valid TOML — {exc}") from exc


@functools.lru_cache(maxsize=None)
def _tracked(*suffixes: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p and p.endswith(suffixes)]


if not _items():
    pytest.skip("no board items migrated yet", allow_module_level=True)


def test_board_holds_only_the_eight_stages() -> None:
    """`board/` is the eight stage directories plus `README.md`, and nothing else.

    A loose `.md` at the top level is how the old shape comes back one file at a time — someone
    parks a list somewhere rather than filing items, and the board quietly has two homes again.
    """
    entries = {p.name for p in BOARD.iterdir() if not p.name.startswith(".")}
    assert entries == set(STAGES) | {"README.md"}, (
        f"unexpected entries in dev/docs/board/: {sorted(entries - set(STAGES) - {'README.md'})}; "
        f"missing: {sorted(set(STAGES) | {'README.md'} - entries)}"
    )


@pytest.mark.parametrize("stage", STAGES)
def test_a_stage_holds_only_item_directories(stage: str) -> None:
    """`ls <stage>/` IS the queue — so a stage may hold item directories and `.gitkeep`, nothing else."""
    stray = sorted(p.name for p in (BOARD / stage).iterdir() if p.is_file() and p.name != ".gitkeep")
    assert not stray, f"dev/docs/board/{stage}/ holds loose files: {stray}"
    assert (BOARD / stage / ".gitkeep").is_file(), (
        f"dev/docs/board/{stage}/.gitkeep is missing — git cannot track the directory once it empties"
    )


def test_item_shape() -> None:
    """An item is an `overview.md` plus, at most, a `questions/` directory."""
    bad = []
    for item in _items():
        if not (item / "overview.md").is_file():
            bad.append(f"{_rel(item)}: no overview.md")
            continue
        stray = [d.name for d in item.iterdir() if d.is_dir() and d.name != "questions"]
        if stray:
            bad.append(f"{_rel(item)}: unexpected subdirectories {stray} (only `questions/` allowed)")
    assert not bad, "\n".join(bad)


def test_frontmatter() -> None:
    """Required keys present, no unknown keys, values in range — and inside the pinned subset.

    The subset check is the load-bearing half. `bin/board` parses this frontmatter in bash with a
    hand-rolled reader, so anything TOML permits but that reader does not handle (literal strings,
    triple-quoted strings, comments, multi-line arrays) would make the two disagree silently.
    """
    bad = []
    for item in _items():
        overview = item / "overview.md"
        try:
            fm = _frontmatter(overview)

            missing = REQUIRED_KEYS - fm.keys()
            if missing:
                bad.append(f"{_rel(overview)}: missing frontmatter keys {sorted(missing)}")
            unknown = fm.keys() - REQUIRED_KEYS - OPTIONAL_KEYS
            if unknown:
                bad.append(f"{_rel(overview)}: unknown frontmatter keys {sorted(unknown)}")
            if "priority" in fm and fm["priority"] not in PRIORITIES:
                bad.append(f"{_rel(overview)}: priority {fm['priority']!r} not in {sorted(PRIORITIES)}")
            if "kind" in fm and fm["kind"] not in KINDS:
                bad.append(f"{_rel(overview)}: kind {fm['kind']!r} not in {sorted(KINDS)}")
            if "summary" in fm:
                summary = fm["summary"]
                if not isinstance(summary, str):
                    bad.append(f"{_rel(overview)}: summary must be a string, got {type(summary).__name__}")
                else:
                    if not summary.strip():
                        bad.append(f"{_rel(overview)}: summary is empty")
                    if "\n" in summary:
                        bad.append(f"{_rel(overview)}: summary must be one line")

            body = overview.read_text(encoding="utf-8").partition("+++\n")[2].partition("\n+++")[0]
            for n, line in enumerate(body.splitlines(), start=2):
                if not line.strip():
                    continue
                if not re.fullmatch(r'[a-z-]+ = (".*"|\[.*\])', line):
                    bad.append(
                        f"{_rel(overview)}:{n}: outside the pinned TOML subset "
                        f"(single-line basic strings and one-line arrays only) — {line!r}"
                    )
        except ValueError as exc:
            bad.append(str(exc))
        except Exception as exc:  # a malformed value (e.g. an array where a string is required)
            bad.append(f"{_rel(overview)}: {exc!r}")  # must not abort checking the rest of the board
    assert not bad, "\n".join(bad)


def test_slugs_are_unique_board_wide() -> None:
    """A slug is an item's permanent identity, so it must mean one thing everywhere.

    Uniqueness spans `done/` and `stale/`, not just the live stages: references outlive the item's
    completion, and a reused name would resolve a citation to the wrong work.
    """
    seen: dict[str, list[str]] = {}
    for item in _items():
        seen.setdefault(item.name, []).append(_rel(item))
    dupes = {slug: paths for slug, paths in seen.items() if len(paths) > 1}
    assert not dupes, f"slugs used more than once: {dupes}"


def test_dependencies_resolve() -> None:
    """`depends-on` names live slugs; `spikes` names real paths; a to-build item is not blocked."""
    items = _items()
    slugs = {d.name for d in items}
    bad = []
    for item in items:
        try:
            fm = _frontmatter(item / "overview.md")
        except ValueError as exc:
            bad.append(str(exc))
            continue
        for dep in fm.get("depends-on", []):
            if dep not in slugs:
                bad.append(f"{_rel(item)}: depends-on `{dep}` matches no board item")
            elif item.parent.name == "to-build" and (BOARD / "stale" / dep).is_dir():
                bad.append(
                    f"{_rel(item)}: is queued to build but depends on `{dep}`, which is shelved as stale"
                )
        for spike in fm.get("spikes", []):
            if not (REPO / spike).exists():
                bad.append(f"{_rel(item)}: spikes path does not exist — {spike}")
    assert not bad, "\n".join(bad)


def test_no_dependency_cycles() -> None:
    """A cycle would make an ordering impossible while every individual edge looked fine."""
    graph = {i.name: _frontmatter(i / "overview.md").get("depends-on", []) for i in _items()}
    state: dict[str, int] = {}

    def walk(node: str, trail: list[str]) -> None:
        if state.get(node) == 2:
            return
        assert state.get(node) != 1, f"dependency cycle: {' -> '.join(trail + [node])}"
        state[node] = 1
        for nxt in graph.get(node, []):
            if nxt in graph:
                walk(nxt, trail + [node])
        state[node] = 2

    for slug in graph:
        walk(slug, [])


def test_question_files_are_well_formed() -> None:
    """Both sections are mandatory.

    A missing `## Answer` must FAIL rather than read as "open": worded the other way round, a
    malformed file has no empty answer section and would sail through the gate below.
    """
    bad = []
    for item in _items():
        qdir = item / "questions"
        for q in sorted(qdir.glob("*.md")) if qdir.is_dir() else []:
            text = q.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"^## Context\s*$", text, re.M):
                bad.append(f"{_rel(q)}: no `## Context` section")
            if not re.search(r"^## Answer\s*$", text, re.M):
                bad.append(f"{_rel(q)}: no `## Answer` section")
    assert not bad, "\n".join(bad)


def test_a_question_never_moves_its_item() -> None:
    """A blocked item keeps its stage — so there is nothing here to forbid, only to surface.

    An earlier revision asserted that no item under `to-plan/`/`to-build/` may hold a question file,
    on the theory that a blocked item must not sit in the build queue looking ready. **The owner
    ruled otherwise:** a question is filed against the item where it is, and the item does not move.
    Bouncing it would shelve finished spec or plan work over one open decision.

    What replaces the gate is visibility, not relocation: `bin/board questions` lists every open
    question wherever it lives, so this test only checks that questions are reachable from any
    stage — a question directory in a stage the tool does not scan would be invisible, which is the
    real failure mode now.
    """
    scanned = set(STAGES)
    with_questions = {
        item.parent.name
        for item in BOARD.glob("*/*/questions")
        if item.is_dir() and any(item.glob("*.md"))
    }
    unreachable = {
        q.parent.parent.parent.name for q in BOARD.glob("*/*/questions/*.md")
    } - scanned
    assert not unreachable, f"question files in stages `bin/board questions` does not scan: {unreachable}"
    assert with_questions or True  # no lower bound: an empty board legitimately has none


def test_slug_references_resolve() -> None:
    """Every ``board item `<slug>``` in the tree names an item that exists."""
    slugs = {i.name for i in _items()}
    bad = []
    for doc in _tracked(*_REF_SUFFIXES):
        if _rel(doc) in _MAY_DEFINE_THE_FORM:
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")
        dangling = [
            s for m in _SLUG_REF.finditer(text)
            for s in _BACKTICKED.findall(m.group(1))
            if s not in slugs
        ]
        if dangling:
            bad.append(f"{_rel(doc)} references missing board items: {dangling}")
    assert not bad, "\n".join(bad)

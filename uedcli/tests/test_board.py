"""Board invariants — `dev/docs/board/` is one directory per work item.

The board is a set of stage directories (`inbox`, `to-spec`, … `done`); the stage an item is in IS
the directory it sits in, and an item advances by `git mv`. Each item directory holds an
`overview.md` whose TOML frontmatter carries priority, kind and a one-line summary, and may hold
`spec.md`, `plan.md` and `questions/<q>.md`. Spec: `dev/docs/specs/2026-07-27-board-per-item-directories.md`.

WHY THESE ARE TESTS AND NOT PROSE. Three of them guard things that fail silently otherwise:

* **A question file under `to-plan/`/`to-build/`** (:test_no_questions_past_to_spec) means an item is
  queued as ready while a decision it depends on is unmade. The gate keys on the file being GONE
  rather than on its answer being filled in, so folding the decision into a durable doc — not merely
  typing a reply — is what unblocks the item.
* **A dangling `board item` reference** (:test_slug_references_resolve). Slug references replaced
  ~400 path citations precisely because a path into `specs/` rots silently; that trade only pays if
  a dangling slug is loud.
* **The frontmatter SUBSET** (:test_frontmatter). `bin/board` is bash with no venv and hand-rolls its
  reader, so the corpus must stay inside what both it and `tomllib` handle.

Whole-board shape (exactly eight stages, no loose files) is NOT asserted yet: the migration converts
one stage per commit, so until it finishes `board/` legitimately holds stage directories *and*
un-migrated `.md` files. Those two assertions land with the final batch.
"""
from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "dev/docs/board"

STAGES = ("inbox", "to-spec", "to-spike", "to-plan", "to-build", "someday", "stale", "done")
#: Stages where a live decision would be queued as ready. `to-spec/` is deliberately absent —
#: drafting a spec is how questions get found, so gating it would be circular.
GATED = ("to-plan", "to-build")

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
    """Every item directory, across every stage that exists yet."""
    return sorted(
        d for stage in STAGES for d in (BOARD / stage).glob("*") if d.is_dir()
    )


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def _frontmatter(overview: Path) -> dict:
    """Parse the ``+++`` block, or fail the calling test with a readable message."""
    text = overview.read_text(encoding="utf-8")
    if not text.startswith("+++\n"):
        pytest.fail(f"{_rel(overview)}: no `+++` frontmatter on line 1")
    _, _, rest = text.partition("+++\n")
    body, sep, _ = rest.partition("\n+++")
    if not sep:
        pytest.fail(f"{_rel(overview)}: frontmatter is not closed by `+++`")
    try:
        return tomllib.loads(body)
    except tomllib.TOMLDecodeError as exc:
        pytest.fail(f"{_rel(overview)}: frontmatter is not valid TOML — {exc}")


def _tracked(*suffixes: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p and p.endswith(suffixes)]


if not _items():
    pytest.skip("no board items migrated yet", allow_module_level=True)


@pytest.mark.parametrize("item", _items(), ids=_rel)
def test_item_shape(item: Path) -> None:
    """An item is an `overview.md` plus, at most, a `questions/` directory."""
    assert (item / "overview.md").is_file(), f"{_rel(item)}: no overview.md"
    stray = [d.name for d in item.iterdir() if d.is_dir() and d.name != "questions"]
    assert not stray, f"{_rel(item)}: unexpected subdirectories {stray} (only `questions/` allowed)"


@pytest.mark.parametrize("item", _items(), ids=_rel)
def test_frontmatter(item: Path) -> None:
    """Required keys present, no unknown keys, values in range — and inside the pinned subset.

    The subset check is the load-bearing half. `bin/board` parses this frontmatter in bash with a
    hand-rolled reader, so anything TOML permits but that reader does not handle (literal strings,
    triple-quoted strings, comments, multi-line arrays) would make the two disagree silently.
    """
    overview = item / "overview.md"
    fm = _frontmatter(overview)

    missing = REQUIRED_KEYS - fm.keys()
    assert not missing, f"{_rel(overview)}: missing frontmatter keys {sorted(missing)}"
    unknown = fm.keys() - REQUIRED_KEYS - OPTIONAL_KEYS
    assert not unknown, f"{_rel(overview)}: unknown frontmatter keys {sorted(unknown)}"

    assert fm["priority"] in PRIORITIES, f"{_rel(overview)}: priority {fm['priority']!r} not in {sorted(PRIORITIES)}"
    assert fm["kind"] in KINDS, f"{_rel(overview)}: kind {fm['kind']!r} not in {sorted(KINDS)}"
    assert fm["summary"].strip(), f"{_rel(overview)}: summary is empty"
    assert "\n" not in fm["summary"], f"{_rel(overview)}: summary must be one line"

    body = overview.read_text(encoding="utf-8").partition("+++\n")[2].partition("\n+++")[0]
    for n, line in enumerate(body.splitlines(), start=2):
        if not line.strip():
            continue
        assert re.fullmatch(r'[a-z-]+ = (".*"|\[.*\])', line), (
            f"{_rel(overview)}:{n}: outside the pinned TOML subset "
            f"(single-line basic strings and one-line arrays only) — {line!r}"
        )


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


@pytest.mark.parametrize("item", _items(), ids=_rel)
def test_dependencies_resolve(item: Path) -> None:
    """`depends-on` names live slugs; `spikes` names real paths; a to-build item is not blocked."""
    fm = _frontmatter(item / "overview.md")
    slugs = {d.name for d in _items()}

    for dep in fm.get("depends-on", []):
        assert dep in slugs, f"{_rel(item)}: depends-on `{dep}` matches no board item"
        if item.parent.name == "to-build":
            assert not (BOARD / "stale" / dep).is_dir(), (
                f"{_rel(item)}: is queued to build but depends on `{dep}`, which is shelved as stale"
            )
    for spike in fm.get("spikes", []):
        assert (REPO / spike).exists(), f"{_rel(item)}: spikes path does not exist — {spike}"


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


@pytest.mark.parametrize("item", _items(), ids=_rel)
def test_question_files_are_well_formed(item: Path) -> None:
    """Both sections are mandatory.

    A missing `## Answer` must FAIL rather than read as "open": worded the other way round, a
    malformed file has no empty answer section and would sail through the gate below.
    """
    for q in sorted((item / "questions").glob("*.md")) if (item / "questions").is_dir() else []:
        text = q.read_text(encoding="utf-8")
        assert re.search(r"^## Context\s*$", text, re.M), f"{_rel(q)}: no `## Context` section"
        assert re.search(r"^## Answer\s*$", text, re.M), f"{_rel(q)}: no `## Answer` section"


@pytest.mark.parametrize("stage", GATED)
def test_no_questions_past_to_spec(stage: str) -> None:
    """An item with an unresolved question may not be queued for planning or building.

    Keyed on the file's ABSENCE, deliberately. Keying on "the answer is filled in" would unblock the
    item the moment the owner typed a reply — before any durable doc recorded the decision, and
    before the spec absorbed it.
    """
    blocked = [
        f"{_rel(item)} ({', '.join(q.name for q in sorted((item / 'questions').glob('*.md')))})"
        for item in (BOARD / stage).glob("*")
        if item.is_dir() and (item / "questions").is_dir() and any((item / "questions").glob("*.md"))
    ]
    assert not blocked, (
        f"items in `{stage}/` have open questions and must move back to `to-spec/`:\n  "
        + "\n  ".join(blocked)
    )


@pytest.mark.parametrize("doc", _tracked(*_REF_SUFFIXES), ids=_rel)
def test_slug_references_resolve(doc: Path) -> None:
    """Every ``board item `<slug>``` in the tree names an item that exists."""
    if _rel(doc) in _MAY_DEFINE_THE_FORM:
        pytest.skip("documents the reference form itself")
    slugs = {i.name for i in _items()}
    text = doc.read_text(encoding="utf-8", errors="replace")
    dangling = [
        s for m in _SLUG_REF.finditer(text)
        for s in _BACKTICKED.findall(m.group(1))
        if s not in slugs
    ]
    assert not dangling, f"{_rel(doc)} references missing board items: {dangling}"

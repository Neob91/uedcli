"""`bin/board` regressions, and the agreement test that keeps its bash TOML reader honest.

`bin/board` reads item frontmatter in bash and sources no venv, because `bin/_venv.sh` hard-fails
without python3.12 and that is far too heavy a dependency for a read-only board query. The cost of
that choice is a SECOND frontmatter parser. :test_bash_reader_agrees_with_tomllib is what stops the
two drifting: it runs the shipped reader and `tomllib` over every real `overview.md` plus a fixture
set covering each escape, and requires identical results.

Without it, the pinned-subset rule in `test_board.py` would be enforced on the corpus while nothing
checked that `bin/board` actually implements that subset the same way.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "dev/docs/board"
SCRIPT = REPO / "bin/board"

#: Values that broke a naive reader during design: an embedded quote (19 real board titles have
#: one), a backslash, both together, and the `p?` scalar.
ESCAPE_FIXTURES = [
    'plain text',
    'an embedded "quote" mid-sentence',
    'a backslash \\ alone',
    'both \\ and "quote"',
    'trailing backslash \\',
    'a colon: and a hash # inside',
    '`backticks` at the start',
]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, cwd=REPO)


def _bash_reads(overview: Path) -> dict[str, str]:
    """Scalar keys as the SHIPPED reader sees them, via `bin/board ls --json` over a temp board."""
    proc = subprocess.run(
        ["bash", "-c",
         f'source /dev/stdin <<"EOF"\n{_reader_shim()}\nEOF\nfm_dump "{overview}"'],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr
    pairs = (line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)
    # Arrays are emitted verbatim by the shipped reader (it unquotes basic strings only) and are
    # tagged with a sentinel so they can be told apart from a STRING that merely starts with `[`.
    # Filtering on a bare leading `[` — which this did — dropped every summary beginning with
    # `[OWNER — confirm]`, the exact marker `CLAUDE.md` mandates, and reported it as a missing key.
    # `depends-on`/`spikes` are checked against the tree by test_board.py via tomllib on both sides.
    return {k: v for k, v in pairs if not v.startswith("\001ARRAY\001")}


def _reader_shim() -> str:
    """The `fm` function lifted verbatim out of `bin/board`, plus a dumper.

    Lifted rather than reimplemented: a reimplementation would test the test, not the script.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("fm() {")
    end = text.index("fm_get()")
    return text[start:end] + "\nfm_dump() { fm \"$1\"; }\n"


def _overviews() -> list[Path]:
    return sorted(BOARD.glob("*/*/overview.md"))


@pytest.mark.parametrize("overview", _overviews() or [None], ids=lambda p: str(p) if p else "none")
def test_bash_reader_agrees_with_tomllib(overview: Path | None) -> None:
    """Every real item parses identically in bash and in `tomllib`."""
    if overview is None:
        pytest.skip("no board items migrated yet")
    body = overview.read_text(encoding="utf-8").partition("+++\n")[2].partition("\n+++")[0]
    expected = {k: v for k, v in tomllib.loads(body).items() if isinstance(v, str)}
    assert _bash_reads(overview) == expected


@pytest.mark.parametrize("summary", ESCAPE_FIXTURES)
def test_escapes_round_trip(tmp_path: Path, summary: str) -> None:
    """A summary written by `new` survives both readers unchanged.

    This is the case that matters at capture time: 19 board titles contain a `"`, so a reader that
    handled only unescaped text would corrupt the first item anyone filed.
    """
    escaped = summary.replace("\\", "\\\\").replace('"', '\\"')
    overview = tmp_path / "overview.md"
    overview.write_text(
        f'+++\npriority = "p?"\nkind = "unknown"\nsummary = "{escaped}"\n+++\n\n# t\n',
        encoding="utf-8",
    )
    body = overview.read_text(encoding="utf-8").partition("+++\n")[2].partition("\n+++")[0]
    assert tomllib.loads(body)["summary"] == summary
    assert _bash_reads(overview)["summary"] == summary


def test_new_creates_an_item_that_passes_the_board_test(tmp_path: Path) -> None:
    """`new` must leave the board GREEN.

    It is the sanctioned path for logging a review finding, so a stub that fails `test_board.py`
    would redden the suite on the first use — during a gate, for everyone.
    """
    title = 'A finding about "quoted" text'
    proc = _run("new", "inbox", title)
    assert proc.returncode == 0, proc.stderr
    created = REPO / proc.stdout.strip()
    try:
        body = (created / "overview.md").read_text(encoding="utf-8")
        fm = tomllib.loads(body.partition("+++\n")[2].partition("\n+++")[0])
        assert fm == {"priority": "p?", "kind": "unknown", "summary": title}
        assert created.name and not created.name.endswith("-")
    finally:
        for f in created.rglob("*"):
            f.unlink()
        created.rmdir()


def test_new_refuses_a_slug_already_used_in_another_stage(tmp_path: Path) -> None:
    """Slug uniqueness is board-wide, so the guard must be too.

    `mkdir` without `-p` only loses a same-stage race; a cross-stage duplicate would slip past it
    and redden `test_board.py` for whoever ran next.
    """
    first = _run("new", "inbox", "Cross stage slug guard probe")
    assert first.returncode == 0, first.stderr
    created = REPO / first.stdout.strip()
    try:
        second = _run("new", "to-spec", "Cross stage slug guard probe")
        assert second.returncode == 2
        assert "already in use" in second.stderr
    finally:
        for f in created.rglob("*"):
            f.unlink()
        created.rmdir()


def _question_item(stage: str, slug: str, answer_body: str, extra: str = "") -> Path:
    d = BOARD / stage / slug
    (d / "questions").mkdir(parents=True)
    (d / "overview.md").write_text(
        f'+++\npriority = "p?"\nkind = "unknown"\nsummary = "probe"\n+++\n\n# {slug}\n', encoding="utf-8")
    (d / "questions" / "q.md").write_text(
        f"# Q\n\n## Context\n\nc\n\n## Answer\n{answer_body}{extra}", encoding="utf-8")
    return d


def _rmtree(d: Path) -> None:
    for f in sorted(d.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    d.rmdir()


@pytest.mark.parametrize(
    "answer_body, extra, expect_open",
    [
        ("\n<!-- Empty = open. -->\n", "", True),
        ("\n<!-- Empty = open. -->\n", "\n## Notes\n\ntrailing prose\n", True),
        ("\n   \n", "", True),
        ("\nOption B.\n", "", False),
        ("\nTBD\n", "", False),
    ],
    ids=["empty", "empty-then-section", "whitespace", "answered", "placeholder-counts"],
)
def test_open_vs_answered(answer_body: str, extra: str, expect_open: bool) -> None:
    """A question is OPEN until its `## Answer` holds real text — and stays open past a later section.

    The `empty-then-section` case is the regression that matters. `awk` here is mawk, which has no
    ERE intervals, so a `/^#{1,2} /` terminator matched only the LITERAL text and the answer section
    ran to EOF: an unanswered blocker was reported as answered, vanished from `bin/board questions`,
    and `CLAUDE.md` tells an agent to fold answered questions out and DELETE them. A live decision
    would have been destroyed by following the documented process.
    """
    d = _question_item("inbox", "zz-answerstate-probe", answer_body, extra)
    try:
        assert ("zz-answerstate-probe" in _run("questions").stdout) is expect_open
        assert ("zz-answerstate-probe" in _run("answered").stdout) is not expect_open
    finally:
        _rmtree(d)


def test_a_reopened_question_leaves_the_fold_out_queue() -> None:
    """An owner reply that is itself a question must not sit in the agent's fold-out queue."""
    d = _question_item("inbox", "zz-reopened-probe", "\nWhy?\n", "\n## Reopened\n\nagent reply\n")
    try:
        assert "zz-reopened-probe" not in _run("answered").stdout
    finally:
        _rmtree(d)


def test_show_resolves_a_real_slug() -> None:
    """Only `show`'s failure path was tested, so it could have returned the wrong stage unnoticed.

    The expected stage is read off the filesystem rather than written in: an item advances by
    `git mv`, so pinning the stage here would redden the suite every time this item moved, which
    is exactly the churn the slug-not-path convention exists to avoid.
    """
    slug = "unified-asset-catalog"
    stage = next(d.parent.name for d in (REPO / "dev/docs/board").glob(f"*/{slug}") if d.is_dir())
    proc = _run("show", slug)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == f"dev/docs/board/{stage}/{slug}"


def test_ls_filters_by_stage() -> None:
    out = _run("ls", "to-spike").stdout
    assert out.strip() and all(" to-spike " in ln for ln in out.splitlines())


def test_ls_rejects_two_stages() -> None:
    """Taking only the last of several silently dropped the others and exited 0."""
    proc = _run("ls", "to-spike", "to-build")
    assert proc.returncode == 2 and "to-spike" in proc.stderr


def test_ls_json_on_an_empty_stage_is_an_empty_array(tmp_path: Path) -> None:
    """A queue drains, and a consumer must then get `[]` — not empty stdout it cannot parse.

    Run over a TEMP board rather than a real stage. This used to point at `stale/` on the premise
    that it is empty, which is not a property the board guarantees: `stale/` exists to HOLD items
    ("judged stale, retained not deleted"), and the 2026-08-02 sweep duly put one there, reddening
    the suite for weeks. Any real stage can be filled by unrelated work, so none of them can carry
    this assertion. `bin/board` resolves its board dir from its own location, so a copy of the
    shipped script beside an empty tree gives a genuinely empty stage with no mocking.
    """
    board = tmp_path / "dev" / "docs" / "board"
    for stage in ("inbox", "to-spec", "to-spike", "to-plan", "to-build", "someday", "stale", "done"):
        (board / stage).mkdir(parents=True)
    (tmp_path / "bin").mkdir()
    shutil.copy2(SCRIPT, tmp_path / "bin" / "board")

    proc = subprocess.run(["bash", str(tmp_path / "bin" / "board"), "ls", "stale", "--json"],
                          capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == []


def test_an_unclosed_frontmatter_is_malformed_not_parsed_to_eof() -> None:
    """The real half-written shape. Parsed to EOF, body prose becomes frontmatter keys."""
    d = BOARD / "inbox" / "zz-unclosed-probe"
    d.mkdir(parents=True)
    try:
        (d / "overview.md").write_text('+++\npriority = "p1"\nsummary = "half written\n', encoding="utf-8")
        proc = _run("ls")
        assert proc.returncode == 0
        assert "zz-unclosed-probe" in proc.stderr and "zz-unclosed-probe" not in proc.stdout
    finally:
        _rmtree(d)


def test_unknown_stage_exits_2_naming_the_value() -> None:
    proc = _run("new", "not-a-stage", "x")
    assert proc.returncode == 2
    assert "not-a-stage" in proc.stderr


def test_unknown_slug_exits_2_naming_the_value() -> None:
    proc = _run("show", "no-such-item-anywhere")
    assert proc.returncode == 2
    assert "no-such-item-anywhere" in proc.stderr


def test_ls_json_is_valid_json() -> None:
    """`ls --json` is the triage scan an agent consumes, over summaries full of quotes."""
    proc = _run("ls", "--json")
    assert proc.returncode == 0, proc.stderr
    if proc.stdout.strip():
        json.loads(proc.stdout)


def test_a_malformed_item_is_skipped_not_fatal() -> None:
    """One half-written item must not break a query about a different one.

    Several sessions share this checkout, so an item mid-write is a normal state, not corruption.
    """
    broken = BOARD / "inbox" / "zz-malformed-probe"
    broken.mkdir(parents=True)
    try:
        (broken / "overview.md").write_text("no frontmatter here\n", encoding="utf-8")
        proc = _run("ls")
        assert proc.returncode == 0, proc.stderr
        assert "zz-malformed-probe" in proc.stderr
    finally:
        (broken / "overview.md").unlink()
        broken.rmdir()

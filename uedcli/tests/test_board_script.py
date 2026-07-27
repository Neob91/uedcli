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
    return dict(
        line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line
    )


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

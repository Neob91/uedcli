"""`uedcli docs list|show|search` — serving uedcli's own USER-facing documentation from the tool.

The command exists so a consumer (a person at a terminal, or a shipped Claude skill) reads the
docs baked into the binary it has instead of carrying a copy that drifts. Three properties are
load-bearing and every one of them is pinned here:

1. **The developer tree never leaks.** `dev/docs/**` is written for uedcli developers; a uedcli
   *user* cannot open those files and must not be sent to them.
2. **`show` cannot be talked into reading an arbitrary file.** It resolves a request by looking a
   TOPIC KEY up in the enumerated served set — there is no path join for `../`, an absolute path
   or a directory name to slip through.
3. **No Python exception ever reaches the user.** Every bad topic, unresolvable docs root and
   ambiguous served set is a clean message naming the offending value at exit 2.

Most tests run against a small synthetic docs tree (the `docs_dir` fixture) so they pin behaviour
rather than the current contents of the real `docs/`; the handful that must see the real tree say
so in their names.
"""
from __future__ import annotations

import importlib.resources
import io
import json
import os
from pathlib import Path

import pytest

from uedcli import cli, userdocs


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def docs_dir(tmp_path, monkeypatch) -> Path:
    """A synthetic docs tree, pointed at by `$UEDCLI_DOCS_DIR`.

    It deliberately contains one of every shape the enumeration has to handle: a root README (folds
    to `index`), a directory README (folds to the directory), a directory WITHOUT a README (so it
    is not addressable at all), a page with no `# ` heading, an empty page, the same basename in
    two directories (so a bare stem cannot resolve), a non-markdown file, and a top-level `dev/`
    subtree that must never be served.
    """
    root = tmp_path / "docs"
    _write(root, "README.md", "# uedcli docs\nthe landing page\n")
    _write(root, "usage.md", "# Usage\nlighting is configured per zone\nsecond lighting line\n")
    _write(root, "guide/README.md", "# Guide overview\ntalks about lighting once\n")
    _write(root, "guide/lighting.md", "# Lighting\nlamps, torches and lighting rigs\n")
    _write(root, "guide/human-scale.md", "# Human scale (guide)\ndoor 96uu\n")
    _write(root, "other/human-scale.md", "# Human scale (other)\ndoor 96uu\n")
    _write(root, "plain/leaf.md", "no heading in this one at all\n")
    _write(root, "empty.md", "")
    _write(root, "notes.txt", "not a doc\n")
    _write(root, "dev/architecture.md", "# Developer architecture\nsecret internals\n")
    _write(root, "dev/nested/deep.md", "# Deeper developer note\n")
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(root))
    return root


def _run(argv: list[str]) -> int:
    return cli.main(argv)


# ------------------------------------------------------------------------------ topic keys / list
def test_list_prints_every_topic_key_on_stdout_and_the_count_on_stderr(docs_dir, capsys):
    rc = _run(["docs", "list"])
    out = capsys.readouterr()
    assert rc == 0
    keys = out.out.split()
    assert keys == ["empty", "guide", "guide/human-scale", "guide/lighting", "index",
                    "other/human-scale", "plain/leaf", "usage"]
    assert keys == sorted(keys)                     # lexicographic by key
    assert out.err.strip() == "8 topic(s)"           # the human count never pollutes the pipe


def test_list_never_serves_the_developer_tree(docs_dir, capsys):
    """`dev/` at the TOP LEVEL of the docs root is not a served subtree, at any depth below it."""
    _run(["docs", "list"])
    out = capsys.readouterr().out
    assert "dev/" not in out and "architecture" not in out and "deep" not in out


def test_the_developer_tree_is_excluded_whatever_its_case(tmp_path, monkeypatch, capsys):
    """The prune is case-INSENSITIVE, like every other comparison in the module. On a
    case-insensitive filesystem (Windows/macOS — the Nuitka ship target) `DEV` and `dev` are one
    directory, and this is the module's one security-relevant filter."""
    root = tmp_path / "docs"
    _write(root, "usage.md", "# Usage\n")
    _write(root, "DEV/architecture.md", "# Developer architecture\nsecret internals\n")
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(root))
    assert _run(["docs", "list"]) == 0
    assert capsys.readouterr().out.split() == ["usage"]
    assert _run(["docs", "show", "DEV/architecture"]) == 2
    assert "Doc not found" in capsys.readouterr().err


def test_a_dev_named_directory_deeper_in_the_tree_is_still_served(docs_dir, capsys):
    """The exclusion is anchored at the root, not "any path segment called dev" — otherwise a
    legitimate `guide/dev/...` page would silently vanish."""
    _write(docs_dir, "guide/dev/tooling.md", "# Tooling\n")
    _run(["docs", "list"])
    assert "guide/dev/tooling" in capsys.readouterr().out.split()


def test_list_folds_readmes_and_exposes_no_readme_key(docs_dir, capsys):
    _run(["docs", "list"])
    keys = capsys.readouterr().out.split()
    assert "guide" in keys and "index" in keys
    assert not [k for k in keys if k.lower().endswith("readme")]


def test_list_json_carries_the_topic_key_and_title(docs_dir, capsys):
    rc = _run(["docs", "list", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert {r["path"] for r in rows} >= {"index", "guide", "usage"}
    assert all(set(r) == {"path", "title"} for r in rows)
    assert {r["path"]: r["title"] for r in rows}["guide"] == "Guide overview"


def test_a_headingless_page_titles_from_its_key_and_a_folded_readme_from_its_directory(
        docs_dir, capsys):
    """A title falls back to the key's last segment — the DIRECTORY name for a folded README (never
    the useless literal `README`) and the file basename for a leaf."""
    _write(docs_dir, "bare/README.md", "no heading here\n")
    _run(["docs", "list", "--json"])
    titles = {r["path"]: r["title"] for r in json.loads(capsys.readouterr().out)}
    assert titles["bare"] == "bare"
    assert titles["plain/leaf"] == "plain/leaf".rsplit("/", 1)[-1]
    assert "README" not in titles.values()


# ------------------------------------------------------------------------------------------ show
def test_show_prints_the_page_verbatim_with_or_without_the_md_suffix(docs_dir, capsysbinary):
    raw = (docs_dir / "guide" / "lighting.md").read_bytes()
    assert _run(["docs", "show", "guide/lighting"]) == 0
    first = capsysbinary.readouterr()
    assert _run(["docs", "show", "guide/lighting.md"]) == 0
    second = capsysbinary.readouterr()
    assert first.out == raw == second.out
    assert first.err == b""                      # nothing on stderr on success


def test_show_is_byte_exact_for_non_ascii_text(docs_dir, capsysbinary):
    """The docs carry UTF-8 typography (`°×≡…`); `show` copies bytes rather than re-encoding them
    through the terminal locale, which would corrupt them under a non-UTF-8 locale."""
    body = "# Units\n90° × 2 ≡ a turn…\n"
    _write(docs_dir, "units.md", body)
    assert _run(["docs", "show", "units"]) == 0
    assert capsysbinary.readouterr().out == body.encode("utf-8")


def test_show_resolves_case_insensitively(docs_dir, capsysbinary):
    assert _run(["docs", "show", "GUIDE/Lighting"]) == 0
    assert capsysbinary.readouterr().out == (docs_dir / "guide" / "lighting.md").read_bytes()


def test_show_serves_a_directory_readme_under_the_directory_key(docs_dir, capsysbinary):
    assert _run(["docs", "show", "guide"]) == 0
    assert capsysbinary.readouterr().out == (docs_dir / "guide" / "README.md").read_bytes()


def test_show_serves_the_root_readme_as_index(docs_dir, capsysbinary):
    assert _run(["docs", "show", "index"]) == 0
    assert capsysbinary.readouterr().out == (docs_dir / "README.md").read_bytes()


def test_show_an_empty_page_prints_nothing_and_succeeds(docs_dir, capsysbinary):
    assert _run(["docs", "show", "empty"]) == 0
    assert capsysbinary.readouterr().out == b""


def test_a_bare_basename_never_resolves_and_the_hint_lists_every_candidate(docs_dir, capsys):
    """Two pages end in `human-scale`. Quietly picking one would be a wrong answer that looks
    right, so the bare stem is a miss whose hint names both."""
    rc = _run(["docs", "show", "human-scale"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "Doc not found: human-scale" in err
    assert "guide/human-scale" in err and "other/human-scale" in err
    assert "Traceback" not in err


def test_the_old_readme_address_is_redirected_to_the_directory_key(docs_dir, capsys):
    rc = _run(["docs", "show", "guide/README"])
    err = capsys.readouterr().err
    assert rc == 2 and "did you mean: guide" in err


@pytest.mark.parametrize("topic", [
    "../../pyproject.toml",     # traversal out of the docs root
    "/etc/passwd",              # an absolute path
    "..",                       # the parent directory
    "dev/architecture",         # the developer tree
    "dev/nested/deep",          # deeper in the developer tree
    "guide/../usage",           # traversal that lands back inside the root
    "notes.txt",                # a served-root file that is not markdown
    "plain",                    # a directory with no README — not a topic
    "",                         # the empty string
])
def test_show_refuses_anything_outside_the_served_set(docs_dir, topic, capsysbinary):
    """`show` looks a key up in the enumerated served set; it never joins user text onto a path.
    So every one of these is an ordinary "not found", with nothing written to stdout."""
    rc = _run(["docs", "show", topic])
    out = capsysbinary.readouterr()
    assert rc == 2
    assert out.out == b""
    assert b"Doc not found" in out.err and b"Traceback" not in out.err
    # …and the message NAMES the offending value (quoted when it is blank, so it stays visible).
    named = topic if topic.strip() else repr(topic)
    assert named.encode() in out.err


@pytest.mark.parametrize("topic", ["", "   "])
def test_an_empty_topic_is_refused_by_NAME(docs_dir, topic, capsys):
    """The house rule is that an error names the offending value. `Doc not found:` followed by
    nothing names nothing — a reader cannot tell an empty argument from a formatting bug."""
    rc = _run(["docs", "show", topic])
    err = capsys.readouterr().err
    assert rc == 2
    assert repr(topic) in err                      # the value itself, quoted so blanks are visible
    assert "cannot be empty" in err and "Traceback" not in err


def test_show_refuses_a_page_reached_only_through_a_symlink_out_of_the_root(docs_dir, capsys):
    """A symlink is not a way around the served set: the target resolves outside the docs root, so
    the file is not enumerated and its key does not exist."""
    outside = docs_dir.parent / "outside.md"
    outside.write_text("# Outside\nnot for users\n", encoding="utf-8")
    (docs_dir / "sneak.md").symlink_to(outside)
    assert _run(["docs", "list"]) == 0
    assert "sneak" not in capsys.readouterr().out.split()
    assert _run(["docs", "show", "sneak"]) == 2
    assert "Doc not found: sneak" in capsys.readouterr().err


def test_show_refuses_a_symlink_into_the_developer_tree(docs_dir, capsys):
    (docs_dir / "leak.md").symlink_to(docs_dir / "dev" / "architecture.md")
    assert _run(["docs", "list"]) == 0
    assert "leak" not in capsys.readouterr().out.split()
    assert _run(["docs", "show", "leak"]) == 2
    assert "Doc not found: leak" in capsys.readouterr().err


# ------------------------------------------------------------------------------------- `show -`
def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_show_dash_prints_every_page_with_a_marker_naming_it(docs_dir, capsysbinary, monkeypatch):
    _stdin(monkeypatch, "guide/lighting\nindex\n")
    rc = _run(["docs", "show", "-"])
    out = capsysbinary.readouterr().out
    assert rc == 0
    assert out == (b"<!-- topic: guide/lighting -->\n"
                   + (docs_dir / "guide" / "lighting.md").read_bytes()
                   + b"<!-- topic: index -->\n"
                   + (docs_dir / "README.md").read_bytes())


def test_show_dash_keeps_a_marker_on_its_own_line_after_a_page_with_no_final_newline(
        docs_dir, capsysbinary, monkeypatch):
    _write(docs_dir, "nonl.md", "# No final newline\nlast line")
    _stdin(monkeypatch, "nonl\nindex\n")
    assert _run(["docs", "show", "-"]) == 0
    out = capsysbinary.readouterr().out
    assert b"last line\n<!-- topic: index -->\n" in out


def test_show_dash_is_atomic_one_bad_key_prints_nothing(docs_dir, capsysbinary, monkeypatch):
    """A partial dump plus a stderr warning would be taken for the complete answer once the
    warning scrolls away — so an unresolvable key means nothing at all on stdout."""
    _stdin(monkeypatch, "index\nnope\nguide\nalso-nope\n")
    rc = _run(["docs", "show", "-"])
    out = capsysbinary.readouterr()
    assert rc == 2
    assert out.out == b""
    assert b"Docs not found: nope, also-nope" in out.err
    assert b"Traceback" not in out.err


def test_show_dash_strips_a_leading_utf8_bom(docs_dir, capsysbinary, monkeypatch):
    """A BOM is not whitespace, so `str.strip` leaves it on the first key and the key stops
    resolving. Because this form is atomic, one BOM'd first line took the whole invocation down.
    `docs show -` reads through `dispatch._names_from_stdin`, the CLI's one newline-list reader,
    which already handles this for every sibling verb."""
    _stdin(monkeypatch, "﻿index\nguide\n")
    assert _run(["docs", "show", "-"]) == 0
    out = capsysbinary.readouterr().out
    assert out.startswith(b"<!-- topic: index -->\n")
    assert b"<!-- topic: guide -->\n" in out


def test_show_dash_writes_nothing_when_a_page_becomes_unreadable_after_resolution(
        docs_dir, capsysbinary, monkeypatch):
    """Atomicity covers READING, not just resolution: every page is in hand before a byte reaches
    stdout, so a file that disappears between enumeration and output cannot leave a partial dump
    behind. (Only a race reaches this in practice — enumeration has already read every file.)"""
    real_bytes = Path.read_bytes
    reads = {"n": 0}                        # `lighting.md` is unique in the fixture tree

    def explode(self):
        if self.name == "lighting.md":
            reads["n"] += 1
            if reads["n"] > 1:              # 1st read is enumeration; the 2nd is `show` itself
                raise PermissionError(13, "Permission denied")
        return real_bytes(self)

    _stdin(monkeypatch, "index\nguide/lighting\n")
    monkeypatch.setattr(Path, "read_bytes", explode)
    rc = _run(["docs", "show", "-"])
    out = capsysbinary.readouterr()
    assert rc == 2
    assert out.out == b""                   # not even the first page, which read fine
    assert b"cannot read doc guide/lighting" in out.err and b"Traceback" not in out.err


def test_show_dash_on_empty_stdin_is_a_clean_no_op(docs_dir, capsysbinary, monkeypatch):
    _stdin(monkeypatch, "")
    assert _run(["docs", "show", "-"]) == 0
    assert capsysbinary.readouterr().out == b""


def test_show_dash_ignores_blank_lines(docs_dir, capsysbinary, monkeypatch):
    _stdin(monkeypatch, "\n  \nindex\n\n")
    assert _run(["docs", "show", "-"]) == 0
    assert capsysbinary.readouterr().out.endswith((docs_dir / "README.md").read_bytes())


# ----------------------------------------------------------------------------------------- search
def test_search_prints_topic_keys_that_show_can_take(docs_dir, capsys):
    rc = _run(["docs", "search", "lighting"])
    out = capsys.readouterr()
    assert rc == 0
    keys = out.out.split()
    assert keys[0] == "guide/lighting"                       # a title match outranks a mention
    assert "guide" in keys                                   # a README hit prints the FOLDED key
    assert out.err.strip() == f"{len(keys)} match(es)"


def test_a_search_result_feeds_straight_into_show(docs_dir, capsysbinary, monkeypatch):
    _run(["docs", "search", "lighting"])
    keys = capsysbinary.readouterr().out.decode().split()
    _stdin(monkeypatch, "\n".join(keys))
    assert _run(["docs", "show", "-"]) == 0
    assert capsysbinary.readouterr().out.count(b"<!-- topic: ") == len(keys)


def test_search_is_case_insensitive_and_scores_a_title_above_body_mentions(docs_dir, capsys):
    _write(docs_dir, "mentions.md", "# Unrelated\n" + "lighting\n" * 9)
    _run(["docs", "search", "LIGHTING"])
    keys = capsys.readouterr().out.split()
    assert keys.index("guide/lighting") < keys.index("mentions")


def test_search_json_carries_key_title_and_a_bounded_snippet(docs_dir, capsys):
    _write(docs_dir, "long.md", "# Long\n" + "x" * 300 + "lighting" + "y" * 300 + "\n")
    rc = _run(["docs", "search", "lighting", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert all(set(r) == {"path", "title", "snippet"} for r in rows)
    assert all(len(r["snippet"]) <= userdocs.SNIPPET_MAX for r in rows)
    assert {r["path"] for r in rows} >= {"guide/lighting", "long"}


def test_a_snippet_is_a_body_line_never_the_pages_own_heading(docs_dir, capsys):
    """The page's heading IS the title, so it is not also a body line. Otherwise a title match
    reports a snippet that just repeats the title with a leading `#` — useless as evidence."""
    _write(docs_dir, "topic.md", "# Lighting rigs\nfirst real body line about lighting\n")
    _run(["docs", "search", "lighting", "--json"])
    row = {r["path"]: r for r in json.loads(capsys.readouterr().out)}["topic"]
    assert row["title"] == "Lighting rigs"
    assert row["snippet"] == "first real body line about lighting"
    assert not row["snippet"].startswith("#") and row["snippet"] != row["title"]


def test_a_title_only_match_scores_ten_with_no_body_line_double_count(docs_dir):
    """The title and the body are counted separately and never both from the same line."""
    _write(docs_dir, "titleonly.md", "# Ventilation\nnothing else mentions it\n")
    docs = userdocs.load_docs(docs_dir)
    hit = next(h for h in userdocs.search(docs, "ventilation") if h.doc.key == "titleonly")
    assert hit.score == 10 and hit.snippet == ""


def test_search_with_no_hits_is_an_empty_success(docs_dir, capsys):
    rc = _run(["docs", "search", "zzzz-nothing-matches-this"])
    out = capsys.readouterr()
    assert rc == 0
    assert out.out == ""
    assert out.err.strip() == "0 match(es)"


def test_search_refuses_an_empty_query(docs_dir, capsys):
    """A blank substring sits inside every line of every page, so it would "match" the whole corpus
    in score order — a meaningless answer rather than an empty one."""
    rc = _run(["docs", "search", "   "])
    err = capsys.readouterr().err
    assert rc == 2 and "must not be empty" in err and "Traceback" not in err


# ------------------------------------------------------------------------ duplicate topic keys
@pytest.mark.parametrize("files, key", [
    ({"thing/README.md": "# A", "thing.md": "# B"}, "thing"),           # a README vs its sibling
    ({"index.md": "# A", "README.md": "# B"}, "index"),                 # vs the reserved root key
    ({"Thing/README.md": "# A", "thing.md": "# B"}, "thing"),           # differing only in case
])
def test_two_files_claiming_one_topic_key_fail_every_docs_invocation(
        tmp_path, monkeypatch, capsys, files, key):
    """An ambiguous served set cannot be trusted, so it is a hard error naming both files rather
    than a silent precedence rule. Because it fails ENUMERATION it trips `docs list` itself (and
    the test suite), so it is caught while authoring — a shipped binary can never carry one."""
    root = tmp_path / "docs"
    for rel, text in files.items():
        _write(root, rel, text)
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(root))
    rc = _run(["docs", "list"])
    err = capsys.readouterr().err
    assert rc == 2
    assert key in err and all(Path(rel).name in err for rel in files)
    assert "Traceback" not in err


def test_the_real_docs_tree_has_no_duplicate_topic_keys(monkeypatch):
    """The standing authoring gate: adding a `X.md` beside an existing `X/README.md` turns every
    `uedcli docs` invocation into an error, so the suite has to catch it first.

    **The `load_docs()` call below IS the assertion** — a duplicate key raises `_SelectionExit`
    from inside it, before any list comes back. The comparison after it can therefore never fail;
    it is kept only so the property being guarded is written down next to the call that guards it.
    """
    monkeypatch.delenv("UEDCLI_DOCS_DIR", raising=False)
    docs = userdocs.load_docs()                     # ← raises on a duplicate key; this is the gate
    keys = [d.key for d in docs]
    assert keys, "the shipped docs tree must serve at least one page"
    assert len(keys) == len({k.casefold() for k in keys})   # restatement, not an independent check


# ------------------------------------------------------------------------------- the docs root
def _fake_package(monkeypatch, pkg: Path) -> None:
    """Make `importlib.resources.files("uedcli")` answer with `pkg`, so the resolver's source-tree
    and bundled branches can be exercised against a synthetic layout."""
    real = importlib.resources.files
    monkeypatch.setattr(importlib.resources, "files",
                        lambda name: pkg if name == "uedcli" else real(name))


def test_the_env_override_wins_over_the_source_tree(tmp_path, monkeypatch):
    override = tmp_path / "elsewhere"
    override.mkdir()
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(override))
    assert userdocs.docs_root() == override


def test_the_source_tree_wins_over_a_bundled_copy(tmp_path, monkeypatch):
    """Source-first on purpose: a stale `_docs/` left behind by an experimental local build must
    never shadow the `docs/` tree a developer is editing."""
    monkeypatch.delenv("UEDCLI_DOCS_DIR", raising=False)
    pkg = tmp_path / "uedcli"
    (pkg / "_docs").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    _fake_package(monkeypatch, pkg)
    assert userdocs.docs_root() == tmp_path / "docs"


def test_the_bundled_copy_answers_when_there_is_no_source_tree(tmp_path, monkeypatch):
    monkeypatch.delenv("UEDCLI_DOCS_DIR", raising=False)
    pkg = tmp_path / "uedcli"
    (pkg / "_docs").mkdir(parents=True)
    _fake_package(monkeypatch, pkg)
    assert userdocs.docs_root() == pkg / "_docs"


def test_an_install_with_no_docs_at_all_is_a_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("UEDCLI_DOCS_DIR", raising=False)
    pkg = tmp_path / "uedcli"
    pkg.mkdir()
    _fake_package(monkeypatch, pkg)
    rc = _run(["docs", "list"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "docs unavailable" in err and "Traceback" not in err


def test_a_readable_docs_root_that_serves_nothing_is_a_clean_error(tmp_path, monkeypatch, capsys):
    """The third shape of "broken root", after nonexistent and unreadable: the directory is there
    and readable but holds no pages. uedcli always ships documentation, so this is a broken build
    or a wrong override — and `0 topic(s)` at exit 0 would say "this build has no docs" in exactly
    the words it would use if that were true, without naming where it looked."""
    root = tmp_path / "docs"
    (root / "dev").mkdir(parents=True)             # a dev/ tree alone still serves nothing
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(root))
    rc = _run(["docs", "list"])
    out = capsys.readouterr()
    assert rc == 2
    assert out.out == ""
    assert "no documentation pages under" in out.err and str(root) in out.err
    assert "Traceback" not in out.err


def test_a_closed_stdout_pipe_is_a_silent_success(docs_dir, monkeypatch):
    """`uedcli docs list | head` — the consumer goes away mid-write. The conventional Unix
    behaviour is a silent exit 0, not an error; `dispatch()`'s global BrokenPipeError handler
    supplies it, and this pins that `docs` rides it."""
    class _ClosedPipe(io.StringIO):
        def write(self, _s):
            raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr("sys.stdout", _ClosedPipe())
    assert _run(["docs", "list"]) == 0


def test_a_docs_dir_override_that_does_not_exist_names_itself(tmp_path, monkeypatch, capsys):
    """Not a silently empty listing: an empty served set would read as "this build has no docs"
    rather than "your override is wrong"."""
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(tmp_path / "nope"))
    rc = _run(["docs", "list"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "UEDCLI_DOCS_DIR is not a directory" in err and "nope" in err
    assert "Traceback" not in err


# ------------------------------------------------------- an unreadable directory is never silent
#
# `pathlib`'s glob swallows the `OSError` from `scandir`, so a directory the process cannot read
# reads back as "this directory is empty". Left unhandled, an unreadable ROOT makes `docs list`
# print nothing at exit 0, and an unreadable SUBdirectory silently drops its pages from `list`,
# `search` AND `show` — a partial answer with no signal at all. Root-owned trees left behind by
# container runs make this a live failure mode in this repo, not a hypothetical one.

_ROOT_USER = os.geteuid() == 0 if hasattr(os, "geteuid") else False


@pytest.fixture
def unreadable():
    """`chmod 000` a directory for the duration of one test, always restoring it afterwards.

    The restore is not optional: pytest reuses and later deletes its tmp directories, and a 000
    directory left behind breaks that cleanup on a subsequent run.
    """
    touched: list[Path] = []

    def make(path: Path) -> Path:
        path.chmod(0o000)
        touched.append(path)
        return path

    yield make
    for path in touched:
        path.chmod(0o755)


@pytest.mark.skipif(_ROOT_USER, reason="root bypasses directory permissions, so 000 is readable")
def test_a_docs_root_that_exists_but_cannot_be_read_is_a_clean_error(
        tmp_path, monkeypatch, capsys, unreadable):
    """Spec §9's "broken root" case that a nonexistent path does not cover: the root is there and
    is a directory, so `docs_root()` accepts it — the failure surfaces in the walk."""
    root = tmp_path / "docs"
    _write(root, "a.md", "# A\n")
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(root))
    unreadable(root)
    rc = _run(["docs", "list"])
    out = capsys.readouterr()
    assert rc == 2                              # NOT an empty listing at exit 0
    assert out.out == ""
    assert "cannot read docs directory" in out.err and str(root) in out.err
    assert "Traceback" not in out.err
    assert _run(["docs", "show", "a"]) == 2      # and `show` says the same, not "Doc not found"
    assert "cannot read docs directory" in capsys.readouterr().err


@pytest.mark.skipif(_ROOT_USER, reason="root bypasses directory permissions, so 000 is readable")
def test_one_unreadable_subdirectory_fails_the_whole_listing_rather_than_dropping_it(
        tmp_path, monkeypatch, capsys, unreadable):
    """The partial-answer case, which is the more dangerous of the two: the surviving pages would
    otherwise list normally and nothing would say that a subtree was missing."""
    root = tmp_path / "docs"
    _write(root, "top.md", "# Top\n")
    _write(root, "sub/s.md", "# S\n")
    _write(root, "hidden/h.md", "# H\n")
    monkeypatch.setenv("UEDCLI_DOCS_DIR", str(root))
    unreadable(root / "hidden")
    rc = _run(["docs", "list"])
    out = capsys.readouterr()
    assert rc == 2
    assert out.out == ""
    assert "cannot read docs directory" in out.err and "hidden" in out.err
    assert "Traceback" not in out.err


def test_the_real_tree_serves_the_deepest_folded_index(monkeypatch, capsysbinary):
    """The seventh folded README index in the shipped tree — the deepest one, and the one a
    synthetic fixture is least likely to model. Byte-identical to that directory's own README."""
    monkeypatch.delenv("UEDCLI_DOCS_DIR", raising=False)
    readme = userdocs.docs_root() / "leveldesign" / "general" / "recipes" / "shapes" / "README.md"
    assert readme.is_file()
    assert _run(["docs", "show", "leveldesign/general/recipes/shapes"]) == 0
    assert capsysbinary.readouterr().out == readme.read_bytes()


def test_docs_run_in_a_bare_checkout_with_no_project_level_or_games_config(capsys):
    """The whole point of shipping the docs in the tool: `docs` must answer in an install that has
    no project, no `$UEDCLI_LEVEL` and no games config. (The autouse fixtures sever all three.)"""
    assert _run(["docs", "list"]) == 0
    out = capsys.readouterr()
    assert "usage" in out.out.split()
    assert out.err.strip().endswith("topic(s)")
    assert _run(["docs", "show", "usage"]) == 0

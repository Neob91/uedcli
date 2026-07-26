"""Doc-link regressions — every markdown link and anchor in the tracked tree resolves.

The docs restructure (`plans/2026-07-26-docs-restructure-plan.md`) retargets ~175 files' citations
away from a deleted `decisions.md`/`direction.md`. Its stated mitigation for "citations dangle or
silently rot" is a link check — which did not exist when the plan was written, so every "verify"
in it was prose. This is that check.

It deliberately covers TWO failure modes the restructure introduces:

1. **A link to a path that no longer exists** — the ordinary case, once a doc is deleted.
2. **A `path#anchor` whose anchor is gone** — the case the restructure makes newly possible.
   Citations used to point at an immutable dated ledger entry; they now point into a
   revise-in-place `rationale/<topic>.md`, so a heading can be edited away underneath a comment
   that still cites it. A missing anchor is silent otherwise.

EXEMPTIONS. `dev/docs/specs/` and `dev/docs/plans/` are ephemeral scratch, deleted once their work
lands, so they are not retargeted and not checked — EXCEPT the ones referenced from
`board/to-build.md`, which are on-deck to be executed and must not carry rot. That carve-out is
derived live from `to-build.md` rather than hardcoded, so it cannot go stale.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: ``[text](target)`` — captures the target, minus any title. Skips images (``![...]``).
_MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

#: A markdown heading, for building the anchor set of a link target.
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*$", re.MULTILINE)

#: Fenced blocks and inline code, stripped before link matching. These docs are full of
#: disassembly and pseudo-code where ``Foo[Level](args)`` and ``[...](...)`` are code, not links —
#: scanning them raw produces false positives that would get the whole check switched off.
_FENCE = re.compile(r"^(?P<f>```|~~~).*?^(?P=f)", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")

_EPHEMERAL = ("dev/docs/specs/", "dev/docs/plans/")


def _prose(text: str) -> str:
    """Text with code stripped, so only real markdown links remain."""
    return _INLINE_CODE.sub("", _FENCE.sub("", text))


def _is_doc_target(target: str) -> bool:
    """Is this target a link to a document, rather than prose that happens to look like one?

    These docs contain unbackticked struct notation in table cells — ``iZone[2](u16)``,
    ``i_leaf[0](i32)`` — which a markdown parser genuinely reads as a link and which no amount of
    code-fence stripping catches. Restricting to path-shaped targets (a separator, a `.md`, or a
    pure fragment) keeps the check honest without flagging prose nobody will "fix".
    """
    core = target.split("#")[0]
    return "/" in core or core.endswith(".md") or target.startswith("#")


def _links(path: Path) -> list[str]:
    found = _MD_LINK.findall(_prose(path.read_text(encoding="utf-8", errors="replace")))
    return [t for t in found if _is_doc_target(t)]


def _tracked(*suffixes: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p and p.endswith(suffixes)]


def _on_deck() -> frozenset[str]:
    """Ephemeral files referenced from ``to-build.md`` — by link OR backticked path.

    Both forms count: `to-build.md` cites some artifacts as markdown links and at least one as a
    bare backticked path, and an exemption boundary that sees only one form silently skips files
    that are about to be executed.
    """
    board = REPO / "dev/docs/board/to-build.md"
    if not board.is_file():
        return frozenset()
    text = _prose(board.read_text(encoding="utf-8"))
    refs = set(_MD_LINK.findall(text)) | set(re.findall(r"`([^`]+\.md)`", board.read_text(encoding="utf-8")))
    out = set()
    for ref in refs:
        stem = ref.split("#")[0]
        # A markdown link resolves against `board/`; a backticked path is written from the
        # dev-docs root (`specs/2026-07-24-docs-command.md`). Try both and keep what exists —
        # resolving only against `board/` silently drops every backticked ref, which is the
        # exemption boundary, so the miss shows up as files being checked or skipped wrongly.
        for base in (board.parent, REPO / "dev/docs", REPO):
            resolved = (base / stem).resolve()
            if resolved.exists():
                try:
                    out.add(str(resolved.relative_to(REPO)))
                except ValueError:
                    pass
                break
    return frozenset(out)


def _slug(heading: str) -> str:
    """GitHub's anchor slug: lowercase, drop punctuation, EACH space becomes a hyphen.

    Runs are NOT collapsed — that is the whole subtlety. ``Movers — animated brush actors``
    drops the em-dash and leaves two adjacent spaces, which GitHub renders as ``movers--animated``.
    A slugger that collapses whitespace produces ``movers-animated``, matches nothing, and reports
    every em-dashed heading in the tree as broken.
    """
    s = re.sub(r"[`*_]", "", heading).strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s", "-", s)


def _anchors(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {_slug(h) for h in _HEADING.findall(text)}


def _checked_docs() -> list[Path]:
    on_deck = _on_deck()
    docs = []
    for p in _tracked(".md"):
        rel = str(p.relative_to(REPO))
        if rel.startswith(_EPHEMERAL) and rel not in on_deck:
            continue
        docs.append(p)
    return docs


@pytest.mark.parametrize("doc", _checked_docs(), ids=lambda p: str(p.relative_to(REPO)))
def test_markdown_links_resolve(doc: Path) -> None:
    """Every ``[text](path)`` in a checked doc points at a file that exists."""
    broken = []
    for target in _links(doc):
        if target.startswith(("http://", "https://", "mailto:")) or target.startswith("#"):
            continue
        resolved = (doc.parent / target.split("#")[0]).resolve()
        if not resolved.exists():
            broken.append(f"{target} -> {resolved}")
    assert not broken, f"{doc.relative_to(REPO)} links to missing files:\n  " + "\n  ".join(broken)


@pytest.mark.parametrize("doc", _checked_docs(), ids=lambda p: str(p.relative_to(REPO)))
def test_markdown_anchors_resolve(doc: Path) -> None:
    """Every ``[text](path#anchor)`` points at a heading that exists in the target.

    This is the check that catches revise-in-place rot: the file still exists, so an
    existence-only checker passes, while the heading the citation was about is gone.
    """
    broken = []
    for target in _links(doc):
        if target.startswith(("http://", "https://", "mailto:")) or "#" not in target:
            continue
        path_part, _, anchor = target.partition("#")
        resolved = (doc.parent / path_part).resolve() if path_part else doc
        if not resolved.is_file() or not anchor:
            continue
        if _slug(anchor) not in _anchors(resolved):
            broken.append(f"{target} (no heading '#{anchor}')")
    assert not broken, f"{doc.relative_to(REPO)} cites missing anchors:\n  " + "\n  ".join(broken)


#: Files that MAY name a deleted doc, because naming it is their job. Without these the check
#: below makes the migration's own end state unreachable: the signpost and the disposition map
#: exist precisely to say where `decisions.md` went, and this module names both docs to check them.
_MAY_NAME_DELETED = frozenset({
    "dev/docs/rationale/README.md",     # the "git log --follow -- dev/docs/decisions.md" signpost
    "dev/docs/rationale/MIGRATION.md",  # the durable date -> topic map, which is *about* the ledger
    "uedctl/tests/test_doc_links.py",   # this file
})


def test_no_citation_of_a_deleted_doc() -> None:
    """No tracked file cites `decisions.md` or `direction.md` once they are gone.

    Skips while either still exists — during the migration they legitimately have citations. The
    moment the restructure removes one, this starts enforcing that nothing points at it. Ephemeral
    specs/plans are exempt (they are deleted with their work), except the on-deck ones, and
    `_MAY_NAME_DELETED` is exempt by design.
    """
    on_deck = _on_deck()
    # Built, not literal, so this module does not match its own check.
    for name in ("decisions" + ".md", "direction" + ".md"):
        if (REPO / "dev/docs" / name).exists():
            continue
        offenders = []
        for p in _tracked(".md", ".py", ".sh", ".toml"):
            rel = str(p.relative_to(REPO))
            if rel in _MAY_NAME_DELETED:
                continue
            if rel.startswith(_EPHEMERAL) and rel not in on_deck:
                continue
            if name in p.read_text(encoding="utf-8", errors="replace"):
                offenders.append(rel)
        assert not offenders, (
            f"{name} is deleted but still cited by:\n  " + "\n  ".join(sorted(offenders))
        )


# --- the checker's own regressions -------------------------------------------------------------
# `dev/docs/rules/spikes.md` "pin the finding, or it rots" — a check nobody has watched fail is a check
# nobody knows works. Two of these shapes DID silently pass an earlier revision: a same-directory
# anchored link (`architecture.md#nope`) was dropped because the target ends in the fragment, not
# in `.md`.

@pytest.mark.parametrize(
    "target, should_be_checked",
    [
        ("other.md", True),
        ("sub/dir/other.md", True),
        ("other.md#some-anchor", True),   # regression: the fragment used to defeat the suffix test
        ("#same-file-anchor", True),
        ("u16", False),                   # struct notation in a table cell, not a link
        ("i32", False),
    ],
)
def test_is_doc_target(target: str, should_be_checked: bool) -> None:
    assert _is_doc_target(target) is should_be_checked


def test_checker_catches_a_broken_link_and_anchor(tmp_path: Path) -> None:
    """The two failure modes, exercised end to end against a scratch doc."""
    doc = tmp_path / "probe.md"
    (tmp_path / "real.md").write_text("# Real Heading\n", encoding="utf-8")
    doc.write_text(
        "[gone](./no-such-file.md)\n"
        "[dead anchor](real.md#not-a-heading)\n"
        "[fine](real.md#real-heading)\n",
        encoding="utf-8",
    )
    targets = _links(doc)
    assert "./no-such-file.md" in targets and "real.md#not-a-heading" in targets

    missing = [t for t in targets if not (doc.parent / t.split("#")[0]).resolve().exists()]
    assert missing == ["./no-such-file.md"]

    bad_anchors = [
        t for t in targets
        if "#" in t
        and (doc.parent / t.split("#")[0]).is_file()
        and _slug(t.split("#", 1)[1]) not in _anchors(doc.parent / t.split("#")[0])
    ]
    assert bad_anchors == ["real.md#not-a-heading"]

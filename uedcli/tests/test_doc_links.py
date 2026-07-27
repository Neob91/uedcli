"""Doc-link regressions — every markdown link and anchor in the tracked tree resolves.

The docs restructure (board item `docs-restructure-is-complete`) retargets ~175 files' citations
away from a deleted `decisions.md`/`direction.md`. Its stated mitigation for "citations dangle or
silently rot" is a link check — which did not exist when the plan was written, so every "verify"
in it was prose. This is that check.

It deliberately covers TWO failure modes the restructure introduces:

1. **A link to a path that no longer exists** — the ordinary case, once a doc is deleted.
2. **A `path#anchor` whose anchor is gone** — the case the restructure makes newly possible.
   Citations used to point at an immutable dated ledger entry; they now point into a
   revise-in-place `rationale/<topic>.md`, so a heading can be edited away underneath a comment
   that still cites it. A missing anchor is silent otherwise.

EXEMPTIONS. A spec or plan now lives inside the board item it belongs to, at
`dev/docs/board/<stage>/<item>/spec.md` (or `plan.md`). Those are ephemeral scratch, deleted once
their work lands, so they are not retargeted and not checked — EXCEPT under `to-build/`, whose
items are on-deck to be executed and must not carry rot. The exemption is therefore a path SHAPE,
matched against the stage directory the file sits in, so an item advancing into or out of the build
queue changes its checking with one `git mv` and nothing to keep in sync.
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

#: An item's own ephemeral `spec.md`/`plan.md`, in any stage EXCEPT the build queue. The negative
#: lookahead is what keeps `to-build/` checked: those items are about to be executed, so rot in
#: their spec or plan is rot someone is about to act on.
_EPHEMERAL_SHAPE = re.compile(r"dev/docs/board/(?!to-build/)[^/]+/[^/]+/(?:spec|plan)\.md$")


def _is_ephemeral(rel: str) -> bool:
    """Is this repo-relative path an un-checked ephemeral spec or plan?"""
    return bool(_EPHEMERAL_SHAPE.fullmatch(rel))


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
    if target.startswith("#") or "/" in core:
        return True
    # A bare filename counts if it has a plausible file suffix. Spike docs link to their committed
    # harness scripts as `harness.py`, which a `.md`-only test drops.
    return bool(re.search(r"\.(md|py|sh|toml|txt|json|t3d|rs)$", core, re.IGNORECASE))


def _links(path: Path) -> list[str]:
    found = _MD_LINK.findall(_prose(path.read_text(encoding="utf-8", errors="replace")))
    return [t for t in found if _is_doc_target(t)]


def _tracked(*suffixes: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p and p.endswith(suffixes)]


def _slug(heading: str) -> str:
    """An APPROXIMATION of GitHub's anchor slug: lowercase, drop punctuation, each space to a hyphen.

    Deliberately coarser than `github-slugger` — it also strips `_` and symbols (→ ⇒ ✅) that
    GitHub keeps, so ~535 real headings slug differently here. That is safe in one direction only:
    the same coarsening is applied to both the heading and the citation, so it can accept an
    anchor GitHub would reject, but never reject one GitHub would accept. False negatives, not
    false positives — the right way round for a check that must not redden the suite.

    Runs are NOT collapsed. ``Movers — animated brush actors``
    drops the em-dash and leaves two adjacent spaces, which GitHub renders as ``movers--animated``.
    A slugger that collapses whitespace produces ``movers-animated``, matches nothing, and reports
    every em-dashed heading in the tree as broken.
    """
    s = re.sub(r"[`*_]", "", heading).strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s", "-", s)


def _anchors(path: Path) -> set[str]:
    """Every anchor the target file offers, in document order.

    Two subtleties, both of which produced wrong answers before they were handled:

    * **Repeated headings get numeric suffixes.** GitHub disambiguates a second ``## Procedure``
      as ``#procedure-1``. Collecting slugs into a plain set loses that, so a *correct*
      cross-reference into any doc with repeated headings reads as broken — nine checked docs
      have them today, and one false positive is what gets a check switched off.
    * **Fences are stripped**, matching `_links`. Otherwise a ``#`` line inside a code sample
      registers as a real heading, and a citation into it passes silently — the exact
      revise-in-place rot the anchor check exists to catch.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    seen: dict[str, int] = {}
    out: set[str] = set()
    for heading in _HEADING.findall(_FENCE.sub("", text)):
        slug = _slug(heading)
        n = seen.get(slug, 0)
        out.add(slug if n == 0 else f"{slug}-{n}")
        seen[slug] = n + 1
    return out


def _rel(path: Path) -> str:
    """Repo-relative path for messages, tolerating a scratch doc outside the repo (self-tests)."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _checked_docs() -> list[Path]:
    return [p for p in _tracked(".md") if not _is_ephemeral(str(p.relative_to(REPO)))]


#: Links that are allowed to dangle, keyed by the doc that writes them.
#:
#: `dev/docs/decisions.md` is FROZEN — the retired ledger, kept verbatim as history and never
#: edited again. It links twice into the old `dev/docs/specs/` tree, which no longer exists: a spec
#: now lives inside the board item it belongs to. The rule that the file may not be touched wins
#: over the rule that links resolve, so the two targets are named here instead. Nothing else in the
#: tree gets this treatment; a dangling link anywhere else is a defect.
_FROZEN_DANGLING = {
    "dev/docs/decisions.md": frozenset({
        # Literal link targets as decisions.md writes them — NOT board-item references. They must
        # stay spelled exactly like the frozen file's text or the exemption stops matching.
        "specs/" "2026-07-25-docs-restructure.md",
        "specs/" "2026-07-24-docs-command.md",
    }),
}


@pytest.mark.parametrize("doc", _checked_docs(), ids=lambda p: str(p.relative_to(REPO)))
def test_markdown_links_resolve(doc: Path) -> None:
    """Every ``[text](path)`` in a checked doc points at a file that exists."""
    allowed = _FROZEN_DANGLING.get(_rel(doc), frozenset())
    broken = []
    for target in _links(doc):
        if target.startswith(("http://", "https://", "mailto:")) or target.startswith("#"):
            continue
        if target in allowed:
            continue
        resolved = (doc.parent / target.split("#")[0]).resolve()
        if not resolved.exists():
            broken.append(f"{target} -> {resolved}")
    assert not broken, f"{_rel(doc)} links to missing files:\n  " + "\n  ".join(broken)


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
    assert not broken, f"{_rel(doc)} cites missing anchors:\n  " + "\n  ".join(broken)


#: Files that MAY name a deleted doc, because naming it is their job. Without these the check
#: below makes the migration's own end state unreachable: the signpost and the disposition map
#: exist precisely to say where `decisions.md` went, and this module names both docs to check them.
_MAY_NAME_DELETED = frozenset({
    "dev/docs/rationale/README.md",     # the "git log --follow -- dev/docs/decisions.md" signpost
    "dev/docs/rationale/MIGRATION.md",  # the durable date -> topic map, which is *about* the ledger
    "uedcli/tests/test_doc_links.py",   # this file
})


def test_no_citation_of_a_deleted_doc() -> None:
    """No tracked file cites `decisions.md` or `direction.md` once they are gone.

    Skips while either still exists — during the migration they legitimately have citations. The
    moment the restructure removes one, this starts enforcing that nothing points at it. Ephemeral
    specs/plans are exempt (they are deleted with their work), except the ones queued in
    `to-build/`, and `_MAY_NAME_DELETED` is exempt by design.
    """
    # NOTE: this module DOES contain both literals (see its docstring); it passes only because
    # it is in `_MAY_NAME_DELETED`. Do not remove that entry on the strength of this loop.
    for name in ("decisions" + ".md", "direction" + ".md"):
        if (REPO / "dev/docs" / name).exists():
            continue
        offenders = []
        for p in _tracked(".md", ".py", ".sh", ".toml"):
            rel = str(p.relative_to(REPO))
            if rel in _MAY_NAME_DELETED:
                continue
            if _is_ephemeral(rel):
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


def _probe(tmp_path: Path, body: str) -> Path:
    """A scratch doc plus a real target to link at."""
    (tmp_path / "real.md").write_text(
        "# Real Heading\n\n## Procedure\n\ntext\n\n## Procedure\n\nmore\n",
        encoding="utf-8",
    )
    doc = tmp_path / "probe.md"
    doc.write_text(body, encoding="utf-8")
    return doc


def test_link_check_fails_on_a_missing_file(tmp_path: Path) -> None:
    """Drive the REAL gate, not a re-implementation of it.

    The earlier version of this test asserted `_links`/`_slug`/`_anchors` inline, so gutting
    `test_markdown_links_resolve` to a no-op still passed — 476 green tests guarding nothing.
    Calling the gate function itself is what makes this a regression rather than decoration.
    """
    doc = _probe(tmp_path, "[gone](./no-such-file.md)\n")
    with pytest.raises(AssertionError, match="links to missing files"):
        test_markdown_links_resolve(doc)


def test_anchor_check_fails_on_a_missing_anchor(tmp_path: Path) -> None:
    doc = _probe(tmp_path, "[dead](real.md#not-a-heading)\n")
    with pytest.raises(AssertionError, match="cites missing anchors"):
        test_markdown_anchors_resolve(doc)


def test_both_checks_pass_on_a_clean_doc(tmp_path: Path) -> None:
    """A green run must be reachable, or the checks are just a wall."""
    doc = _probe(tmp_path, "[fine](real.md#real-heading)\n[code](real.md)\n")
    test_markdown_links_resolve(doc)
    test_markdown_anchors_resolve(doc)


def test_repeated_headings_get_numeric_suffixes(tmp_path: Path) -> None:
    """`#procedure-1` is a VALID citation into a doc with two `## Procedure` headings.

    Nine checked docs have repeated headings; treating the second one's anchor as broken is a
    false positive on correct content, which is how a check earns its own deletion.
    """
    doc = _probe(tmp_path, "[second](real.md#procedure-1)\n")
    test_markdown_anchors_resolve(doc)
    assert {"procedure", "procedure-1"} <= _anchors(tmp_path / "real.md")


def test_headings_inside_code_fences_are_not_anchors(tmp_path: Path) -> None:
    """A `#` line in a code sample is not a heading, so citing it must fail."""
    (tmp_path / "real.md").write_text(
        "# Real Heading\n\n```\n# Not A Heading\n```\n", encoding="utf-8"
    )
    doc = tmp_path / "probe.md"
    doc.write_text("[phantom](real.md#not-a-heading)\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="cites missing anchors"):
        test_markdown_anchors_resolve(doc)

# --- prose citations ------------------------------------------------------------------------
# The dominant citation form in this tree is PROSE, not a markdown link: `dev/docs/rules/spikes.md`
# "pin the finding". A link checker passes all of it, which is why the restructure's ~177-file
# retarget had no check behind it.
#
# SCOPE, deliberately narrow. A blanket "every backticked path must exist" flags ~150 legitimate
# references: plans naming files they will create, paths into other repos, `_scratch/` (gitignored
# by design), and spike-internal relatives. Those are not defects, and a check that cries wolf at
# them gets deleted. So this guards exactly what the migration creates and repoints at — the three
# new doc trees. A citation into `direction/`, `rationale/` or `rules/` that does not resolve is
# always a real defect, because those files are the retarget destinations.

_NEW_TREES = ("dev/docs/direction/", "dev/docs/rationale/", "dev/docs/rules/")
_PROSE_PATH = re.compile(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+\.(?:md|py|sh|toml|rs))`")


def _declared_direction_topics() -> frozenset[str]:
    """Topic files listed in `direction/README.md`'s index.

    The index is the tree's manifest, so a citation to a topic it declares is a legitimate forward
    reference while that topic is still pending migration — not rot. A citation to a path the index
    does NOT declare is rot, which is what this distinction buys.
    """
    idx = REPO / "dev/docs/direction/README.md"
    if not idx.is_file():
        return frozenset()
    return frozenset(re.findall(r"`?([a-z0-9-]+\.md)`?", idx.read_text(encoding="utf-8")))


def _prose_paths(path: Path) -> list[str]:
    text = _FENCE.sub("", path.read_text(encoding="utf-8", errors="replace"))
    return _PROSE_PATH.findall(text)


@pytest.mark.parametrize("doc", _checked_docs(), ids=lambda p: str(p.relative_to(REPO)))
def test_prose_citations_into_the_new_trees_resolve(doc: Path) -> None:
    """A backticked path into `direction/`, `rationale/` or `rules/` points at a real file."""
    broken = []
    for ref in _prose_paths(doc):
        norm = ref if ref.startswith("dev/docs/") else "dev/docs/" + ref.lstrip("./")
        if not norm.startswith(_NEW_TREES):
            continue
        if any((base / ref).exists() for base in (doc.parent, REPO, REPO / "dev/docs")):
            continue
        if norm.startswith("dev/docs/direction/") and Path(ref).name in _declared_direction_topics():
            continue  # declared in the index, pending migration
        broken.append(ref)
    assert not broken, f"{_rel(doc)} cites missing paths in the new trees:\n  " + "\n  ".join(broken)

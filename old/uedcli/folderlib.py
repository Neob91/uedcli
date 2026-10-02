"""Folder path grammar + globstar matching — the pure core of the actor-folder feature.

A **folder** is a uedcli-side hierarchical dotted organization path on an actor (`castle.tower.roof`),
stored in a per-actor trunk sidecar, never emitted to the built map, independent of the T3D `Group=`
prop. This module is the pure grammar/validation + the NORMATIVE match algorithm; it has no I/O and
no editor. See board item `actor-folders-hierarchical-actor-organization` §3 (the spec the tests pin) and
dev/docs/architecture.md "Folders".

Two grammars:
- a STORED path (`actor folder set --to` / `actor add --folder`): literal segments only.
- a QUERY pattern (`actor find --folder`): literal segments plus the `*` / `**` globstar tokens.

Matching is **case-insensitive** (FName-consistent, mirroring the group match); a stored path is
kept as authored for display.
"""
from __future__ import annotations

import re

# One segment of a STORED path: conservative, since a stored path must not contain the pattern
# metacharacters or separators that would make a query ambiguous. Folders are never emitted to the
# editor, so there is no FName char constraint — the set is deliberately narrow, not maximal
# (decision R2: "keep [A-Za-z0-9_+-]").
_SEGMENT = re.compile(r"[A-Za-z0-9_+-]+")


def validate_segment(s: str) -> None:
    """Validate a SINGLE literal segment against the shared `[A-Za-z0-9_+-]` charset. Raises
    `ValueError` (naming the offending value) if `s` is empty or contains a character outside the
    set (so a `.`, `/`, `\\`, whitespace, `*`, `,` all reject). This is the folder charset shared
    with labels (labellib layers a leading-`-` reject on top); it does NOT itself reject a leading
    `-`, because folder paths rely on the bare charset."""
    if not _SEGMENT.fullmatch(s):
        raise ValueError(
            f"invalid segment: {s!r} (must match [A-Za-z0-9_+-], no '.', '/', '\\', whitespace, "
            f"'*', or ',')")


def validate_folder_path(path: str) -> None:
    """Validate a STORED folder path. Raises `ValueError` (naming the offending value) if it is
    empty, has an empty segment (leading/trailing/`..` dot), or a segment with a character outside
    `[A-Za-z0-9_+-]` (rejecting `*`, `,`, `/`, `\\`, whitespace, and a `.` inside a segment)."""
    if not path:
        raise ValueError("folder path must not be empty")
    segments = path.split(".")
    for seg in segments:
        if seg == "":
            raise ValueError(
                f"invalid folder path {path!r}: empty segment (no leading/trailing/'..' dot)")
        if not _SEGMENT.fullmatch(seg):
            raise ValueError(
                f"invalid folder path {path!r}: segment {seg!r} must match [A-Za-z0-9_+-] "
                f"(no '*', ',', '/', '\\', whitespace, or '.' inside a segment)")


def validate_pattern(pattern: str) -> None:
    """Validate a QUERY pattern (`actor find --folder`). Each `.`-separated segment must be exactly
    `*`, exactly `**`, or a pure literal `[A-Za-z0-9_+-]+`. Rejects `?`/`[`/`]` and any other
    metacharacter, `***` (no triple-star), a mixed `a*b` segment, and empty segments — so an
    fnmatch-style implementation can never silently leak `?`/`[...]` semantics the grammar never
    sanctions (spec §3). Raises `ValueError` naming the offending value."""
    if not pattern:
        raise ValueError("folder pattern must not be empty")
    for seg in pattern.split("."):
        if seg in ("*", "**"):
            continue
        if seg == "":
            raise ValueError(
                f"invalid folder pattern {pattern!r}: empty segment (no leading/trailing/'..' dot)")
        if not _SEGMENT.fullmatch(seg):
            raise ValueError(
                f"invalid folder pattern {pattern!r}: segment {seg!r} must be a literal "
                f"[A-Za-z0-9_+-]+, '*' (one segment), or '**' (any depth) — no '?', '[', ']', "
                f"'***', or mixed literal/star segments")


def format_folder_carrier(folder: str) -> str:
    """The `// uedcli-folder:` line for an actor's folder path, indented to sit inside an actor block
    (mirrors `labellib.format_labels_carrier`). Consumed by `emit.inject_carriers` / `actor show`; the
    T3D importer strips bare `//` lines, so it round-trips uedcli-side only."""
    return "    // uedcli-folder: " + folder


def is_wildcard_free(pattern: str) -> bool:
    """A pattern is 'wildcard-free' iff it contains no `*`. That single exact test drives the
    subtree-vs-glob switch in `matches` (spec §3)."""
    return "*" not in pattern


def _seg_match(pat: list[str], path: list[str]) -> bool:
    """Globstar segment-list match: `*` = exactly one segment, `**` = zero or more segments, a
    literal = that exact segment. Provably identical to the spec's anchored separator-absorbing
    regex (both operate at whole-segment granularity); the boundary cases are pinned in the tests."""
    if not pat:
        return not path
    head = pat[0]
    if head == "**":
        # zero or more path segments, then the rest of the pattern
        for k in range(len(path) + 1):
            if _seg_match(pat[1:], path[k:]):
                return True
        return False
    if not path:
        return False
    if head == "*":                          # exactly one segment (segments are always non-empty)
        return _seg_match(pat[1:], path[1:])
    return head == path[0] and _seg_match(pat[1:], path[1:])


def matches(pattern: str, folder: str | None) -> bool:
    """Does `folder` match `pattern`? The §3 normative algorithm (validate the pattern first).

    - `folder is None` (ungrouped) matches NO pattern (select the ungrouped set with `--no-folder`).
    - Case-insensitive (casefold both, then split on `.`).
    - A **wildcard-free** pattern `X` matches `X` AND its whole subtree: `folder == X` or `folder`
      starts with `X + "."` (segment-boundary prefix, so `cast` does NOT match `castle`).
    - A pattern containing any `*` is a pure glob with NO subtree extension: `*` = exactly one
      segment, `**` = any depth (zero or more segments, incl. `X.**` matching `X` itself and
      `**.roof` matching a top-level `roof`)."""
    if folder is None:
        return False
    p = pattern.casefold()
    f = folder.casefold()
    if is_wildcard_free(pattern):
        return f == p or f.startswith(p + ".")
    return _seg_match(p.split("."), f.split("."))

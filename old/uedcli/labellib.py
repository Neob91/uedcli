"""Label grammar + flat `*`-only matching + the interchange carrier — the pure core of the
actor-label feature.

A **label** is a uedcli-side flat classification token on an actor (e.g. "lighting", "flammable",
"dup-a1f"). Actors carry a SET of them (`Actor.labels: frozenset[str]`), stored in a per-actor trunk
sidecar, never emitted to the built map, orthogonal to `folder`/`Group`/`Tag`. This module is the
pure grammar/validation + the flat matcher + the `// uedcli-labels:` carrier; it has NO I/O, no
editor, and MUST stay model-free (imported at the top of `model.py`, so a `model` import here would
cycle). See board item `re-evaluate-whether-reject-nonlevel-target` and dev/docs/architecture.md.

Two grammars mirror the folder split, but a label is a single FLAT token (no dotted path):
- a STORED label (`actor label add`/`actor add --label`): one literal segment, no leading `-`.
- a QUERY pattern (`actor find --label`): a literal plus the `*` wildcard ONLY (no `?`/`[`/`]`).

Matching is **case-insensitive** (mirroring folders), via `fnmatch.fnmatchcase` on casefolded
operands (bare `fnmatch.fnmatch` is case-sensitive on Linux, so it is deliberately NOT used).
"""
from __future__ import annotations

import fnmatch
import re

from . import folderlib

# The `actor show` label interchange carrier: a bare `// uedcli-labels: a,b,c` line inside an actor
# block (comma-joined, sorted). `actor show` emits it from the labels sidecar; the T3D importer
# strips all bare `//` lines, so the text pastes cleanly into UnrealEd. `model.parse_t3d` reads it
# back into `actor.labels`. A stored trunk body NEVER contains this line — labels are the sidecar.
_LABELS_CARRIER = re.compile(r"^\s*//\s*uedcli-labels:\s*(.+?)\s*$")


def validate_label(s: str) -> None:
    """Validate a STORED label. Shares the folder single-segment charset (`[A-Za-z0-9_+-]`, no `.`)
    then additionally rejects a LEADING `-` (so a label never looks like a `remove --label` flag or
    a negated token). Raises `ValueError` naming the offending value."""
    folderlib.validate_segment(s)
    if s.startswith("-"):
        raise ValueError(f"label cannot start with '-': {s!r}")


def match_label(pattern: str, label: str) -> bool:
    """Does `label` match the query `pattern`? Case-insensitive, with `*` the ONLY wildcard: `?`,
    `[`, and `]` are rejected (raising `ValueError`) so an fnmatch char-class can never silently
    leak semantics the grammar never sanctions. Both operands are casefolded first."""
    if any(ch in pattern for ch in "?[]"):
        raise ValueError(
            f"invalid label pattern {pattern!r}: '*' is the only wildcard (no '?', '[', ']')")
    return fnmatch.fnmatchcase(label.casefold(), pattern.casefold())


def format_labels_carrier(labels) -> str:
    """The `// uedcli-labels:` line for an actor's label set: sorted, comma-joined, indented to sit
    inside an actor block (mirrors the folder carrier's indentation)."""
    return "    // uedcli-labels: " + ",".join(sorted(labels))


def parse_labels_carrier(match: re.Match) -> set[str]:
    """The captured group of `_LABELS_CARRIER` → the label set (split on `,`, strip, drop blanks)."""
    return {tok.strip() for tok in match.group(1).split(",") if tok.strip()}

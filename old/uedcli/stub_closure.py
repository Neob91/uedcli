"""Resolve a v68 package's DIRECT dependencies (ONE hop) and classify each — already-v69 code
(substrate or cache), must-stub v68 code, or content — for the stubbing pipeline.

Deliberately NOT a transitive DAG / topo-sort: the closure bottoms out on the committed v69
substrate, so a direct code dep is either already v69 or a single shallow stub. The one case that
would force going deeper — a must-stub dep that itself needs an only-v68 code dep — is surfaced as
a hard, named error (the M1 boundary), never silently chased. See
`dev/docs/specs/2026-06-21-uedcli-package-stubbing-design.md`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .dxpkg import direct_packages
from .packages import _ALWAYS_LOADED

_CODE_EXT = ".u"
_CONTENT_EXTS = (".utx", ".uax", ".umx")


class StubClosureError(RuntimeError):
    """A dependency could not be classified, or a deeper-than-one-hop stub would be required. A
    `RuntimeError` so a resolution site's existing guard catches it (no bare traceback to the user)."""


@dataclass(frozen=True, kw_only=True)
class ClosureResult:
    ready_code: tuple[str, ...]      # direct code deps already v69 (substrate/cache or always-loaded)
    must_stub_code: tuple[str, ...]  # direct code deps present only as v68 install `.u`
    content: tuple[str, ...]         # content packages (loaded, never stubbed)


def _resolves_as(name: str, exts: tuple[str, ...], dirs: list[str]) -> bool:
    """Case-insensitive: does any dir hold `<name><ext>` for an `ext` in `exts`?"""
    want = {f"{name}{ext}".lower() for ext in exts}
    for d in dirs:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        if any(n.lower() in want for n in entries):
            return True
    return False


def _find_code(name: str, dirs: list[str]) -> str | None:
    want = f"{name}{_CODE_EXT}".lower()
    for d in dirs:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for n in entries:
            if n.lower() == want:
                return os.path.join(d, n)
    return None


def _classify(name: str, *, v69_code_dirs: list[str], search_dirs: list[str]) -> str:
    """Return one of 'ready' / 'must-stub' / 'content'; raise StubClosureError if unresolvable.

    Precedence: always-loaded > v69 code (substrate ≻ cache, both in `v69_code_dirs`) > v68 code >
    content. Discrimination is by EXTENSION within the SAME `search_dirs` (the whole composed config
    set, direction/containers.md 2026-07-14 — one uniform dir set): a name present as `.u` there is v68 code
    (must-stub); present as a content ext is content. `.u` wins over a same-named content ext (a code
    dep by reference); `.dx` is excluded (a level is never a code/content dependency)."""
    if name in _ALWAYS_LOADED:
        return "ready"
    if _resolves_as(name, (_CODE_EXT,), v69_code_dirs):
        return "ready"
    if _resolves_as(name, (_CODE_EXT,), search_dirs):
        return "must-stub"
    if _resolves_as(name, _CONTENT_EXTS, search_dirs):
        return "content"
    raise StubClosureError(f"{name} not found on substrate / cache / composed search path")


def resolve(
    v68_path: str,
    *,
    substrate_dirs: list[str],
    cache_dir: str,
    search_dirs: list[str],
) -> ClosureResult:
    """Classify `<P>`'s direct deps. `substrate_dirs`+`cache_dir` are the v69 CODE dirs (UED22 + the
    stub cache — the ONLY code/content split that remains, and it's about VERSION not directory role).
    `search_dirs` is the whole composed config set (project overlay before game base): a dep present
    there as v68 `.u` is must-stub, as a content ext is content — discriminated by extension, not by a
    per-dir classification."""
    v69_code_dirs = [*substrate_dirs, cache_dir]
    ready, must_stub, content = [], [], []
    for name in sorted(direct_packages(v68_path)):
        kind = _classify(name, v69_code_dirs=v69_code_dirs, search_dirs=search_dirs)
        (ready if kind == "ready" else must_stub if kind == "must-stub" else content).append(name)

    # M1 boundary: a must-stub dep whose OWN direct code deps include an only-v68 one would force a
    # second stub level — refuse, named, rather than chase it.
    for dep in must_stub:
        dep_path = _find_code(dep, search_dirs)
        if dep_path is None:
            continue
        for deeper in sorted(direct_packages(dep_path)):
            if deeper in _ALWAYS_LOADED or _resolves_as(deeper, (_CODE_EXT,), v69_code_dirs):
                continue
            if _resolves_as(deeper, (_CODE_EXT,), search_dirs):
                raise StubClosureError(
                    f"{dep} needs {deeper} which is only v68; deep recursion is out of scope"
                )
            # A deeper dep that's content, or unresolvable here, is deliberately NOT flagged: this
            # check scopes only to the "second stub level" case. An unresolvable deeper dep surfaces
            # later as a clean UCC load error while stubbing `dep` — not silently overlooked.

    return ClosureResult(
        ready_code=tuple(ready), must_stub_code=tuple(must_stub), content=tuple(content)
    )

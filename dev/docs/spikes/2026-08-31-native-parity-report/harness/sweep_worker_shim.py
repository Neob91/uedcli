#!/usr/bin/env python3
"""Runs `parity_report.py`'s own CLI, in-process, after redirecting `parity_pipeline`'s trunk-
extraction cache from its default per-worktree `_scratch/` to the sweep-wide SHARED cache
(`sweep_lib.shared_trunk_cache_root`) -- so a level already extracted by an earlier sweep run (from a
DIFFERENT, since-deleted worktree) is not re-extracted from scratch.

This is `sweep_corpus.py`'s per-level subprocess entry point -- never invoked directly by a human.
Deliberately a real `subprocess`, not an in-process function call: `sweep_corpus.py`'s scheduler needs
a real OS process to `Popen.kill()` as its hang-detector (see that file), and `parity_report.py`'s own
`--json` CLI is the "call it correctly, don't reinvent it" seam the task asked to reuse verbatim --
this shim's only job is the one-line monkeypatch, applied BEFORE `parity_report`'s own
`import parity_pipeline as pp` binds the same module object (Python's module cache makes this safe:
both imports return the identical `parity_pipeline` module, so the patched `build_root` is what
`parity_pipeline.ensure_golden` sees).

The patch mirrors the same seam `test_parity_pipeline.py` already uses to isolate `build_root`
(`patch.object(pp, "build_root", ...)`) -- not a new mechanism, just applied for real instead of in a
test.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parity_pipeline as pp  # noqa: E402
import sweep_lib as sl  # noqa: E402

_shared_root = sl.shared_trunk_cache_root(HERE)


def _shared_build_root(hash_hex: str) -> Path:
    return _shared_root / hash_hex / "trunk"


pp.build_root = _shared_build_root

import parity_report  # noqa: E402  (imports `parity_pipeline` again -- same cached module object)

if __name__ == "__main__":
    raise SystemExit(parity_report.main(sys.argv[1:]))

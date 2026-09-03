"""Re-export of the MSVC CRT `qsort` port — now single-sourced in the production module
`uedcli.native.saveorder` (see it for the disasm provenance)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.native.saveorder import msvc_qsort  # noqa: E402,F401

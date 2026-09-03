"""Re-export of the object/name creation-order model — now single-sourced in the
production module `uedcli.native.saveorder` (see it for the trace-derived provenance)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.native.saveorder import (  # noqa: E402,F401
    boot_object_paths, import_creation_order, package_creation_order, package_name_order)

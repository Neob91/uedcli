"""List a `.u`/`.utx`'s exports of a given class (e.g. LodMesh, Texture).

    python3 list_exports.py <pkg> <ClassName> [limit]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.upackage import load_package  # noqa: E402

pkg = load_package(sys.argv[1])
want = sys.argv[2].casefold()
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 40
n = 0
for i in range(len(pkg.exports)):
    ref = i + 1
    cls = pkg.object_class_name(ref)
    if cls and cls.casefold() == want:
        print(f"{ref:6d}  {pkg.object_path(ref)}")
        n += 1
        if n >= limit:
            break
print(f"-- {n} shown")

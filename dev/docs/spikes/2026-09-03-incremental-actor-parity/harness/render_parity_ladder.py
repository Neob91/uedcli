#!/usr/bin/env python3
"""Render the Parity Ladder artifact's HTML from `parity_ladder_data.json` + `parity_ladder_template.html`.

The artifact (a claude.ai Artifact, published via the `Artifact` tool -- not scriptable from here)
had gone stale twice: once from a hand-edited SNAPSHOT literal nobody kept in sync, once from a
subagent overwriting good data with a stale figure it measured on its own branch. This script makes
"update the ladder page" a data edit + a render, not a 400-line HTML hand-edit, so the SNAPSHOT block
is always exactly `json.dumps(parity_ladder_data.json)` -- never independently retyped.

Usage:
    render_parity_ladder.py [--data parity_ladder_data.json] [--template parity_ladder_template.html] -o OUT.html

Then publish OUT.html with the `Artifact` tool (`action: "publish"`, the existing artifact's `url`).
This script only produces the file; it does not call the Artifact tool itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def render(data_path: Path, template_path: Path) -> str:
    data = json.loads(data_path.read_text())
    if "updated_at" not in data:
        data["updated_at"] = max(l["updated"] for l in data["levels"])
    template = template_path.read_text()
    marker = "/*__LEVELS_JSON__*/"
    if marker not in template:
        raise ValueError(f"template is missing the {marker} placeholder")
    return template.replace(marker, json.dumps(data, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=HERE / "parity_ladder_data.json")
    ap.add_argument("--template", type=Path, default=HERE / "parity_ladder_template.html")
    ap.add_argument("-o", "--out", type=Path, required=True, help="output HTML path")
    args = ap.parse_args()

    html = render(args.data, args.template)
    args.out.write_text(html)
    print(f"wrote {args.out} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

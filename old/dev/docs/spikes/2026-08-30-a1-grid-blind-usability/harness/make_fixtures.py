"""Build the blind-usability fixtures from a rendered scene.

Reads the `actor preview --json` map and the captured stderr, and writes, per scene:

  <scene>.legend-cells.txt   the real legend  — `Name  Cell  (Span)`      (the GRID arm)
  <scene>.legend-plain.txt   the same lines with the cell/span stripped   (the CONTROL arm)
  <scene>.truth.json         per-task ground-truth name sets, from the cell map

Both arms get the SAME image. The control withholds only the addressing, which is the variable
under test — not the actor list, which an agent would have from `actor find` anyway.
"""

import json
import re
import sys
from pathlib import Path

CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def cell_of(entry: dict, pane: str) -> str:
    return entry["panes"][pane]["cell"]


def col_row(cell: str) -> tuple[int, int]:
    """`D4` → (3, 3), both 0-based. Single-letter columns only (the grid is bounded at 52)."""
    m = CELL_RE.match(cell)
    assert m, f"unparseable cell: {cell}"
    letters, row = m.group(1), int(m.group(2))
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1, row - 1


def names_in(actors: dict, pane: str, cols: tuple[int, int], rows: tuple[int, int]) -> list[str]:
    """Actors whose CENTROID cell falls in the inclusive 0-based col/row box."""
    out = []
    for name, entry in actors.items():
        c, r = col_row(cell_of(entry, pane))
        if cols[0] <= c <= cols[1] and rows[0] <= r <= rows[1]:
            out.append(name)
    return sorted(out)


def legend_lines(actors: dict, pane: str, *, cells: bool) -> list[str]:
    """The stderr legend, with or without the cell column."""
    lines = []
    for name, entry in actors.items():
        p = entry["panes"][pane]
        if not cells:
            lines.append(name)
            continue
        span = p.get("span")
        lines.append(f"{name}  {p['cell']}" + (f"  ({span})" if span else ""))
    return lines


def main(json_path: str, pane: str, tasks_path: str, out_prefix: str) -> None:
    doc = json.loads(Path(json_path).read_text())
    actors = doc["actors"]
    n = doc["grid"]["cols"]

    header = f"grid: {n}×{n} columns A–{chr(ord('A') + n - 1)}, rows 1–{n}"
    Path(f"{out_prefix}.legend-cells.txt").write_text(
        "\n".join([header] + legend_lines(actors, pane, cells=True)) + "\n")
    Path(f"{out_prefix}.legend-plain.txt").write_text(
        "\n".join(legend_lines(actors, pane, cells=False)) + "\n")

    truth = {}
    for task in json.loads(Path(tasks_path).read_text()):
        if task["kind"] == "region":
            truth[task["id"]] = names_in(actors, pane, tuple(task["cols"]), tuple(task["rows"]))
        elif task["kind"] == "locate":
            truth[task["id"]] = [cell_of(actors[task["actor"]], pane)]
        else:
            raise SystemExit(f"unknown task kind: {task['kind']}")
    Path(f"{out_prefix}.truth.json").write_text(json.dumps(truth, indent=2) + "\n")

    for tid, names in truth.items():
        print(f"{tid}: {len(names)} → {names[:6]}{' …' if len(names) > 6 else ''}")


if __name__ == "__main__":
    main(*sys.argv[1:5])

#!/usr/bin/env python3
"""Predict the export-table order of a `MAP NEW` -> `MAP IMPORT`(whole-level T3D) -> `MAP SAVE`.

FULLY GENERATIVE, zero per-level constants. Reproduces (canonical roles) the export tables of all
four probe goldens EXACTLY: toysmall (np3,nb2), toy30 (np2,nb30), toy150 (np5,nb150),
UNATCO import (np674,nb762). See structure_diff.py for the byte-level table dumps.

Inputs are the two import-order counts:
  np = number of POINT actors, nb = number of BRUSH actors (levelinfo_first_order: LevelInfo,
  then points in trunk order, then brushes in trunk order).

Roles emitted (resolve to concrete names elsewhere):
  LevelInfo, Polys3, Model2 (world model + its Polys), Camera6..Camera11 (the 6 fixed viewport
  cameras), LevelSummary, MyLevel (the ULevel), point[i], brush[i], bmodel[i]=Model_<brush i>,
  bpolys[i]=<brush i>'s Polys.

Mechanism (data-derived; the underlying editor primitive is the GObjObjects free-list, but its net
effect is this closed form):
  - Export order == ascending GObjObjects index, filtered to package objects.
  - Fixed low preamble: LevelInfo, Polys3, Camera6, Camera7, Model2.
  - The editor's object creation stream during import (excl. LevelInfo) is:
        points[0..], brushes[0..], then per brush i: bmodel[i], bpolys[i],
        with LevelSummary emitted just before the LAST brush's bpolys.
  - Exactly ONE low free slot (P6) is consumed at the MIDPOINT of that stream:
        R = (np + 3*nb - 1) // 2
    The object created at rank R (rest[R]) lands in P6 -> export slot 5 (the "displaced object";
    its class varies with size: brush / bmodel / bpolys). Camera11 takes the append slot rank R
    would otherwise have used, i.e. it sorts exactly where rest[R] was.
  - Trailing: Camera8, Camera9, Camera10, then MyLevel last.
"""
from __future__ import annotations


def predict_export_order(np_: int, nb: int) -> list[str]:
    rest = [f"point[{i}]" for i in range(np_)] + [f"brush[{i}]" for i in range(nb)]
    for i in range(nb):
        rest.append(f"bmodel[{i}]")
        if i == nb - 1:
            rest.append("LevelSummary")
        rest.append(f"bpolys[{i}]")
    R = (np_ + 3 * nb - 1) // 2                      # stream midpoint -> free slot P6
    out = ["LevelInfo", "Polys3", "Camera6", "Camera7", "Model2", rest[R]]
    for k, o in enumerate(rest):
        if k == R:
            out.append("Camera11")                   # Camera11 takes rest[R]'s would-be append slot
            continue
        out.append(o)
    out += ["Camera8", "Camera9", "Camera10", "MyLevel"]
    return out


if __name__ == "__main__":
    for np_, nb in [(3, 2), (2, 30), (5, 150), (674, 762)]:
        seq = predict_export_order(np_, nb)
        print(f"np={np_} nb={nb}: {len(seq)} exports; slot5(displaced)={seq[5]}")

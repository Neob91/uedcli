"""Brush-geometry decode (`mapimport`): the `FPoly` name table and the `RF_HasStack` body entry.

Each test pins a format trap a decoder gets wrong by default and that raises nothing when it does.
Both defects below once shipped; these are the regression pins.

The packages are SYNTHETIC, built from uedcli's own writers, because retail maps are copyrighted and
cannot be committed (`dev/docs/spikes/2026-07-24-level-import-order/findings.md`). That proves the
decoder inverts OUR writer, not that we read what UnrealEd wrote — the layouts were separately
validated against real maps, and the measurements are in `dev/docs/unrealed/package-format.md`.
"""
from __future__ import annotations

import struct

import pytest

from uedcli import mapimport
from uedcli.native.actor_write import FPoly, state_frame, write_upolys_body
from uedcli.native.codec import write_ci
from uedcli.native.umodel import Model, write_model_body
from uedcli.upackage import Package, SchemaError

RF_HasStack = 0x02000000


def _names_index(names: list[str]):
    """A `name_index(str) -> int` over a fixed name table, for uedcli's writers."""
    return lambda s: names.index(s)


def _pkg(names: list[str], exports: list[dict], buf: bytes) -> Package:
    return Package(name="Synth", version=68, names=names, imports=[], exports=exports, buf=buf)


def _square() -> list[tuple[float, float, float]]:
    return [(0.0, 0.0, 0.0), (128.0, 0.0, 0.0), (128.0, 128.0, 0.0), (0.0, 128.0, 0.0)]


def _stack(node_ref: int | None) -> bytes:
    """A serialized `FStateFrame`, or no bytes at all when `node_ref` is None.

    The frame's trailing `Offset` compact is present ONLY when `Node` is non-zero, so the two
    non-empty cases have different lengths and a reader that gets the condition wrong desyncs on
    exactly one of them. `native.actor_write.state_frame` covers the `Node != 0` case (it is only
    ever called with a real class ref, and writes the `Offset` unconditionally); the `Node == 0`
    case has no writer, so it is built here.
    """
    if node_ref is None:
        return b""
    if node_ref != 0:
        return state_frame(node_ref)
    return write_ci(0) + write_ci(0) + struct.pack("<Q", 0) + struct.pack("<I", 0)


# The three body shapes every body reader has to handle, and the export flags that select them.
_STACKS = [
    pytest.param(None, id="no-stateframe"),
    pytest.param(3, id="stateframe-node-set"),
    pytest.param(0, id="stateframe-node-zero"),
]


# ── defect A: an FPoly's Item is an FName, and name index 0 is a REAL name ───────────────────

@pytest.mark.parametrize("item_index,expected", [
    (0, "OUTSIDE"),   # index 0 is an ordinary, heavily-used name — NOT a sentinel
    (1, "Base"),
    (2, None),        # "no label" is the index of the name `None`, wherever it sits
])
def test_polygon_item_label_is_read_by_name_not_by_index_zero(item_index, expected):
    """A polygon's `Item=` label resolves through the name TABLE, and "unset" is the name `None`.

    Why this is pinned. `Item` is an `FName` — a compact index into the package's own name table —
    and it is tempting to treat index 0 as "unset" the way a null object ref is 0. It is not: in
    every Deus Ex map sampled (2026-07-27) name index 0 is `OUTSIDE`, the editor's own default face
    label, and it is genuinely used on 7399 of `02_NYC_Street.dx`'s 10690 authored polygons. A
    decoder that tests `index == 0` therefore deletes every `Item=OUTSIDE` from the map it decodes
    — silently, with no error, visible only by reading the emitted T3D and counting labels.

    The name table's order is per package, so nothing pins `None` to a fixed slot either; here it
    sits at index 2, as it does in `00_Training.dx`. Evidence and the retail census:
    `dev/docs/unrealed/package-format.md` "`FPoly.ItemName` — name index 0 is a REAL name".
    """
    names = ["OUTSIDE", "Base", "None"]
    pkg = _pkg(names, [], b"")
    fp = FPoly(verts=_square(), item_index=item_index, texture_ref=0)

    poly = mapimport.polygon_of(pkg, fp)

    assert poly.item == expected


def test_polygon_item_index_off_the_name_table_is_a_named_error():
    """A corrupt `Item` index must surface as a `SchemaError` naming the package, never as a bare
    `IndexError` out of a binary parser (`CLAUDE.md`, "Never let a Python exception reach the CLI
    user")."""
    pkg = _pkg(["None"], [], b"")
    fp = FPoly(verts=_square(), item_index=9999, texture_ref=0)

    with pytest.raises(SchemaError, match=r"Item name index 9999 .*Synth"):
        mapimport.polygon_of(pkg, fp)


# ── defect B: RF_HasStack is a per-EXPORT flag, and it lands on data objects too ──────────────

def _polys_pkg(node_ref: int | None) -> tuple[Package, list[FPoly]]:
    """A package holding one `Polys` export, optionally prefixed with a `StateFrame`."""
    names = ["None", "Polys", "Base"]
    polys = [FPoly(verts=_square(), item_index=2, texture_ref=0, poly_flags=7)]
    body = _stack(node_ref) + write_upolys_body(_names_index(names), polys)
    buf = b"\x00" * 16 + body                   # a non-zero soff, as a real package has
    export = dict(cls=0, sup=0, outer=0, nm=1,
                  flags=0 if node_ref is None else RF_HasStack,
                  ssize=len(body), soff=16)
    return _pkg(names, [export], buf), polys


@pytest.mark.parametrize("node_ref", _STACKS)
def test_upolys_body_is_entered_past_any_state_frame(node_ref):
    """A `Polys` body is entered through the StateFrame skip, decided on the EXPORT's flags.

    Why this is pinned. An object body begins with an `FStateFrame` — the UnrealScript execution
    state — exactly when that export's flags word carries `RF_HasStack` (`0x02000000`). It is
    natural to assume only ACTORS are affected, since an actor is the thing that runs
    UnrealScript, and to enter a plain data object's body at its raw serial offset. That
    assumption is wrong: in retail Deus Ex maps a minority of `Model` and `Polys` exports — pure
    data, no script — carry the flag too. Measured over the first twelve `DX/Maps/*.dx`
    (2026-07-27): 21 flagged `Model` exports and the matching 21 `Polys`, 13 of them in
    `00_TrainingCombat.dx` alone.

    Entering at the raw offset on one of those desyncs by the StateFrame's length. It is not a
    quiet wrong answer — `decode_upolys`' consume-to-EOF check turns it into an error — but it
    made `00_Training.dx` fail to import at all. Evidence:
    `dev/docs/unrealed/package-format.md` "`RF_HasStack` is a per-EXPORT flag, not an 'is it an
    actor?' flag".

    The frame's trailing `Offset` field is serialized only when `Node` is non-zero, so both
    variants are covered: getting that condition wrong shifts the body by one compact index.
    """
    pkg, written = _polys_pkg(node_ref)

    decoded = mapimport.decode_upolys(pkg, 0)

    assert len(decoded) == len(written)
    assert decoded[0].verts == written[0].verts
    assert decoded[0].poly_flags == written[0].poly_flags
    assert decoded[0].item_index == written[0].item_index
    # And the label survives the whole way to the model object the emitter renders.
    assert mapimport.polygon_of(pkg, decoded[0]).item == "Base"


@pytest.mark.parametrize("node_ref", _STACKS)
def test_brush_model_body_is_entered_past_any_state_frame(node_ref):
    """A brush's private `UModel` body is entered the same way, for the same reason.

    `brush_of` walks `Brush=` → a private `UModel` → that model's `Polys` reference → the polygon
    list. The `UModel` half has the identical trap: `parse_model_body` parses to EOF and fails
    outright when it starts one StateFrame early, which is how `00_Training.dx` surfaced this as
    `brush_of: corrupt map body (IndexError…)` on `Brush41`/`Brush42`. With the skip applied,
    `parse_model_body` reaches EOF on 21 of 21 flagged retail models.

    Both the model export and the polys export are flagged together here — retail maps flag a
    brush model and its polygon list as a PAIR (the counts always match, per the census).
    """
    names = ["None", "Model", "Polys", "Base"]
    polys = [FPoly(verts=_square(), item_index=3, texture_ref=0)]
    stack = _stack(node_ref)
    flags = 0 if node_ref is None else RF_HasStack

    polys_body = stack + write_upolys_body(_names_index(names), polys)
    # `Polys` is export 2 (1-based ref 2); the model points at it via `field_0x54`.
    model_body = stack + write_model_body(Model(field_0x54=2, none_index=0))

    buf = bytearray(b"\x00" * 8)
    model_soff = len(buf); buf += model_body
    polys_soff = len(buf); buf += polys_body
    exports = [
        dict(cls=0, sup=0, outer=0, nm=1, flags=flags, ssize=len(model_body), soff=model_soff),
        dict(cls=0, sup=0, outer=0, nm=2, flags=flags, ssize=len(polys_body), soff=polys_soff),
    ]
    pkg = _pkg(names, exports, bytes(buf))

    brush = mapimport.brush_of(pkg, 1)          # 1-based ref to the Model export

    assert brush.model_name == "Model"
    assert len(brush.polys) == 1
    assert brush.polys[0].item == "Base"
    assert len(brush.polys[0].vertices) == 4

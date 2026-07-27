"""Sweep the RETAIL map corpus through `level import`'s decoder.

Skips entirely when the corpus is absent, which it is on any machine that has not had a Deus Ex copy
installed into the substrate tree (`dev/scripts/install-deusex-assets.sh --with-maps`). Retail maps
are copyrighted and gitignored, so they can never be committed — this test is how they get used as
evidence anyway: it costs nothing where they are missing and covers the whole corpus where they exist.

**What this closes, and what it does not.** The committed fixtures
(`uedcli/tests/test_mapimport_import.py`) are three small editor-built maps; a shipped mission is
several thousand times larger and exercises property types, class variety, brush counts and
`RF_HasStack` placements the fixtures never touch. Sweeping them proves the decoder survives real
content and that its own integrity gates hold. It does NOT compare against the official exporter's
output — that needs the UnrealEd container as an oracle and is the remaining `p1` item on
`dev/docs/board/inbox/`.

Runtime scales with the corpus (a 2000-actor map decodes to megabytes of T3D), so the sweep is capped
at `UEDCLI_CORPUS_MAPS` maps (default 6; `all` or `0` for the whole corpus). A cap raises a WARNING
naming how many maps went uncovered, because pytest hides skip reasons by default and a bounded run
that looks green otherwise reads as full coverage.
"""
from __future__ import annotations

import functools
import os
import warnings
from pathlib import Path

import pytest

from uedcli import mapimport, model, normalize
from uedcli.classindex import ClassIndex
from uedcli.tests.conftest import install_root
from uedcli.upackage import load_package

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
# Classes come from the GAME's own `System/` when the corpus is present, not from the committed v69
# editor packages. They genuinely disagree: `Engine.CameraPoint` is an `Engine.Actor` descendant in
# the game's v68 `Engine.u` (CameraPoint → Keypoint → Actor → Object) and is UNKNOWN to UED22's v69
# one, so resolving retail maps against UED22 makes two Endgame maps look like decode failures when
# the decoder is right. Production resolves against the project's composed path, which includes the
# game — so using the game here matches it.
_GAME_SYSTEM = install_root() / "System"
_CLASSES = _GAME_SYSTEM if (_GAME_SYSTEM / "Engine.u").is_file() else _UED22
_CAP_ENV = "UEDCLI_CORPUS_MAPS"


def _cap() -> int:
    """How many corpus maps to sweep; `0` means all. Default 6.

    Parsed defensively because this runs at IMPORT time, before any skip can apply: a bad value used
    to raise `ValueError` during collection and abort the WHOLE session, including every unrelated
    test file in the same run. `all` is the obvious thing to type given `0` means no cap, so it is
    accepted rather than punished.
    """
    raw = (os.environ.get(_CAP_ENV) or "").strip()
    if not raw:
        return 6
    if raw.casefold() in ("all", "0", "-1"):
        return 0
    if raw.isdigit():
        return int(raw)
    warnings.warn(f"{_CAP_ENV}={raw!r} is not a number or 'all' — sweeping the default 6 maps",
                  stacklevel=2)
    return 6


def _corpus() -> list[Path]:
    maps_dir = install_root() / "Maps"
    if not maps_dir.is_dir():
        return []
    return sorted(p for p in maps_dir.glob("*.dx") if p.is_file())


_ALL = _corpus()
_CAPPED = _cap()
_MAPS = _ALL if _CAPPED <= 0 else _ALL[:_CAPPED]

# A capped sweep is announced as a WARNING, not just a skip reason. pytest prints skip reasons only
# under `-rs`/`-ra`, which `pytest.ini` does not set — so on a 100-map corpus a default `bin/test`
# showed `6 passed, 1 skipped` and nothing said 94 maps went uncovered. Warnings DO appear in the
# default summary, which is the point: `CLAUDE.md` forbids a cap that reads as full coverage.
if _ALL and len(_MAPS) < len(_ALL):
    warnings.warn(
        f"retail-corpus sweep covers {len(_MAPS)} of {len(_ALL)} maps — "
        f"{len(_ALL) - len(_MAPS)} NOT decoded (set {_CAP_ENV}=all for the whole corpus)",
        stacklevel=1)

pytestmark = [
    pytest.mark.skipif(not _ALL, reason=f"no retail map corpus at {install_root() / 'Maps'} "
                                        "(user-supplied + gitignored; see "
                                        "dev/docs/deusex-assets-setup.md)"),
    pytest.mark.skipif(not (_CLASSES / "Engine.u").is_file(),
                       reason="no Engine.u in the game System/ or the committed UED22 tree"),
]


def _resolver(name: str) -> str | None:
    p = _CLASSES / f"{name}.u"
    return str(p) if p.is_file() else None


@functools.lru_cache(maxsize=None)
def _index() -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in _CLASSES.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


@functools.lru_cache(maxsize=None)
def _decode(dx: Path) -> tuple[model.Level, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """One map decoded → `(level after the scratch drop, dropped names, dropped classes, face
    labels)`.

    Cached so the whole-corpus checks reuse the per-map decode instead of paying for it twice: a
    retail map is megabytes of T3D and the decode is the expensive part.
    """
    pkg = load_package(str(dx), name=dx.stem)
    text = mapimport.import_map(pkg, _index(), mapimport.ImportSchema(resolver=_resolver))
    level = model.parse_t3d(text)
    labels = {p.item for a in level.actors.values() if a.brush is not None
              for p in a.brush.polys if p.item}
    # Classes are read BEFORE the drop, so what was removed can be asserted rather than assumed.
    classes = {n: (a.cls or "").rsplit(".", 1)[-1] for n, a in level.actors.items()}
    dropped = mapimport.drop_editor_scratch(level)
    return level, tuple(dropped), tuple(classes[n] for n in dropped), tuple(sorted(labels))


def test_the_sweep_reports_what_it_left_out():
    """The cap is announced, so a green run is never mistaken for full coverage.

    The announcement itself is a module-level `warnings.warn` (visible in pytest's default summary,
    unlike a skip reason). This test only guards the invariant that the cap selected something —
    a cap of, say, 0 maps would otherwise make every sweep below vacuously absent.
    """
    assert _MAPS, f"the corpus holds {len(_ALL)} map(s) but the cap selected none"
    assert len(_MAPS) <= len(_ALL)


@pytest.mark.parametrize("dx", _MAPS, ids=lambda p: p.stem)
def test_a_retail_map_decodes_and_round_trips(dx):
    """One shipped mission: decode → parse → drop scratch → re-emit, all clean.

    Every assertion here is something a decode can plausibly get wrong on real content while passing
    on a small fixture:

    * it decodes at all — no truncated body, no unhandled property type, no desync;
    * the emitted text parses back, and every actor named by the level's own order array arrives;
    * only editor apparatus is dropped, and real content survives;
    * re-emitting through the canonical emitter is a fixed point, so an imported tree would not
      churn on its first unrelated edit.
    """
    pkg = load_package(str(dx), name=dx.stem)
    text = mapimport.import_map(pkg, _index(), mapimport.ImportSchema(resolver=_resolver))
    parsed = model.parse_t3d(text)

    # The decode's own integrity gates already refuse a partial result, so reaching here means the
    # Actors array and every actor body were fully consumed. Check the text survives the parser too.
    ordered = model.parse_t3d_actors(text)
    assert len(ordered) == len(parsed.actors), (
        f"{dx.name}: {len(ordered) - len(parsed.actors)} actor name(s) collide, so the level dict "
        "silently dropped some — import would report success having lost content")
    assert next(iter(parsed.actors.values())).cls == "LevelInfo", \
        f"{dx.name}: Actors[0] is not the LevelInfo singleton — the order array was misaligned"

    level, dropped, dropped_classes, _labels = _decode(dx)
    assert level.actors, f"{dx.name}: every actor was dropped as editor scratch"
    assert not any(a.cls.rsplit(".", 1)[-1] == "Camera" for a in level.actors.values())
    # Only apparatus went: every dropped actor was a Camera or a Brush (the builder brush). Without
    # checking the CLASSES of what was removed, "the scratch drop worked" is satisfied by a map that
    # simply had no cameras — and a drop that ate real content would pass too.
    assert set(dropped_classes) <= {"Camera", "Brush"}, (
        f"{dx.name}: the scratch drop removed {sorted(set(dropped_classes) - {'Camera', 'Brush'})} "
        "— those are content classes, not editor apparatus")
    # No assertion on the kept/dropped RATIO: a small map is mostly apparatus (the three committed
    # fixtures drop 6-7 and keep 3), so "kept > dropped" holds only for real missions and would be a
    # false invariant. What matters is WHAT went, which the class check above pins.

    once = {n: normalize.canonical_actor_t3d(a) for n, a in level.actors.items()}
    again = model.parse_t3d("Begin Map\n" + "\n".join(once.values()) + "\nEnd Map\n")
    assert {n: normalize.canonical_actor_t3d(a) for n, a in again.actors.items()} == once, \
        f"{dx.name}: re-emitting the decoded level is not a fixed point"

    # A shipped mission always carries real brush geometry; zero would mean the model→Polys chain
    # silently produced empty brushes (which uedcli's OWN native builder does, but the editor's
    # maps never do).
    brushes = [a for a in level.actors.values() if a.brush is not None]
    assert brushes, f"{dx.name}: no brush actors at all"
    assert any(a.brush.polys for a in brushes), \
        f"{dx.name}: every brush decoded with an EMPTY polygon list — the UPolys chain is broken"


def test_named_faces_appear_across_the_corpus():
    """`Item=OUTSIDE` — the editor's default face label — survives the decode on real maps.

    The corpus-scale form of the name-table trap: `OUTSIDE` sits at name index 0 in these packages,
    and a decoder that treats index 0 as "unset" deletes every occurrence with no error. On the
    committed fixtures that is a handful of faces; across a mission it is thousands, so its absence
    is unmistakable.

    Covers every map the sweep covers (the decode is cached, so this costs nothing extra) — not a
    silent sub-sample, which would undercut the very point of the cap warning.
    """
    labels: set[str] = set()
    for dx in _MAPS:
        labels.update(_decode(dx)[3])

    assert labels, f"no polygon across {len(_MAPS)} retail map(s) carries ANY Item= label"
    assert "OUTSIDE" in labels, (
        f"no polygon across {len(_MAPS)} retail map(s) carries Item=OUTSIDE — name-table index 0 is "
        "being treated as 'unset' again (dev/docs/unrealed/package-format.md)")

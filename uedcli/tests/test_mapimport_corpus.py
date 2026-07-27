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
`dev/docs/board/inbox.md`.

Runtime scales with the corpus (a 2000-actor map decodes to megabytes of T3D), so the sweep is capped
and reports what it skipped rather than silently sampling — set `UEDCLI_CORPUS_MAPS=0` for all of them.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from uedcli import mapimport, model, normalize
from uedcli.classindex import ClassIndex
from uedcli.tests.conftest import install_root
from uedcli.upackage import load_package

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
# 0 = no cap. The default keeps a full-suite run to a few seconds per map while still crossing
# several missions; the corpus is ~100 maps and decoding all of them takes minutes.
_CAP = int(os.environ.get("UEDCLI_CORPUS_MAPS", "6"))


def _corpus() -> list[Path]:
    maps_dir = install_root() / "Maps"
    if not maps_dir.is_dir():
        return []
    return sorted(p for p in maps_dir.glob("*.dx") if p.is_file())


_ALL = _corpus()
_MAPS = _ALL if _CAP <= 0 else _ALL[:_CAP]

pytestmark = [
    pytest.mark.skipif(not _ALL, reason=f"no retail map corpus at {install_root() / 'Maps'} "
                                        "(user-supplied + gitignored; see "
                                        "dev/docs/deusex-assets-setup.md)"),
    pytest.mark.skipif(not (_UED22 / "Engine.u").is_file(),
                       reason="committed UED22/Engine.u not present"),
]


def _resolver(name: str) -> str | None:
    p = _UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


@pytest.fixture(scope="module")
def index() -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


def test_the_sweep_reports_what_it_left_out():
    """A capped sweep says so, so a green run is never mistaken for full coverage.

    `CLAUDE.md` forbids a silent cap: bounding coverage and not saying it reads as "everything
    passed". If this is the only signal you have, note the number.
    """
    left_out = len(_ALL) - len(_MAPS)
    assert _MAPS, "the corpus was found but the cap selected nothing"
    if left_out:
        pytest.skip(f"sweeping {len(_MAPS)} of {len(_ALL)} corpus maps "
                    f"({left_out} not covered; set UEDCLI_CORPUS_MAPS=0 for all)")


@pytest.mark.parametrize("dx", _MAPS, ids=lambda p: p.stem)
def test_a_retail_map_decodes_and_round_trips(dx, index):
    """One shipped mission: decode → parse → drop scratch → re-emit, all clean.

    Every assertion here is something a decode can plausibly get wrong on real content while passing
    on a small fixture:

    * it decodes at all — no truncated body, no unhandled property type, no desync;
    * the emitted text parses back, and every actor named by the level's own order array arrives;
    * re-emitting through the canonical emitter is a fixed point, so an imported tree would not
      churn on its first unrelated edit;
    * the editor's scratch objects are gone and real content is not.
    """
    pkg = load_package(str(dx), name=dx.stem)
    schema = mapimport.ImportSchema(resolver=_resolver)

    text = mapimport.import_map(pkg, index, schema)
    level = model.parse_t3d(text)

    # The decode's own integrity gates already refuse a partial result, so reaching here means the
    # Actors array and every actor body were fully consumed. Check the text survives the parser too.
    ordered = model.parse_t3d_actors(text)
    assert len(ordered) == len(level.actors), (
        f"{dx.name}: {len(ordered) - len(level.actors)} actor name(s) collide, so the level dict "
        "silently dropped some — import would report success having lost content")
    assert next(iter(level.actors.values())).cls == "LevelInfo", \
        f"{dx.name}: Actors[0] is not the LevelInfo singleton — the order array was misaligned"

    dropped = mapimport.drop_editor_scratch(level)
    assert level.actors, f"{dx.name}: every actor was dropped as editor scratch"
    assert not any(a.cls.rsplit(".", 1)[-1] == "Camera" for a in level.actors.values())

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
    print(f"{dx.name}: {len(level.actors)} actors kept, {len(dropped)} scratch dropped, "
          f"{sum(len(a.brush.polys) for a in brushes)} polys")


def test_named_faces_appear_across_the_corpus(index):
    """`Item=OUTSIDE` — the editor's default face label — survives the decode on real maps.

    This is the corpus-scale form of the name-table trap: `OUTSIDE` sits at name index 0 in these
    packages, and a decoder that treats index 0 as "unset" deletes every occurrence with no error.
    On the committed fixtures that is a handful of faces; here it is thousands, and its absence
    across a whole mission is unmistakable.
    """
    labels: set[str] = set()
    for dx in _MAPS[:2]:
        pkg = load_package(str(dx), name=dx.stem)
        text = mapimport.import_map(pkg, index, mapimport.ImportSchema(resolver=_resolver))
        for a in model.parse_t3d(text).actors.values():
            if a.brush is not None:
                labels.update(p.item for p in a.brush.polys if p.item)
    assert "OUTSIDE" in labels, (
        "no polygon in the sampled retail maps carries Item=OUTSIDE — name-table index 0 is being "
        "treated as 'unset' again (dev/docs/unrealed/package-format.md)")

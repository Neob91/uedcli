"""Regression for this spike's finding: UED22 identifies the builder brush by ARRAY POSITION
(`ULevel.Actors[1]`), not by the content heuristic `uedcli.normalize.is_builder_brush` currently
uses (`Class=Brush` + inner model name `Brush` + no `CsgOper`). See `../spike.md`.

Standalone (not part of the `uedcli` package's own suite -- this is a research spike; production
code is untouched per this task's scope). Run directly:

    python3 -m pytest dev/docs/spikes/2026-09-15-builder-brush-is-actors1-not-a-content-heuristic/harness/test_builder_brush_is_position_not_content.py -v

Uses SYNTHETIC T3D fixtures, not real extracted Deus Ex level content (`dev/games/` is gitignored
copyrighted game content and must never be committed -- see the repo's own `.gitignore`). The
synthetic actors below reproduce the exact real-world shape this spike found (a `Class=Engine.Brush`
actor with no `CsgOper=` line whose inner Brush model is named plain `Model`, not the reserved
`Brush` singleton `is_builder_brush` requires) without embedding any actual game geometry, texture
refs, or tags copied from the real `showcase_unatcohq`/`showcase_island` trunks this spike surveyed
(see `survey_output.txt` for the real, aggregate, non-content findings: actor names, classes, and
LexoRank positions only).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Reach the real `uedcli.normalize.is_builder_brush` -- read-only, never modified by this spike.
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT))

from uedcli import model  # noqa: E402
from uedcli.normalize import is_builder_brush  # noqa: E402

# A synthetic stand-in for a real stray builder brush: `Class=Brush`, no `CsgOper=` line, and an
# inner model named plain `Model` (not the reserved unnumbered `Brush` the current predicate
# requires) -- exactly the shape this spike found on `Brush74` (`showcase_unatcohq`) and `Brush296`
# (`showcase_island`), minus any real geometry/texture/tag content from those actual trunks.
_SYNTHETIC_STRAY_BUILDER_BRUSH_T3D = """\
Begin Actor Class=Engine.Brush Name=SyntheticStrayBrush
    Location=(X=100.000000,Y=200.000000,Z=300.000000)
    Begin Brush Name=Model
       Begin PolyList
         Begin Polygon Item=OUTSIDE
         Origin   +00000.000000,+00000.000000,+00000.000000
         Normal   +00000.000000,+00000.000000,+00001.000000
         TextureU +00001.000000,+00000.000000,+00000.000000
         TextureV +00000.000000,+00001.000000,+00000.000000
         Vertex   -00016.000000,-00016.000000,+00000.000000
         Vertex   +00016.000000,-00016.000000,+00000.000000
         Vertex   +00016.000000,+00016.000000,+00000.000000
         Vertex   -00016.000000,+00016.000000,+00000.000000
         End Polygon
       End PolyList
    End Brush
    Brush=Model'MyLevel.Model'
    Name="SyntheticStrayBrush"
End Actor
"""

# An ordinary, real, CsgOper-bearing content brush -- what `is_builder_brush` must NOT match, at
# any position, including the one immediately after the stray brush above (mirroring the real
# trunks' own `Brush82`/`Brush570`-etc. immediately following `Brush74`/`Brush296`).
_ORDINARY_CONTENT_BRUSH_T3D = """\
Begin Actor Class=Engine.Brush Name=OrdinaryContentBrush
    CsgOper=CSG_Subtract
    Location=(X=0.000000,Y=0.000000,Z=0.000000)
    Begin Brush Name=Model
       Begin PolyList
         Begin Polygon Item=OUTSIDE
         Origin   +00000.000000,+00000.000000,+00000.000000
         Normal   +00000.000000,+00000.000000,+00001.000000
         TextureU +00001.000000,+00000.000000,+00000.000000
         TextureV +00000.000000,+00001.000000,+00000.000000
         Vertex   -00064.000000,-00064.000000,+00000.000000
         Vertex   +00064.000000,-00064.000000,+00000.000000
         Vertex   +00064.000000,+00064.000000,+00000.000000
         Vertex   -00064.000000,+00064.000000,+00000.000000
         End Polygon
       End PolyList
    End Brush
    Brush=Model'MyLevel.Model'
    Name="OrdinaryContentBrush"
End Actor
"""


def _parse_one_actor(t3d_body: str) -> model.Actor:
    level = model.parse_t3d(f"Begin Map\n{t3d_body}End Map\n")
    (actor,) = level.actors.values()
    return actor


def test_current_heuristic_misses_a_real_shaped_stray_builder_brush():
    """Pins the BUG: the current content predicate returns False for an actor with the exact shape
    this spike found on real content (`Brush74`/`Brush296`) -- no `CsgOper`, inner model plainly
    named `Model`. This must keep failing until `is_builder_brush` is actually fixed; if this test
    ever starts passing, `spike.md`'s finding needs re-checking, not silent deletion of this test.
    """
    actor = _parse_one_actor(_SYNTHETIC_STRAY_BUILDER_BRUSH_T3D)
    assert actor.brush is not None
    assert actor.brush.model_name == "Model", \
        "fixture drifted from the real-world shape this spike found"
    assert is_builder_brush(actor) is False, (
        "is_builder_brush unexpectedly matched -- either the predicate was already fixed "
        "(update this spike/finding) or this fixture no longer reproduces the real shape"
    )


def test_ordinary_content_brush_is_never_matched():
    """Sanity: an ordinary CsgOper-bearing brush is correctly never flagged, by the current
    predicate OR by the proposed positional one below."""
    actor = _parse_one_actor(_ORDINARY_CONTENT_BRUSH_T3D)
    assert is_builder_brush(actor) is False
    assert _is_builder_brush_by_position(["LevelInfo0", "SyntheticStrayBrush",
                                          "OrdinaryContentBrush"], "OrdinaryContentBrush") is False


def _is_builder_brush_by_position(order: list[str], name: str) -> bool:
    """The PROPOSED fix, reimplemented here (not in `uedcli/normalize.py` -- production code is
    untouched by this spike): the builder brush is whichever actor sits at position 1 in the
    level's order, immediately after the `LevelInfo` singleton at position 0 -- mirroring
    `ULevel::Brush() == (ABrush*)Actors(1)`. No property inspection at all."""
    return len(order) > 1 and order[1] == name


def test_positional_rule_correctly_identifies_the_stray_brush_content_check_misses():
    """The proposed fix catches exactly what the current predicate misses, using ONLY position --
    no Class, no CsgOper, no model-name check."""
    order = ["LevelInfo0", "SyntheticStrayBrush", "OrdinaryContentBrush"]
    assert _is_builder_brush_by_position(order, "SyntheticStrayBrush") is True
    assert _is_builder_brush_by_position(order, "OrdinaryContentBrush") is False
    assert _is_builder_brush_by_position(order, "LevelInfo0") is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

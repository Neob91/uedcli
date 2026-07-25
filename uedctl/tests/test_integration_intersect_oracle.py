"""Live-editor ORACLE for `brush intersect`/`brush deintersect` — regeneration + differential.

Deselected by default (`pytest.ini`: `addopts = -m "not integration"`).  Run with:

    bin/test uedctl/tests/test_integration_intersect_oracle.py -m integration -v

For every case in `intersect_cases.CASES` this drives the REAL UnrealEd
(`BRUSH FROM INTERSECTION`/`DEINTERSECTION`, `editor_oracle.py`), writes the result to
`fixtures/intersect/<case>.t3d`, and diffs the NATIVE merge against it in WORLD space.

The committed fixtures are the standing offline bar (`test_brush_merge.py`); this module is how
they are re-derived when the algorithm or a case changes.  It is NOT part of the default gate: the
editor needs the live `dx-lum-uned` container and wedges silently when it fails
(`unrealed/quirks.md` "Stability").
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from uedctl import config
from uedctl.tests import editor_oracle, intersect_cases
from uedctl.tests.merge_compare import FIXTURES, native_faces, oracle_faces, assert_same_faces

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def state_dir(tmp_path_factory):
    proj = tmp_path_factory.mktemp("oracleproj")
    (proj / "uedctl.toml").write_text('game = "deusex"\n')
    return config.state_dir(proj, create=True)


@pytest.mark.parametrize("case_id", sorted(intersect_cases.CASES))
def test_native_matches_the_editor(case_id, state_dir):
    """Drive the live editor for this case and diff the native merge against it.

    **Writing the golden is OPT-IN** (`UEDCTL_REGEN_GOLDENS=1`).  Rewriting the tracked fixture on
    every run would mean a run where the editor wedged or produced garbage silently becomes the new
    "oracle" — the pinned fact would move under us instead of tripping a red test, which is the
    opposite of what the committed goldens are for.  Default is compare-only, so this doubles as an
    audit that the committed fixtures still reflect what UnrealEd does.
    """
    case = intersect_cases.CASES[case_id]
    actors = intersect_cases.build_actors(case_id)

    t3d = editor_oracle.run(case["verb"], actors, state_dir=state_dir)
    if os.environ.get("UEDCTL_REGEN_GOLDENS"):
        out = FIXTURES / f"{case_id}.t3d"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(t3d)

    assert_same_faces(
        native_faces(case_id),
        oracle_faces(t3d),
        what=f"{case_id} ({case['verb']}): native vs the live editor",
    )

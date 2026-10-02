"""Pins for the advisory BSP-check orchestration — especially the robustness contract:
a check that raises is caught and reported, never propagated (materialize must stay rc 0).
"""
from unittest import mock

import pytest

from uedcli import doctor
from uedcli.bsp import checks as C
from uedcli.bsp.editorlog import BuildLog


def _clean_model(*_a, **_k):
    return object()


@pytest.fixture
def dx(tmp_path):
    """A real (dummy) file so `_built_model_check`'s read succeeds and only the parse is stubbed."""
    p = tmp_path / "Built.dx"
    p.write_bytes(b"not-a-real-package")
    return str(p)


def test_run_bsp_checks_is_silent_when_both_checks_are_clean(monkeypatch, dx):
    monkeypatch.setattr(C, "flush_and_parse_since", lambda *a, **k: BuildLog(final_nodes=6, leaves=1))
    monkeypatch.setattr(C.builtmodel, "load_model_from_dx", _clean_model)
    monkeypatch.setattr(C.builtmodel, "analyze_built", lambda m: [])
    assert C.run_bsp_checks(mock.Mock(), log_offset=100, dx_path=dx) == []


def test_run_bsp_checks_reports_both_findings_under_a_header(monkeypatch, dx):
    monkeypatch.setattr(C, "flush_and_parse_since",
                        lambda *a, **k: BuildLog(unlinked_tpoints=4))
    monkeypatch.setattr(C.builtmodel, "load_model_from_dx", _clean_model)
    monkeypatch.setattr(C.builtmodel, "analyze_built", lambda m: [doctor.Finding(
        severity=doctor.Severity.WARN, category="degenerate", brush="(built BSP)",
        coord=(1.0, 2.0, 3.0), message="BSP node 7 (surf 3) has ~zero area",
        symptom="phantom/sliver node — an invisible wall", fix="give it real area")])
    lines = C.run_bsp_checks(mock.Mock(), log_offset=100, dx_path=dx)
    assert lines[0] == "materialize: BSP health check (advisory; build succeeded):"
    joined = "\n".join(lines)
    assert "4 unlinked T-junction side(s) (HoM crack)" in joined
    assert "[WARN ] degenerate @(1.0, 2.0, 3.0): BSP node 7 (surf 3) has ~zero area" in joined


def test_a_raising_build_output_check_yields_a_skip_note_not_an_exception(monkeypatch, dx):
    monkeypatch.setattr(C, "flush_and_parse_since",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("editor wedged")))
    monkeypatch.setattr(C.builtmodel, "load_model_from_dx", _clean_model)
    monkeypatch.setattr(C.builtmodel, "analyze_built", lambda m: [])
    lines = C.run_bsp_checks(mock.Mock(), log_offset=100, dx_path=dx)
    assert lines == ["materialize: BSP health check (advisory; build succeeded):",
                     "  build-output check skipped (RuntimeError: editor wedged)"]


def test_a_raising_built_model_check_yields_a_skip_note_not_an_exception(monkeypatch, dx):
    monkeypatch.setattr(C, "flush_and_parse_since", lambda *a, **k: BuildLog())
    monkeypatch.setattr(C.builtmodel, "load_model_from_dx",
                        lambda b: (_ for _ in ()).throw(ValueError("no Model export found in the saved map")))
    lines = C.run_bsp_checks(mock.Mock(), log_offset=100, dx_path=dx)
    assert lines == ["materialize: BSP health check (advisory; build succeeded):",
                     "  built-model check skipped (ValueError: no Model export found in the saved map)"]


def test_a_missing_log_offset_skips_only_the_build_output_check(monkeypatch, dx):
    monkeypatch.setattr(C.builtmodel, "load_model_from_dx", _clean_model)
    monkeypatch.setattr(C.builtmodel, "analyze_built", lambda m: [])
    lines = C.run_bsp_checks(mock.Mock(), log_offset=None, dx_path=dx)
    assert lines == ["materialize: BSP health check (advisory; build succeeded):",
                     "  build-output check skipped (could not read the editor log offset)"]

"""Offline pins for the build-output (editor-rebuild-log) BSP check."""
from unittest import mock

from uedcli.bsp import editorlog as E


def test_it_parses_every_drop_channel_with_counts():
    text = (
        "FPoly::CalcNormal: Zero-area polygon\n"
        "FPoly::CalcNormal: Zero-area polygon\n"
        "FPoly::Finalize: Not enough vertices (2)\n"
        "BspValidateBrush linked 5 of 6 polys\n"
        "bspAddNode: Infinitesimal polygon 3 (7)\n"
        "Processed 20 T-points, linked: 16/20 sides\n"
        "Nodes: 40 -> 38\n"
        "Portalized: built 2 leaves, 38 nodes\n"
    )
    log = E.parse_build_log(text)
    assert log.zero_area_drops == 2
    assert log.few_vert_drops == (2,)
    assert log.unwatertight == ((5, 6),)
    assert log.infinitesimal_nodes == 1
    assert log.unlinked_tpoints == 4              # 20 sides − 16 linked
    assert log.final_nodes == 38
    assert log.leaves == 2
    assert log.has_drops is True
    assert log.findings() == [
        "2 zero-area face(s) dropped (hole/HOM)",
        "face dropped: only 2 vertices after cleanup (hole/HOM)",
        "brush not watertight: linked 5 of 6 polys (leak/hole)",
        "4 unlinked T-junction side(s) (HoM crack)",
        "1 infinitesimal node(s) (invisible-wall candidate)",
    ]


def test_it_reports_a_clean_linked_6_of_6_as_no_findings():
    log = E.parse_build_log("BspValidateBrush linked 6 of 6 polys\nNodes: 6 -> 6\n"
                            "Portalized: built 1 leaves, 6 nodes\n")
    assert log.unwatertight == ()                 # linked == total is NOT a leak
    assert log.has_drops is False
    assert log.has_holes_or_hom is False
    assert log.findings() == []
    assert (log.final_nodes, log.leaves) == (6, 1)


def test_flush_and_parse_since_forces_a_flush_then_reads_the_slice(monkeypatch):
    monkeypatch.setattr(E.time, "sleep", lambda *_: None)
    driver = mock.Mock()
    driver.read_log_since.return_value = "Processed 12 T-points, linked: 9/12 sides\n"
    log = E.flush_and_parse_since(driver, 4096)
    assert log.unlinked_tpoints == 3
    driver.dismiss_blocking_dialog.assert_called_once_with()
    driver.exec.assert_called_once_with("OBJ LIST CLASS=Class")   # the buffer-flush nudge
    driver.read_log_since.assert_called_once_with(4096)           # reads from the recorded offset

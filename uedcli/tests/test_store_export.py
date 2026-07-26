from unittest import mock

from uedcli import store_export
from uedcli.normalize import canonical_actor_t3d


def test_export_dx_t3d_exports_into_a_uuid_work_dir_then_cleans_up():
    with mock.patch("uedcli.store_export.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout="Begin Map\nEnd Map", returncode=0, stderr="")
        store_export.export_dx_t3d("ct", "/work/snap.dx")
    mkdir_outdir = run.call_args_list[0].args[0][-1]    # ["docker","exec",c,"mkdir","-p",OUTDIR]
    assert mkdir_outdir.startswith("/work/ucc_export-")  # uuid-suffixed /work path (spec B4)
    cleanup = run.call_args_list[-1].args[0]
    assert cleanup[:5] == ["docker", "exec", "ct", "rm", "-rf"]   # xfer.remove cleans the outdir
    assert cleanup[5] == mkdir_outdir


def test_export_dx_t3d_bounds_every_docker_call():
    """An unbounded `docker exec` parks `level materialize`/the post-verify forever when wine or
    dockerd wedges (dev/docs/rules/background-work.md). Pinned per call site."""
    with mock.patch("uedcli.store_export.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout="Begin Map\nEnd Map", returncode=0, stderr="")
        store_export.export_dx_t3d("ct", "/work/snap.dx")
    for call in run.call_args_list:
        assert call.kwargs.get("timeout"), call


def test_export_dx_t3d_removes_the_work_dir_even_when_the_export_fails():
    """The `/work/ucc_export-<uuid>` tree used to be stranded whenever the export raised, because
    the cleanup sat after the last call instead of in a `finally:`."""
    import subprocess
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if any("UCC.exe" in part for part in cmd):
            raise subprocess.CalledProcessError(1, cmd)
        return mock.Mock(stdout="", returncode=0, stderr="")

    with mock.patch("uedcli.store_export.subprocess.run", fake_run):
        try:
            store_export.export_dx_t3d("ct", "/work/snap.dx")
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError("expected the export failure to propagate")
    outdir = calls[0][-1]
    assert calls[-1][:5] == ["docker", "exec", "ct", "rm", "-rf"] and calls[-1][5] == outdir


def test_export_dx_t3d_turns_a_wedged_ucc_into_a_named_driver_error():
    import subprocess
    from uedcli.driver import DriverError
    import pytest

    def fake_run(cmd, **kw):
        if any("UCC.exe" in part for part in cmd):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 0))
        return mock.Mock(stdout="", returncode=0, stderr="")

    with mock.patch("uedcli.store_export.subprocess.run", fake_run):
        with pytest.raises(DriverError, match="UCC batchexport"):
            store_export.export_dx_t3d("ct", "/work/snap.dx")


_DX_T3D = ("Begin Map\nBegin Actor Class=Brush Name=B\n"
           "    Brush=Model'ondisk.Model1'\n    Name=\"B\"\nEnd Actor\n"
           "Begin Actor Class=Light Name=L\n    Name=\"L\"\nEnd Actor\nEnd Map")


def test_export_dx_level_parses_captures_order_and_canonicalizes(monkeypatch):
    monkeypatch.setattr(store_export, "export_dx_t3d", lambda container, dx_path: _DX_T3D)
    level = store_export.export_dx_level("ct", "/repo/Maps/x.dx")
    assert level.order == ["B", "L"]                 # full order captured pre-normalize
    assert set(level.actors) == {"B", "L"}
    assert "MyLevel.Model1" in canonical_actor_t3d(level.actors["B"])   # M2 applied downstream

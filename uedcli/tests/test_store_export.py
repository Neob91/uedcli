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


_DX_T3D = ("Begin Map\nBegin Actor Class=Brush Name=B\n"
           "    Brush=Model'ondisk.Model1'\n    Name=\"B\"\nEnd Actor\n"
           "Begin Actor Class=Light Name=L\n    Name=\"L\"\nEnd Actor\nEnd Map")


def test_export_dx_level_parses_captures_order_and_canonicalizes(monkeypatch):
    monkeypatch.setattr(store_export, "export_dx_t3d", lambda container, dx_path: _DX_T3D)
    level = store_export.export_dx_level("ct", "/repo/Maps/x.dx")
    assert level.order == ["B", "L"]                 # full order captured pre-normalize
    assert set(level.actors) == {"B", "L"}
    assert "MyLevel.Model1" in canonical_actor_t3d(level.actors["B"])   # M2 applied downstream

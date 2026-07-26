from unittest import mock

from uedcli import xfer


def test_it_mints_a_uuid_suffixed_work_path_with_the_given_extension():
    p1 = xfer.work_path("t3d")
    p2 = xfer.work_path("t3d")
    assert p1.startswith("/work/") and p1.endswith(".t3d")
    assert p1 != p2                                  # uuid-unique (spec B4)


def test_it_mints_a_work_dir_uuid_suffixed():
    d = xfer.work_dir("ucc_export")
    assert d.startswith("/work/ucc_export-") and "." not in d.rsplit("/", 1)[-1]


def test_cp_in_copies_host_to_a_minted_work_path_and_returns_raw_posix():
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        cpath = xfer.cp_in("c1", "/host/abs/Map.dx", ext="dx")
    assert cpath.startswith("/work/") and cpath.endswith(".dx")
    run.assert_called_once_with(
        ["docker", "cp", "/host/abs/Map.dx", f"c1:{cpath}"],
        check=True, capture_output=True, text=True)


def test_cp_out_copies_container_path_to_host():
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        xfer.cp_out("c1", "/work/out.dx", "/host/abs/dest.dx")
    run.assert_called_once_with(
        ["docker", "cp", "c1:/work/out.dx", "/host/abs/dest.dx"],
        check=True, capture_output=True, text=True)


def test_remove_is_best_effort_rm_rf_and_never_raises():
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(returncode=1)
        xfer.remove("c1", "/work/a.t3d", "/work/b")           # must not raise
    run.assert_called_once_with(
        ["docker", "exec", "c1", "rm", "-rf", "/work/a.t3d", "/work/b"],
        capture_output=True, text=True, check=False)

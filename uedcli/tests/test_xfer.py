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
        check=True, capture_output=True, text=True, timeout=xfer.CP_TIMEOUT)


def test_cp_out_streams_container_file_to_host_via_docker_exec_cat(tmp_path):
    # `docker cp`-out remounts the container's mounts :ro, which rootless docker cannot do — so
    # cp_out streams the bytes with `docker exec … cat` (stdout redirected to the host file) instead.
    import subprocess
    dest = tmp_path / "dest.dx"
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(returncode=0)
        xfer.cp_out("c1", "/work/out.dx", str(dest))
    run.assert_called_once_with(
        ["docker", "exec", "c1", "cat", "/work/out.dx"],
        check=True, stdout=mock.ANY, stderr=subprocess.PIPE, timeout=xfer.CP_TIMEOUT)


def test_remove_is_best_effort_rm_rf_and_never_raises():
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(returncode=1)
        xfer.remove("c1", "/work/a.t3d", "/work/b")           # must not raise
    run.assert_called_once_with(
        ["docker", "exec", "c1", "rm", "-rf", "/work/a.t3d", "/work/b"],
        capture_output=True, text=True, check=False, timeout=xfer.REMOVE_TIMEOUT)


# ── every docker call is BOUNDED (dev/docs/rules/background-work.md) ──────────────


def test_every_subprocess_call_here_passes_a_timeout(tmp_path):
    """A `docker cp`/`docker exec` with no `timeout=` parks the caller forever when dockerd hangs.
    Pinned as a property of the module rather than per-call, so a new call site cannot slip through
    unbounded."""
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(returncode=0)
        xfer.cp_in("c1", "/host/x.dx", ext="dx")
        xfer.cp_out("c1", "/work/x.dx", str(tmp_path / "y.dx"))
        xfer.remove("c1", "/work/x.dx")
    assert run.call_count == 3
    for call in run.call_args_list:
        assert call.kwargs.get("timeout"), call


def test_a_hung_cp_raises_a_named_driver_error_not_a_subprocess_timeout():
    import subprocess
    from uedcli.driver import DriverError
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.side_effect = subprocess.TimeoutExpired(cmd="docker cp", timeout=xfer.CP_TIMEOUT)
        try:
            xfer.cp_in("c1", "/host/x.dx", ext="dx")
        except DriverError as e:
            assert "docker cp did not finish" in str(e) and "/host/x.dx" in str(e)
        else:
            raise AssertionError("expected DriverError")


def test_a_failed_cp_out_surfaces_dockers_stderr_in_a_named_driver_error(tmp_path):
    import subprocess
    from uedcli.driver import DriverError
    # `docker exec cat` gives bytes stderr (no text=True, since stdout is redirected to the host file).
    err = subprocess.CalledProcessError(1, "docker exec", stderr=b"cat: /work/x.dx: No such file")
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.side_effect = err
        try:
            xfer.cp_out("c1", "/work/x.dx", str(tmp_path / "out.dx"))
        except DriverError as e:
            assert "docker exec cat failed" in str(e) and "No such file" in str(e)
        else:
            raise AssertionError("expected DriverError")


def test_a_hung_remove_is_swallowed_because_cleanup_must_never_hang_the_caller():
    import subprocess
    with mock.patch("uedcli.xfer.subprocess.run", autospec=True) as run:
        run.side_effect = subprocess.TimeoutExpired(cmd="docker exec", timeout=xfer.REMOVE_TIMEOUT)
        xfer.remove("c1", "/work/x")                   # must not raise

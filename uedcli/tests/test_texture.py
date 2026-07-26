from unittest import mock

from uedcli import texture


def test_it_batchexports_by_bare_name_and_cps_each_pcx_out(tmp_path):
    container, package = "dx-lum-uned", "CoreTexMetal"
    host_out = str(tmp_path / "pcx")
    calls = []

    def fake_run(argv, *a, **kw):
        calls.append(argv)
        if "find" in argv:
            return mock.Mock(stdout="/work/tex-abc/Metal.Wall.pcx\n", returncode=0, stderr="")
        return mock.Mock(stdout="", returncode=0, stderr="")

    with mock.patch("subprocess.run", autospec=True, side_effect=fake_run):
        pcxs = texture.batchexport_textures(container, package, host_out)

    assert pcxs == [str(tmp_path / "pcx" / "Metal.Wall.pcx")]       # HOST pcx paths
    # batchexport is invoked with the BARE NAME (UCC resolves it via container Paths) — never
    # "<pkg>.u" (the old bug) and never an extension we guessed
    bx = next(c for c in calls if "batchexport" in c)
    assert "CoreTexMetal" in bx and "CoreTexMetal.u" not in bx and "CoreTexMetal.utx" not in bx
    assert any(c[:2] == ["docker", "cp"] and c[2].startswith(f"{container}:/work/") for c in calls)
    assert any(c[:3] == ["docker", "exec", container] and c[3:5] == ["rm", "-rf"] for c in calls)


def test_it_returns_empty_when_no_pcx_even_on_a_nonzero_batchexport(tmp_path):
    # a textureless/unreachable package: UCC may exit non-zero AND produce no pcx -> [] (not a crash)
    def fake_run(argv, *a, **kw):
        if "batchexport" in argv:
            return mock.Mock(stdout="", returncode=1, stderr="Can't find file")   # check=False
        return mock.Mock(stdout="", returncode=0, stderr="")
    with mock.patch("subprocess.run", autospec=True, side_effect=fake_run):
        assert texture.batchexport_textures("ct", "Empty", str(tmp_path / "e")) == []

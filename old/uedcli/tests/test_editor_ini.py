from unittest import mock

from uedcli import editor


def test_apply_ini_overrides_sets_keys_in_the_right_section():
    base = "\n".join(["[U2Viewport1]", "RendMap=14", "[U2Viewport2]", "RendMap=5",
                      "PctRight=0.650000", "Active=1", "[U2Viewport3]", "RendMap=15"])
    out = editor.apply_ini_overrides(base, {"U2Viewport2": {"RendMap": "6", "PctRight": "1.000000"}})
    lines = out.split("\n")
    assert "[U2Viewport1]" in lines and lines[lines.index("[U2Viewport1]") + 1] == "RendMap=14"  # untouched
    v2 = lines.index("[U2Viewport2]")
    assert "RendMap=6" in lines[v2:v2 + 4] and "PctRight=1.000000" in lines[v2:v2 + 4]
    assert "Active=1" in lines[v2:v2 + 4]                       # non-overridden key kept
    assert lines[lines.index("[U2Viewport3]") + 1] == "RendMap=15"


def test_apply_ini_overrides_preserves_crlf_on_rewritten_lines():
    # the baked ini is CRLF; a rewritten value must KEEP its \r (else wine may ignore it)
    base = "[U2Viewport2]\r\nRendMap=5\r\nActive=1\r\n"
    out = editor.apply_ini_overrides(base, {"U2Viewport2": {"RendMap": "6"}})
    assert "RendMap=6\r" in out                                 # override line keeps CRLF
    assert "Active=1\r" in out                                  # untouched line keeps CRLF
    assert "RendMap=6\n" not in out.replace("\r\n", "\r")       # not a bare-LF line


def test_force_headless_render_device_sets_softdrv_in_engine_section_only():
    # [Engine.Engine]'s three device keys -> SoftDrv; a like-named key in another section is left as
    # is; CRLF is preserved on the rewritten lines (a bare-LF engine ini GPFs wine at boot).
    base = ("[Engine.Engine]\r\nGameRenderDevice=OpenGLDrv.OpenGLRenderDevice\r\n"
            "WindowedRenderDevice=OpenGLDrv.OpenGLRenderDevice\r\n"
            "RenderDevice=GlideDrv.GlideRenderDevice\r\nViewportManager=WinDrv.WindowsClient\r\n"
            "[D3D9Drv.D3D9RenderDevice]\r\nGameRenderDevice=None\r\n").encode("latin-1")
    out = editor._force_headless_render_device(base).decode("latin-1")
    assert "GameRenderDevice=SoftDrv.SoftwareRenderDevice\r\n" in out
    assert "WindowedRenderDevice=SoftDrv.SoftwareRenderDevice\r\n" in out
    assert "RenderDevice=SoftDrv.SoftwareRenderDevice\r\n" in out
    assert "ViewportManager=WinDrv.WindowsClient\r\n" in out            # untouched non-device key
    assert "[D3D9Drv.D3D9RenderDevice]\r\nGameRenderDevice=None\r\n" in out  # other section untouched
    assert "OpenGL" not in out and "Glide" not in out


def test_write_engine_ini_forces_softdrv_and_regenerates_paths(tmp_path, monkeypatch):
    # _write_engine_ini crafts Paths from the mounts AND forces the headless device, byte-exact.
    from uedcli import container_assets
    base = ("[Core.System]\r\nPaths=../System/*.u\r\n"
            "[Engine.Engine]\r\nGameRenderDevice=OpenGLDrv.OpenGLRenderDevice\r\n"
            "WindowedRenderDevice=OpenGLDrv.OpenGLRenderDevice\r\n"
            "RenderDevice=GlideDrv.GlideRenderDevice\r\n").encode("latin-1")
    monkeypatch.setattr(editor, "_base_engine_ini_path", lambda: tmp_path / "base.ini")
    (tmp_path / "base.ini").write_bytes(base)
    mounts = container_assets.resource_mounts([str(tmp_path)])       # dir has base.ini -> one .u? no
    out_path = editor._write_engine_ini("uned-x", mounts, tmp_path)
    text = open(out_path, "rb").read().decode("latin-1")
    assert "RenderDevice=SoftDrv.SoftwareRenderDevice\r" in text
    assert "GameRenderDevice=SoftDrv.SoftwareRenderDevice\r" in text
    assert "Paths=/stubs/*.u\r" in text and "Paths=/opt/UED22/*.u\r" in text  # regenerated Paths
    assert "Paths=../System/*.u" not in text                         # old Paths dropped


def test_ensure_editor_mounts_override_ini_absolute_rw(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "_is_running", lambda c: False)
    monkeypatch.setattr(editor, "_wait_ready", lambda c, t: None)
    monkeypatch.setattr(editor, "editor_container", lambda s: "uned-x")
    monkeypatch.setattr(editor, "_wineprefix_volume", lambda s: "uned-wp-x")
    monkeypatch.setattr(editor, "_base_ini_path", lambda: tmp_path / "base.ini")
    (tmp_path / "base.ini").write_text("[U2Viewport2]\nRendMap=5\n")
    with mock.patch.object(editor.subprocess, "run") as run:
        run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        # state_dir = a hermetic tmp .uedcli (the override/engine inis land under its tmp/)
        editor.ensure_editor("x", state_dir=tmp_path,
                             ini_overrides={"U2Viewport2": {"RendMap": "6"}})
    argv = run.call_args[0][0]
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    ini_mount = [m for m in mounts if "/opt/UED22/UnrealEd.ini" in m][0]
    src = ini_mount.split(":/opt/UED22/UnrealEd.ini")[0]
    assert src.startswith("/")                                 # absolute host source
    assert not ini_mount.endswith(":ro")                       # RW (wine rewrites it on exit)
    assert "RendMap=6" in open(src).read()


def test_override_ini_lives_under_state_dir_not_system_tempdir(tmp_path):
    # REGRESSION: the docker daemon must SEE the bind source; a sandboxed shell's /tmp is private
    # to the sandbox, so /tmp/<c>.preview.ini mounts a phantom dir. It must sit under the project
    # tree (<root>/.uedcli/tmp), which is shared host<->daemon at an identical real path.
    import tempfile
    path = editor._override_ini_path("uned-x", tmp_path)
    assert path == tmp_path / "tmp" / "uned-x.preview.ini"       # under the state dir, daemon-visible
    assert not str(path).startswith(tempfile.gettempdir() + "/uned-")  # NOT bare system tempdir


def test_ensure_editor_without_overrides_adds_no_ini_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(editor, "_is_running", lambda c: False)
    monkeypatch.setattr(editor, "_wait_ready", lambda c, t: None)
    monkeypatch.setattr(editor, "editor_container", lambda s: "uned-x")
    monkeypatch.setattr(editor, "_wineprefix_volume", lambda s: "uned-wp-x")
    with mock.patch.object(editor.subprocess, "run") as run:
        run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        editor.ensure_editor("x", state_dir=tmp_path)
    argv = run.call_args[0][0]
    assert not any("/opt/UED22/UnrealEd.ini" in a for a in argv)

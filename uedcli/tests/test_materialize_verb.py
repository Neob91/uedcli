"""`level materialize` — the pure git-native build (git-native slice 3).

The live `_materialize`/`_save_and_swap_verified` drive is integration-only (needs `dx-lum-uned`).
Offline we stub those seams and prove the guards (overwrite-refusal, extension, trunk-only routing,
dup-order warn) + the composed-search-path load set wiring.
"""
import argparse
import contextlib
from pathlib import Path
from unittest import mock

import pytest

from uedcli import apply as applymod
from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.apply import ApplyResult, run_materialize
from uedcli.model import Actor, Level
from uedcli import xfer
from uedcli.verify import VerifyResult
from uedcli.tests.conftest import StubDefaults


def _NO_PACKAGES(package_name):
    """A schema resolver that finds no package on disk — the offline suite has no game install.
    `run_materialize` requires a resolver (the post-verify types both compare sides against
    the real class defaults and has NO zero fallback); the guard tests below stub the resolution
    itself via the `_level_defaults` seam, so this only has to exist."""
    return None


@pytest.fixture
def _stub_editor(monkeypatch):
    """Stub the live editor seams so run_materialize's orchestration + guards are offline-testable."""
    monkeypatch.setattr(applymod, "ensure_editor", lambda ed_id, **kw: "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: None)
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock())
    monkeypatch.setattr(applymod, "_materialize", lambda *a, **k: None)
    monkeypatch.setattr(applymod, "_save_and_swap_verified", lambda *a, **k: None)
    # The class-defaults resolve is a MOCKABLE SEAM (like dispatch's `_class_defaults`): decoding
    # them needs the game's `.u` packages, which the offline suite has none of.
    monkeypatch.setattr(applymod, "_level_defaults", lambda level, *, resolver: StubDefaults())


def _one_actor_level(cls="Engine.Light"):
    return Level(actors={"A_1": Actor(name="A_1", cls=cls, location=(1, 2, 3))}, order=["A_1"])


# ── Task 3: run_materialize guards (run BEFORE the stubbed drive → genuinely offline) ──

def test_it_refuses_to_overwrite_an_existing_out(tmp_path, _stub_editor):
    out = tmp_path / "Map.dx"
    out.write_text("hand-placed")
    r = run_materialize(level=_one_actor_level(), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / '.uedcli', out_path=str(out), overwrite=False)
    assert r.rc == 2 and str(out) in r.message
    assert out.read_text() == "hand-placed"                 # untouched


def test_it_allows_overwrite_with_the_flag(tmp_path, _stub_editor):
    out = tmp_path / "Map.dx"
    out.write_text("old")
    r = run_materialize(level=_one_actor_level(), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / '.uedcli', out_path=str(out), overwrite=True)
    assert r.rc == 0


def test_relative_out_resolves_against_the_cwd(tmp_path, monkeypatch, _stub_editor):
    # Spec §10.8: a relative --out joins the CWD (standard CLI semantics — the old repo-root join
    # + /repo remap died with repo_paths). Run from a non-root cwd; the overwrite guard must see
    # the cwd-resolved file.
    sub = tmp_path / "some" / "sub"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    (sub / "Map.dx").write_text("hand-placed")
    r = run_materialize(level=_one_actor_level(), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / ".uedcli",
                        out_path="Map.dx", overwrite=False)
    assert r.rc == 2 and "Map.dx" in r.message              # guard hit the cwd-resolved target
    assert (sub / "Map.dx").read_text() == "hand-placed"


def test_it_rejects_a_non_map_extension(tmp_path, _stub_editor):
    r = run_materialize(level=_one_actor_level(), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / '.uedcli',
                        out_path=str(tmp_path / "Map.txt"), overwrite=False)
    assert r.rc == 2 and ".dx" in r.message


def test_it_rejects_a_directory_out(tmp_path, _stub_editor):
    r = run_materialize(level=_one_actor_level(), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / '.uedcli',
                        out_path=str(tmp_path), overwrite=False)
    assert r.rc == 2 and "directory" in r.message


def test_it_tears_the_ephemeral_container_down_even_on_a_build_error(tmp_path, monkeypatch):
    stopped = []
    monkeypatch.setattr(applymod, "ensure_editor", lambda ed_id, **kw: "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: stopped.append(ed_id))
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock())
    monkeypatch.setattr(applymod, "_materialize",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(applymod, "_level_defaults", lambda level, *, resolver: StubDefaults())
    r = run_materialize(level=_one_actor_level(), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / '.uedcli',
                        out_path=str(tmp_path / "New.dx"), overwrite=False)
    assert r.rc == 2 and "nothing written" in r.message
    assert len(stopped) == 1                                # the ephemeral container was torn down


def test_an_unresolvable_class_exits_2_naming_the_actor_and_never_starts_the_editor(tmp_path,
                                                                                   monkeypatch):
    """The post-verify resolves both compare sides against the CLASS DEFAULTS and has no zero
    fallback (assuming zero IS the bug it exists to catch), so a class whose defaults cannot be
    decoded is fatal. It must fail (a) cleanly — exit 2, a message, no traceback; (b) naming the
    ACTOR as well as the class, since "class 'Camera' is not fully qualified" alone leaves the user
    grepping the level for it; and (c) BEFORE the ~100 s editor build, not after it.

    Bare classes really do reach here: `qualify.requalify_classes_to_loaded` leaves a bare class
    alone when the live editor offers 0 or 2+ candidates for it."""
    started = []
    monkeypatch.setattr(applymod, "ensure_editor",
                        lambda ed_id, **kw: started.append(ed_id) or "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: None)
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock())
    r = run_materialize(level=_one_actor_level(cls="Camera"), packages=[],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / ".uedcli",
                        out_path=str(tmp_path / "New.dx"), overwrite=False)
    assert r.rc == 2
    assert "'A_1'" in r.message and "Camera" in r.message and "qualified" in r.message
    assert not started                               # no container was ever created
    assert not (tmp_path / "New.dx").exists()        # and nothing was written


def test_no_verify_does_not_require_resolvable_class_defaults(tmp_path, monkeypatch):
    """`--no-verify` skips the post-verify entirely (its reason for existing is a broken or
    unavailable verify), so it must not be gated on the defaults the verify would have needed."""
    monkeypatch.setattr(applymod, "ensure_editor", lambda ed_id, **kw: "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: None)
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock())
    monkeypatch.setattr(applymod, "_materialize", lambda *a, **k: None)
    monkeypatch.setattr(applymod, "_save_and_swap_verified", lambda *a, **k: None)
    r = run_materialize(level=_one_actor_level(cls="Camera"), packages=[],
                        schema_resolver=_NO_PACKAGES, no_verify=True,
                        state_dir=tmp_path / ".uedcli",
                        out_path=str(tmp_path / "New.dx"), overwrite=False)
    assert r.rc == 0


def test_the_resolved_defaults_reach_the_post_verify(tmp_path, monkeypatch):
    """WIRING GUARD. The whole point of resolving class defaults up front is that the post-verify
    compares against THEM. Every other test here stubs `_save_and_swap_verified` wholesale, so a
    regression that resolved the defaults and then failed to thread them into `verify_dx_matches`
    would be invisible. This one follows the object all the way through."""
    resolved = StubDefaults()
    seen = {}
    monkeypatch.setattr(applymod, "ensure_editor", lambda ed_id, **kw: "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: None)
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock(container="uned-stub"))
    monkeypatch.setattr(applymod, "_materialize", lambda *a, **k: None)
    monkeypatch.setattr(applymod, "_level_defaults", lambda level, *, resolver: resolved)
    monkeypatch.setattr(applymod, "verify_dx_matches",
                        lambda **kw: seen.update(kw) or VerifyResult(ok=True))
    monkeypatch.setattr(xfer, "cp_out", lambda c, src, dst: Path(dst).write_bytes(b"dx"))
    monkeypatch.setattr(xfer, "remove", lambda *a, **k: None)
    r = run_materialize(level=_one_actor_level(), packages=[], schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / ".uedcli",
                        out_path=str(tmp_path / "New.dx"), overwrite=False)
    assert r.rc == 0
    assert seen["defaults"] is resolved               # the SAME object, not a re-resolve


def test_an_unresolvable_class_in_the_BUILT_map_is_a_clean_exit_2(tmp_path, monkeypatch):
    """The pre-flight only sees the trunk's classes. The re-exported map's classes are requalified
    against the live editor and can still come back bare (0 or 2+ candidates), so `compare_view`
    raises DURING the verify — after the build. That must still be exit 2 with the actor named, not
    a traceback, and nothing may be written (the swap happens after the verify)."""
    from uedcli.uprops import SchemaError
    monkeypatch.setattr(applymod, "ensure_editor", lambda ed_id, **kw: "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: None)
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock(container="uned-stub"))
    monkeypatch.setattr(applymod, "_materialize", lambda *a, **k: None)
    monkeypatch.setattr(applymod, "_level_defaults", lambda level, *, resolver: StubDefaults())
    monkeypatch.setattr(applymod, "verify_dx_matches", mock.Mock(
        side_effect=SchemaError("cannot verify actor 'Cam_x' — class must be fully qualified "
                                "(Package.Class): 'Camera'")))
    monkeypatch.setattr(xfer, "remove", lambda *a, **k: None)
    out = tmp_path / "New.dx"
    r = run_materialize(level=_one_actor_level(), packages=[], schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / ".uedcli", out_path=str(out), overwrite=False)
    assert r.rc == 2
    assert "'Cam_x'" in r.message and "Camera" in r.message
    assert not out.exists()


# ── Task 4: dispatch routing (mock run_materialize + the composed load set — no editor) ──

def _project_with_level(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light", location=(1, 2, 3)),
                        "B_2": Actor(name="B_2", cls="Light", location=(4, 5, 6))})
    trunk.write_level(proj / "maps" / name, lvl, {"A_1": "m", "B_2": "t"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj, name


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_materialize_resolves_the_trunk(tmp_path, monkeypatch):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    captured = {}

    def fake_run(**kw):
        captured.update(kw)
        return ApplyResult(rc=0, message="materialized out.dx")

    monkeypatch.setattr("uedcli.apply.run_materialize", fake_run)
    monkeypatch.setattr("uedcli.cli.resources.composed_load_set", lambda p: ["Engine", "DeusExDeco"])
    monkeypatch.setattr("uedcli.cli.resources.composed_dirs", lambda p: ["/g/Textures"])
    rc = dispatch.dispatch(_ns(cmd="level", sub="materialize", project=str(proj),
                               out=str(tmp_path / "out.dx"), overwrite=False))
    assert rc == 0
    assert set(captured["level"].actors) == {"A_1", "B_2"}     # read from the trunk
    assert captured["packages"] == ["Engine", "DeusExDeco"]    # composed-search-path load set
    assert captured["search_dirs"] == ["/g/Textures"]          # whole composed set → /resources


def test_materialize_warns_on_duplicate_order_value(tmp_path, monkeypatch, capsys):
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={"A_1": Actor(name="A_1", cls="Light", location=(1, 2, 3)),
                        "B_2": Actor(name="B_2", cls="Light", location=(4, 5, 6))})
    trunk.write_level(proj / "maps" / "lvl", lvl, {"A_1": "m", "B_2": "m"})   # SAME rank
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    monkeypatch.setattr("uedcli.apply.run_materialize",
                        lambda **kw: ApplyResult(rc=0, message="ok"))
    monkeypatch.setattr("uedcli.cli.resources.composed_load_set", lambda p: [])
    monkeypatch.setattr("uedcli.cli.resources.composed_dirs", lambda p: [])
    rc = dispatch.dispatch(_ns(cmd="level", sub="materialize", project=str(proj),
                               out=str(tmp_path / "out.dx"), overwrite=False))
    assert rc == 0
    assert "shared by 2+ actors" in capsys.readouterr().err


# ── Task 5: level doctor reads the trunk (fully offline — no editor) ──

def test_doctor_reads_the_trunk(tmp_path, monkeypatch, capsys):
    proj, name = _project_with_level(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(cmd="level", sub="doctor", project=str(proj),
                               json=False, severity=None, category=None))
    assert rc in (0, 1)                                  # findings-dependent, but it ran on the trunk
    assert name in capsys.readouterr().out              # report header uses the trunk level name


def test_doctor_no_project_errors_cleanly(tmp_path, monkeypatch, capsys):
    # With no uedcli project there is no level to lint; must exit 2 with a message, NOT a traceback.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UEDCLI_PROJECT", "")
    rc = dispatch.dispatch(_ns(cmd="level", sub="doctor", project=None,
                               json=False, severity=None, category=None))
    assert rc == 2
    err = capsys.readouterr().err
    assert "not in a uedcli project" in err and "Traceback" not in err


def test_materialize_missing_out_errors_before_the_load_set(tmp_path, monkeypatch, capsys):
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    # _composed_load_set must NOT be reached (it would hard-error on no games config first otherwise)
    monkeypatch.setattr("uedcli.cli.resources.composed_load_set",
                        lambda p: (_ for _ in ()).throw(AssertionError("load set computed too early")))
    rc = dispatch.dispatch(_ns(cmd="level", sub="materialize", project=str(proj),
                               out=None, overwrite=False))
    assert rc == 2
    assert "requires --out" in capsys.readouterr().err


def test_run_materialize_threads_search_dirs_into_mounts_and_ensure_load(tmp_path, monkeypatch):
    # The "computed ONCE and threaded" claim: search_dirs → resource_mounts → ensure_editor(mounts=)
    # AND ensure_load(search_dirs=, mounts=), the SAME mount list to both.
    seen = {}
    monkeypatch.setattr(applymod, "ensure_editor",
                        lambda ed_id, **kw: seen.update(editor_mounts=kw.get("mounts")) or "uned-stub")
    monkeypatch.setattr(applymod, "stop_editor", lambda ed_id, sd: None)
    monkeypatch.setattr(applymod, "Driver", lambda container=None: mock.Mock())
    monkeypatch.setattr(applymod, "_save_and_swap_verified", lambda *a, **k: None)

    def fake_materialize(driver, *, result, materialized_order, packages, search_dirs, mounts):
        seen.update(mat_search_dirs=search_dirs, mat_mounts=mounts)
    monkeypatch.setattr(applymod, "_materialize", fake_materialize)
    monkeypatch.setattr(applymod, "_level_defaults", lambda level, *, resolver: StubDefaults())

    r = run_materialize(level=_one_actor_level(), packages=["CoreTexMetal"],
                        schema_resolver=_NO_PACKAGES,
                        state_dir=tmp_path / '.uedcli',
                        search_dirs=["/g/Textures", "/g/System"],
                        out_path=str(tmp_path / "New.dx"), overwrite=False)
    assert r.rc == 0
    # ensure_editor and _materialize got the SAME mounts (one Mount per composed dir, /resources/rNNN)
    assert seen["editor_mounts"] == seen["mat_mounts"]
    assert [m.container_dir for m in seen["editor_mounts"]] == ["/resources/r000", "/resources/r001"]
    assert [m.host_dir for m in seen["editor_mounts"]] == ["/g/Textures", "/g/System"]
    # host resolution list = [stub cache, UED22, *composed dirs]; its tail is the composed dirs
    assert seen["mat_search_dirs"][-2:] == ["/g/Textures", "/g/System"]


def test_composed_dirs_hard_errors_without_a_games_config(tmp_path, monkeypatch):
    # The new no-games-config branch must exit 2 with a clear message, not a traceback.
    from uedcli import config
    monkeypatch.setattr(config, "load_user_config", lambda *a, **k: None)
    proj, _ = _project_with_level(tmp_path, monkeypatch)
    monkeypatch.setattr("uedcli.apply.run_materialize",
                        lambda **kw: pytest.fail("must not reach run_materialize"))
    rc = dispatch.dispatch(_ns(cmd="level", sub="materialize", project=str(proj),
                               out=str(tmp_path / "out.dx"), overwrite=False))
    assert rc == 2


@pytest.mark.integration
def test_materialize_builds_and_verifies_live(tmp_path):
    # requires dx-lum-uned: builds a one-actor trunk into a .dx, H3 verifies, the file exists.
    pytest.skip("integration: requires the dx-lum-uned container")

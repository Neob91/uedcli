from pathlib import Path
from unittest import mock

import pytest

from uedcli.stub_closure import resolve, StubClosureError


def _touch(d: Path, *names: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"")
    return d


def _dirs(tmp_path):
    substrate = _touch(tmp_path / "substrate", "Engine.u", "DeusEx.u")
    cache = _touch(tmp_path / "cache", "PriorStub.u")
    install = _touch(tmp_path / "install", "Target.u", "Foo.u", "DeusEx.u")
    content = _touch(tmp_path / "content", "Effects.utx")
    # One uniform search set: the v68 install dir + the content dir (the closure discriminates a dep
    # by extension within it — `.u` → must-stub, content ext → content).
    return dict(
        substrate_dirs=[str(substrate)],
        cache_dir=str(cache),
        search_dirs=[str(install), str(content)],
    )


def test_it_classifies_ready_must_stub_and_content_deps(tmp_path):
    # Arrange — Target depends on an always-loaded pkg, a substrate v69, a cache v69, a v68-only,
    # and a content package. Foo's own deps are all ready (no boundary error).
    dirs = _dirs(tmp_path)
    graph = {
        "Target.u": {"Engine", "DeusEx", "PriorStub", "Foo", "Effects"},
        "Foo.u": {"Core"},
    }

    # Act
    with mock.patch("uedcli.stub_closure.direct_packages", side_effect=lambda p: graph[Path(p).name]):
        result = resolve(str(tmp_path / "install" / "Target.u"), **dirs)

    # Assert
    assert set(result.ready_code) == {"Engine", "DeusEx", "PriorStub"}
    assert set(result.must_stub_code) == {"Foo"}
    assert set(result.content) == {"Effects"}


def test_it_raises_on_an_unresolvable_direct_dep(tmp_path):
    # Arrange — Target needs Ghost, which exists on no search dir.
    dirs = _dirs(tmp_path)
    graph = {"Target.u": {"Ghost"}}

    # Act / Assert
    with mock.patch("uedcli.stub_closure.direct_packages", side_effect=lambda p: graph[Path(p).name]):
        with pytest.raises(StubClosureError, match="Ghost"):
            resolve(str(tmp_path / "install" / "Target.u"), **dirs)


def test_it_raises_the_m1_boundary_when_a_must_stub_dep_needs_an_only_v68_dep(tmp_path):
    # Arrange — Foo is must-stub and Foo itself needs Bar, which is only v68 (a second stub level).
    dirs = _dirs(tmp_path)
    _touch(tmp_path / "install", "Bar.u")
    graph = {
        "Target.u": {"Foo"},
        "Foo.u": {"Bar"},
    }

    # Act / Assert
    with mock.patch("uedcli.stub_closure.direct_packages", side_effect=lambda p: graph[Path(p).name]):
        with pytest.raises(StubClosureError, match="only v68"):
            resolve(str(tmp_path / "install" / "Target.u"), **dirs)


def test_it_excludes_a_dx_only_dep_from_content_and_treats_it_as_unresolvable(tmp_path):
    # Arrange — a name present only as a `.dx` (a level) must not classify as content.
    dirs = _dirs(tmp_path)
    _touch(tmp_path / "content", "SomeLevel.dx")
    graph = {"Target.u": {"SomeLevel"}}

    # Act / Assert
    with mock.patch("uedcli.stub_closure.direct_packages", side_effect=lambda p: graph[Path(p).name]):
        with pytest.raises(StubClosureError, match="SomeLevel"):
            resolve(str(tmp_path / "install" / "Target.u"), **dirs)


def test_a_dep_present_as_both_code_and_content_classifies_as_code(tmp_path):
    # Arrange — `.u` must win over a same-named content ext (a code dep by reference).
    dirs = _dirs(tmp_path)
    _touch(Path(dirs["substrate_dirs"][0]), "Dual.u")
    _touch(tmp_path / "content", "Dual.utx")            # content dir is in search_dirs
    graph = {"Target.u": {"Dual"}}

    # Act
    with mock.patch("uedcli.stub_closure.direct_packages", side_effect=lambda p: graph[Path(p).name]):
        result = resolve(str(tmp_path / "install" / "Target.u"), **dirs)

    # Assert
    assert "Dual" in result.ready_code
    assert "Dual" not in result.content


def test_m1_boundary_does_not_fire_when_a_deeper_dep_is_content_or_ready(tmp_path):
    # Arrange — Foo is must-stub; its OWN deps are all ready/content (none only-v68) → no boundary.
    dirs = _dirs(tmp_path)
    graph = {
        "Target.u": {"Foo"},
        "Foo.u": {"Engine", "DeusEx", "Effects"},
    }

    # Act
    with mock.patch("uedcli.stub_closure.direct_packages", side_effect=lambda p: graph[Path(p).name]):
        result = resolve(str(tmp_path / "install" / "Target.u"), **dirs)

    # Assert — no StubClosureError; Foo is the only must-stub.
    assert set(result.must_stub_code) == {"Foo"}

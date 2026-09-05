"""`resources.texture_dims_resolver` — the `ref -> (USize, VSize)` callback per-surface texture
verbs (step 5: `align run --fit-perimeter`'s tile fix, `align one-tile`, `scale --to`) inject into
`polyalign`/`surface`, built over a real (synthetic) package rather than a mock.
"""
from __future__ import annotations

import argparse

import pytest

from uedcli.cli import resources
from uedcli.cli.errors import CommandError
from uedcli.tests import pkgfixture


@pytest.fixture
def _files(tmp_path):
    path = tmp_path / "Wall.utx"
    path.write_bytes(pkgfixture.texture_package(name="Wood", mips=pkgfixture.linear_chain(256, 64)))
    return [str(path)]


def test_texture_dims_resolver_resolves_a_real_package(monkeypatch, _files):
    monkeypatch.setattr(resources, "package_path_or_exit",
                        lambda args: (object(), object(), _files))
    resolve_dims = resources.texture_dims_resolver(argparse.Namespace())
    assert resolve_dims("Wall.Wood") == (256, 64)


def test_texture_dims_resolver_shares_one_cache_across_calls(monkeypatch, _files):
    """Built ONCE per invocation — two lookups of the same ref must not re-open the package."""
    monkeypatch.setattr(resources, "package_path_or_exit",
                        lambda args: (object(), object(), _files))
    resolve_dims = resources.texture_dims_resolver(argparse.Namespace())
    assert resolve_dims("Wall.Wood") == resolve_dims("Wall.Wood") == (256, 64)


def test_texture_dims_resolver_raises_plain_valueerror_naming_the_ref(monkeypatch, _files):
    monkeypatch.setattr(resources, "package_path_or_exit",
                        lambda args: (object(), object(), _files))
    resolve_dims = resources.texture_dims_resolver(argparse.Namespace())
    with pytest.raises(ValueError, match="Wall.NoSuchTexture"):
        resolve_dims("Wall.NoSuchTexture")


def test_texture_dims_resolver_exits_2_with_no_project(tmp_path, monkeypatch):
    """No project/no games config → `package_path_or_exit`'s own canonical CommandError, before
    a resolver is ever built — the same precondition every author-time texture validation shares."""
    monkeypatch.chdir(tmp_path)                       # no uedcli.toml here or above
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    with pytest.raises(CommandError, match="not in a uedcli project"):
        resources.texture_dims_resolver(argparse.Namespace(project=None))

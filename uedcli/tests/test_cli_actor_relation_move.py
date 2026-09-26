"""The relation family hangs off `actor`, not `brush` — and `brush relation` is gone outright."""
import argparse
from decimal import Decimal

import pytest

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.cli.main import build_parser
from uedcli.model import Level


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl,
                      {a.name: f"{i:04d}" for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _pair():
    return [make_brush_actor("LegFoot", cube(16, 16, 4),
                             location=tuple(Decimal(str(c)) for c in (0, 0, 4))),
            make_brush_actor("FloorPad", cube(200, 200, 8),
                             location=tuple(Decimal(str(c)) for c in (0, 0, -8)))]


def test_actor_relation_compare_runs(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _pair())
    ns = argparse.Namespace(cmd="actor", sub="relation", relationsub="compare",
                            project=str(proj), tree=None, ref="LegFoot",
                            target=["FloorPad"], top=1, allow_self=False)
    assert dispatch.dispatch(ns) == 0
    assert "LegFoot <-> FloorPad" in capsys.readouterr().out


def test_brush_relation_no_longer_parses():
    """argparse itself refuses the removed subcommand (SystemExit 2), no alias, no custom message."""
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["brush", "relation", "compare", "A", "B"])
    assert e.value.code == 2


def test_no_source_or_doc_still_says_brush_relation():
    """The old verb name is gone from every user-visible string and every shipped doc.

    Four exclusions, none of them a real hit: `parser_baseline` fixtures (regenerated from the
    parser, not authored); `docs/superpowers/plans/` (this rename's own ephemeral planning doc,
    which necessarily narrates the old name); this file itself (its docstrings, and the grep
    pattern literal below, unavoidably contain the searched-for string); and
    `docs/reference/brush/relation.md`, deliberately left saying `brush relation` until the page
    is moved and its links retargeted in one later commit (a link to it would 404 today)."""
    import subprocess
    out = subprocess.run(
        ["grep", "-rn", "brush relation", "uedcli", "docs", "plugins"],
        capture_output=True, text=True).stdout
    hits = [ln for ln in out.splitlines()
            if "parser_baseline" not in ln
            and "docs/superpowers/plans/" not in ln
            and "test_cli_actor_relation_move.py" not in ln
            and "docs/reference/brush/relation.md" not in ln]
    assert hits == [], "\n".join(hits)

"""`music` CLI — the reduced family + embedded title (audio arm A5).

`music` ships `list`/`show`/`search`/`classify` only — no `preview`/`prewarm` (a module has no
picture). `show` and `list --json` carry each module's embedded `title`/`format`, read live from the
`.umx` (`umxtitle`): IT is live-verified on Deus Ex; S3M/XM/unknown are fixture-built here.
"""
from __future__ import annotations

import io
import json

import pytest

from uedcli import audio_catalog as ac
from uedcli import audioindex
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser
from uedcli.tests import audiofixture as af

# (file stem, embedded module bytes, expected (title, format)).
MODULES = [
    ("Area51_Music", af.it_module("Area 51"), ("Area 51", "IT")),
    ("Vandenberg_Music", af.s3m_module("Vandenberg"), ("Vandenberg", "S3M")),
    ("HongKong_Music", af.xm_module("Hong Kong"), ("Hong Kong", "XM")),
    ("Broken_Music", b"", (None, "unknown")),
]


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for stem, embed, _ in MODULES:
        (corpus / f"{stem}.umx").write_bytes(af.audio_package(
            name=stem, kind="music", objects=[(None, "Song")], embed=embed))
    files = [(str(p), "fixture") for p in sorted(corpus.iterdir())]
    music_idx = audioindex.AudioIndex.from_files(files, "music")
    sound_idx = audioindex.AudioIndex.from_files(files, "sound")
    catalog = tmp_path / "catalog"
    monkeypatch.setattr(resources, "resolve_project", lambda args: object())
    monkeypatch.setattr(resources, "audio_index",
                        lambda project, kind: music_idx if kind == "music" else sound_idx)
    monkeypatch.setattr(resources, "catalog_dir", lambda project=None: str(catalog))

    def _run(*argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        rc = dispatch.dispatch(build_parser().parse_args(list(argv)))
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    _run.catalog = catalog
    return _run


def test_list_enumerates_the_module_refs(cli):
    rc, out, err = cli("music", "list")
    assert rc == 0
    assert out.split() == ["Area51_Music.Song", "Broken_Music.Song", "HongKong_Music.Song",
                           "Vandenberg_Music.Song"]
    assert err.strip() == "4 musics"


@pytest.mark.parametrize("stem,_embed,expected", MODULES)
def test_show_carries_the_embedded_title_and_format(cli, stem, _embed, expected):
    title, fmt = expected
    rc, out, _ = cli("music", "show", f"{stem}.Song", "--json")
    obj = json.loads(out)
    assert (obj["title"], obj["format"]) == (title, fmt)
    assert obj["ref"] == f"{stem}.Song"


def test_show_human_block_prints_title_and_format(cli):
    rc, out, _ = cli("music", "show", "Area51_Music.Song")
    assert "title:    Area 51" in out and "format:   IT" in out


def test_list_json_carries_title_and_format(cli):
    rc, out, _ = cli("music", "list", "--json")
    rows = {json.loads(ln)["ref"]: json.loads(ln) for ln in out.splitlines()}
    assert rows["Area51_Music.Song"]["title"] == "Area 51"
    assert rows["Broken_Music.Song"] == {"ref": "Broken_Music.Song", "identity": "Broken_Music.Song",
                                         "group": None, "classified": False,
                                         "title": None, "format": "unknown"}


def test_classify_refuse_then_force_on_music(cli):
    cli("music", "classify", "set", "Area51_Music.Song", "--tags", "ambient", "--description", "keep?")
    rc, out, err = cli("music", "classify", "set", "Area51_Music.Song", "--tags", "x")
    assert rc == 2 and "Area51_Music.Song" in err and "Traceback" not in err
    rc, out, err = cli("music", "classify", "set", "Area51_Music.Song", "--tags", "x", "--force")
    assert rc == 0, err
    shard = ac.load_shard(ac.shard_path(cli.catalog, "music", "Area51_Music.Song"))
    assert shard.tags == ["x"] and shard.description == "" and shard.kind == "music"


def test_classify_status_counts_music(cli):
    cli("music", "classify", "set", "HongKong_Music.Song", "--tags", "combat")
    rc, out, _ = cli("music", "classify", "status")
    assert out.strip() == "classified 1 / 4 musics"


@pytest.mark.parametrize("absent", ["preview", "prewarm"])
def test_music_has_no_preview_or_prewarm_verb(cli, absent):
    with pytest.raises(SystemExit) as e:
        cli("music", absent, "Area51_Music.Song")
    assert e.value.code == 2                            # argparse "invalid choice"

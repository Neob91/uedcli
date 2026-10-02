"""`sound` CLI — list / show / search / classify (audio arm A4).

End-to-end over a synthetic fixture corpus (the `resources` seams patched offline): no default
filter, the exact+repeatable `--package`, the refuse-then-`--force` write rule, the JSONL batch,
identity resolution across the 2-/3-part spellings, and the error dispositions (each a clean exit 2,
never a traceback). `sound preview` must be absent from the parser.
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

# The fixture sound corpus (dotted refs). DeusExSounds has a Bang collision across two groups.
SOUNDS = [
    "Ambient.Rain", "Ambient.Wind", "DeusExSounds.Ammo.Bang", "DeusExSounds.Beep",
    "DeusExSounds.Weapons.Bang", "DeusExSounds.Weapons.PistolShot",
]
PISTOL = "DeusExSounds.Weapons.PistolShot"          # unique bare name → 2-part identity
PISTOL_ID = "DeusExSounds.PistolShot"


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "DeusExSounds.uax").write_bytes(af.audio_package(
        name="DeusExSounds", kind="sound",
        objects=[("Weapons", "PistolShot"), ("Weapons", "Bang"), ("Ammo", "Bang"), (None, "Beep")]))
    (corpus / "Ambient.uax").write_bytes(af.audio_package(
        name="Ambient", kind="sound", objects=[(None, "Wind"), (None, "Rain")]))
    (corpus / "Area51_Music.umx").write_bytes(af.audio_package(
        name="Area51_Music", kind="music", objects=[(None, "Area51_Music")],
        embed=af.it_module("Area 51")))
    files = [(str(p), "fixture") for p in sorted(corpus.iterdir())]
    sound_idx = audioindex.AudioIndex.from_files(files, "sound")
    music_idx = audioindex.AudioIndex.from_files(files, "music")
    catalog = tmp_path / "catalog"
    monkeypatch.setattr(resources, "resolve_project", lambda args: object())
    monkeypatch.setattr(resources, "audio_index",
                        lambda project, kind: sound_idx if kind == "sound" else music_idx)
    monkeypatch.setattr(resources, "catalog_dir", lambda project=None: str(catalog))

    def _run(*argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        rc = dispatch.dispatch(build_parser().parse_args(list(argv)))
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    _run.catalog = catalog
    return _run


# --------------------------------------------------------------------------- list

def test_list_prints_every_ref_with_no_default_filter(cli):
    rc, out, err = cli("sound", "list")
    assert rc == 0
    assert out.split() == SOUNDS                       # every ref, dotted, sorted; nothing hidden
    assert err.strip() == "6 sounds"


def test_list_package_is_exact_and_repeatable(cli):
    rc, out, _ = cli("sound", "list", "--package", "DeusExSounds")
    assert out.split() == [s for s in SOUNDS if s.startswith("DeusExSounds")]
    rc, out, _ = cli("sound", "list", "--package", "DeusExSounds", "--package", "Ambient")
    assert out.split() == SOUNDS                       # union of the two


def test_list_package_is_not_a_glob(cli):
    rc, out, err = cli("sound", "list", "--package", "DeusEx*")
    assert rc == 2 and out == "" and "DeusEx*" in err and "Traceback" not in err


def test_list_unknown_package_exits_2_naming_it(cli):
    rc, out, err = cli("sound", "list", "--package", "Nope")
    assert rc == 2 and out == "" and "Nope" in err and "Traceback" not in err


def test_list_classified_unclassified_partition(cli):
    cli("sound", "classify", "set", PISTOL, "--tags", "weapon")
    rc, out, _ = cli("sound", "list", "--classified")
    assert out.split() == [PISTOL]
    rc, out, _ = cli("sound", "list", "--unclassified")
    assert PISTOL not in out.split() and len(out.split()) == 5


def test_list_json_shape(cli):
    rc, out, _ = cli("sound", "list", "--package", "DeusExSounds", "--json")
    rows = {json.loads(ln)["ref"]: json.loads(ln) for ln in out.splitlines()}
    assert rows[PISTOL] == {"ref": PISTOL, "identity": PISTOL_ID, "group": "Weapons",
                            "classified": False}
    assert rows["DeusExSounds.Weapons.Bang"]["identity"] == "DeusExSounds.Weapons.Bang"  # collision → 3-part


# --------------------------------------------------------------------------- classify set / refuse / force

def test_set_records_against_identity_and_prints_it(cli):
    rc, out, err = cli("sound", "classify", "set", PISTOL, "--tags", "weapon,loud",
                       "--description", "a pistol shot")
    assert rc == 0, err
    assert out.strip() == PISTOL_ID                    # the resolved identity, not the dotted ref
    shard = ac.load_shard(ac.shard_path(cli.catalog, "sound", PISTOL_ID))
    assert shard.to_json() == {"kind": "sound", "ref": PISTOL_ID,
                               "tags": ["weapon", "loud"], "description": "a pistol shot"}


def test_the_two_part_identity_addresses_the_same_shard(cli):
    cli("sound", "classify", "set", PISTOL, "--tags", "weapon")       # via the dotted ref
    rc, out, _ = cli("sound", "show", PISTOL_ID)                       # via the 2-part identity
    assert "weapon" in out and PISTOL_ID in out


def test_second_set_refuses_then_force_replaces_wholesale(cli):
    cli("sound", "classify", "set", PISTOL, "--tags", "a,b", "--description", "keep?")
    rc, out, err = cli("sound", "classify", "set", PISTOL, "--tags", "c")
    assert rc == 2 and out == "" and PISTOL_ID in err and "keep?" in err and "Traceback" not in err
    assert ac.load_shard(ac.shard_path(cli.catalog, "sound", PISTOL_ID)).tags == ["a", "b"]   # unchanged
    rc, out, err = cli("sound", "classify", "set", PISTOL, "--tags", "c", "--force")
    assert rc == 0, err
    shard = ac.load_shard(ac.shard_path(cli.catalog, "sound", PISTOL_ID))
    assert shard.tags == ["c"] and shard.description == ""             # wholesale; description wiped


def test_set_needs_at_least_one_field(cli):
    rc, _, err = cli("sound", "classify", "set", PISTOL)
    assert rc == 2 and "--tags" in err and "Traceback" not in err


def test_set_unknown_ref_exits_2_naming_it(cli):
    rc, out, err = cli("sound", "classify", "set", "DeusExSounds.NoSuch", "--tags", "x")
    assert rc == 2 and out == "" and "DeusExSounds.NoSuch" in err and "Traceback" not in err


def test_set_ambiguous_two_part_of_a_collision_exits_2(cli):
    rc, out, err = cli("sound", "classify", "set", "DeusExSounds.Bang", "--tags", "x")
    assert rc == 2 and "ambiguous" in err and "Traceback" not in err


# --------------------------------------------------------------------------- JSONL batch

def test_batch_writes_all_or_nothing(cli):
    rows = "\n".join(json.dumps(r) for r in [
        {"ref": PISTOL, "tags": ["weapon"]},
        {"ref": "DeusExSounds.NoSuch", "tags": ["x"]},          # bad → whole batch aborts
    ])
    rc, out, err = cli("sound", "classify", "set", "-", stdin=rows)
    assert rc == 2 and out == "" and "DeusExSounds.NoSuch" in err
    assert not ac.shard_path(cli.catalog, "sound", PISTOL_ID).exists()   # good row rolled back


def test_batch_force_governs_every_row(cli):
    cli("sound", "classify", "set", PISTOL, "--tags", "old")
    rc, out, err = cli("sound", "classify", "set", "-", "--force",
                       stdin=json.dumps({"ref": PISTOL, "tags": ["new"]}))
    assert rc == 0, err
    assert ac.load_shard(ac.shard_path(cli.catalog, "sound", PISTOL_ID)).tags == ["new"]


def test_batch_empty_stdin_is_a_clean_noop(cli):
    rc, out, _ = cli("sound", "classify", "set", "-", stdin="")
    assert rc == 0 and out == ""


# --------------------------------------------------------------------------- search / show

def test_search_ranks_and_requires_a_term(cli):
    rc, out, err = cli("sound", "search", "pistolshot")
    assert rc == 0 and out.strip() == PISTOL           # exact leaf name, top rank
    rc, out, err = cli("sound", "search")
    assert rc == 2 and "sound list" in err and "Traceback" not in err


def test_show_reads_a_ref_list_from_stdin(cli):
    rc, out, err = cli("sound", "show", "-", stdin=f"{PISTOL}\nAmbient.Wind\n")
    assert rc == 0 and PISTOL in out and "Ambient.Wind" in out


def test_show_empty_stdin_is_a_clean_noop(cli):
    rc, out, _ = cli("sound", "show", "-", stdin="")
    assert rc == 0 and out == ""


def test_show_bad_ref_exits_2_naming_it_no_traceback(cli):
    rc, out, err = cli("sound", "show", "DeusExSounds.Nope")
    assert rc == 2 and out == "" and "DeusExSounds.Nope" in err and "Traceback" not in err


def test_status_and_tags(cli):
    cli("sound", "classify", "set", PISTOL, "--tags", "weapon,loud")
    rc, out, _ = cli("sound", "classify", "status")
    assert out.strip() == "classified 1 / 6 sounds"
    rc, out, _ = cli("sound", "classify", "tags", "--json")
    assert json.loads(out) == {"loud": 1, "weapon": 1}


# --------------------------------------------------------------------------- corrupt shard on disk

def _corrupt_shard(cli, ref, text="{ this is <<<<<<< merge-conflicted not json"):
    p = ac.shard_path(cli.catalog, "sound", ref)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


@pytest.mark.parametrize("argv", [
    ("sound", "show", PISTOL_ID),
    ("sound", "search", "pistolshot"),
    ("sound", "classify", "set", PISTOL_ID, "--tags", "x", "--force"),
    ("sound", "classify", "unset", PISTOL_ID, "--all"),
])
def test_a_corrupt_tracked_shard_exits_2_naming_it_not_a_traceback(cli, argv):
    """A git merge-conflicted (invalid-JSON) shard is a hand-editable tracked file; reading it must
    be a clean exit 2 naming the shard, never a JSONDecodeError/KeyError traceback."""
    p = _corrupt_shard(cli, PISTOL_ID)
    rc, out, err = cli(*argv)
    assert rc == 2 and out == "" and str(p) in err and "Traceback" not in err


# --------------------------------------------------------------------------- preview is absent (phase b)

def test_sound_preview_is_absent_from_the_parser(cli):
    with pytest.raises(SystemExit) as e:
        cli("sound", "preview", PISTOL)
    assert e.value.code == 2                            # argparse "invalid choice"

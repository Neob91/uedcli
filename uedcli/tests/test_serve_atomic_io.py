import json
from pathlib import Path
from uedcli.serve.atomic_io import atomic_write_text, atomic_write_json

def test_atomic_write_text_creates_file_with_exact_content(tmp_path):
    p = tmp_path / "sub" / "f.txt"
    atomic_write_text(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"

def test_atomic_write_text_leaves_no_tmp_file_behind(tmp_path):
    p = tmp_path / "f.txt"
    atomic_write_text(p, "x")
    leftovers = [f for f in tmp_path.iterdir() if f != p]
    assert leftovers == []

def test_atomic_write_json_round_trips(tmp_path):
    p = tmp_path / "f.json"
    atomic_write_json(p, {"a": 1, "b": [1, 2]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2]}

def test_atomic_write_overwrites_existing_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("old", encoding="utf-8")
    atomic_write_text(p, "new")
    assert p.read_text(encoding="utf-8") == "new"

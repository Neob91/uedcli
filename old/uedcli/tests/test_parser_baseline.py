"""Slice 1 parser characterization: the live `cli.build_parser()` must match the checked-in
baseline for help text, the action tree, the argv corpus, and the non-CLI import closure. A later
reorg slice that moves parser registration must leave every one of these identical.

Regenerate with `python -m uedcli.tests.parser_baseline` (see `parser_baseline.regenerate`); a
failure here never rewrites a fixture.
"""
from __future__ import annotations

from uedcli.cli import main as cli
from uedcli.tests import parser_baseline as pb


def test_help_screens_match_baseline():
    assert pb.help_screens() == pb.load_fixture("help.json")


def test_action_tree_matches_baseline():
    assert pb.action_tree(cli.build_parser()) == pb.load_fixture("action_tree.json")


def test_argv_corpus_matches_baseline():
    assert pb.argv_corpus_results() == pb.load_fixture("argv_corpus.json")


def test_import_closure_matches_baseline():
    assert pb.compute_import_closure() == pb.load_fixture("import_closure.json")


def test_baseline_helpers_are_self_consistent():
    """The generator is deterministic: running a helper twice yields the same result, so a fixture
    diff means the parser changed, not the harness."""
    assert pb.help_screens() == pb.help_screens()
    assert pb.action_tree(cli.build_parser()) == pb.action_tree(cli.build_parser())

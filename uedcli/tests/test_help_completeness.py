"""Enforce the uedcli `CLAUDE.md` rule: *every command and argument needs a `help=`
that explains what it actually does — never just a restatement of the flag/command name.*

This walks the REAL argparse tree from `cli.build_parser()` and asserts, for every
subcommand and every argument, that its help string:
  (a) EXISTS (not None / not blank),
  (b) is not merely the flag/command NAME echoed back (`--target` → "target"), and
  (c) exceeds a minimal length (so a one-word stub like "extent" fails).

A future command/arg added with a missing or lazy help string trips this in CI. If a
genuinely-terse help is intentional, make it explain the thing (mention units, the axis,
the effect) rather than restating the name — that is the point of the rule.
"""
from __future__ import annotations

import argparse
import re

from uedcli.cli import main as cli

_MIN_LEN = 10   # chars, after strip — a real explanation clears this; "X extent" (8) did not


def _norm(s: str) -> str:
    """Lowercased, alphanumerics only — so `--target` ~ "target" ~ "Target." all compare equal."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _classify(help_text, label):
    """Return a defect reason for (help_text, label), or None if the help is acceptable."""
    if not help_text or not help_text.strip():
        return "MISSING"
    if _norm(help_text) == _norm(label):
        return "ECHOES-NAME"
    if len(help_text.strip()) < _MIN_LEN:
        return "TOO-SHORT"
    return None


def _walk(parser, path):
    """Yield (location, label, reason) for every offending action/subcommand under `parser`."""
    for act in parser._actions:
        if isinstance(act, argparse._HelpAction):
            continue                                    # argparse's own -h/--help: not ours to police
        if isinstance(act, argparse._SubParsersAction):
            # Sub-COMMAND help lives on the pseudo-actions (one per choice), not the group action.
            for ch in act._choices_actions:
                if (reason := _classify(ch.help, ch.dest)):
                    yield f"{path} {ch.dest}", ch.dest, reason
            for name, sub in act.choices.items():
                yield from _walk(sub, f"{path} {name}")
        else:
            label = act.option_strings[0] if act.option_strings else (act.metavar or act.dest)
            if (reason := _classify(act.help, label)):
                yield f"{path} {label}", label, reason


def test_classifier_catches_each_defect_class():
    """Proves the checker actually detects gaps — so the sweep test passing is meaningful, not
    a no-op that would green-light anything."""
    assert _classify(None, "--x") == "MISSING"
    assert _classify("   ", "--x") == "MISSING"
    assert _classify("target", "--target") == "ECHOES-NAME"
    assert _classify("Target.", "--target") == "ECHOES-NAME"      # normalization ignores case/punct
    assert _classify("extent", "--width") == "TOO-SHORT"          # a one-word stub
    assert _classify("box size along the X axis, in world units (uu)", "--width") is None


def test_every_command_and_argument_has_a_real_help_string():
    offenders = list(_walk(cli.build_parser(), "uedcli"))
    assert not offenders, "help= gaps (CLAUDE.md: help must EXPLAIN, not restate the name):\n" + \
        "\n".join(f"  [{reason}] {loc}" for loc, _label, reason in offenders)

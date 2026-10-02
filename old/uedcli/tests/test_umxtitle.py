"""`umxtitle.sniff_title` — the `.umx` embedded tracker-module title reader (audio arm A2).

IT is the only format live-verified on Deus Ex (all 35 `.umx` are IT); the S3M/XM offsets are
pinned by hand-built fixtures, and an unrecognised container must report absence AS absence
(`title=None`, `format="unknown"`), never a blank that reads as "this module has no title".
"""
from __future__ import annotations

import pytest

from uedcli import umxtitle
from uedcli.tests import audiofixture as af

# The three golden IT titles, live-verified on the real .umx (spike measure.py:_GOLDEN_UMX_TITLES).
GOLDEN_IT = {"Area51_Music": "Area 51", "Credits_Music": "The Illuminati",
             "Area51Bunker_Music": "Begin the End"}


@pytest.mark.parametrize("stem,title", sorted(GOLDEN_IT.items()))
def test_it_reads_the_golden_song_name(stem, title):
    assert umxtitle.sniff_title(af.it_module(title)) == (title, "IT")


def test_s3m_reads_its_own_name_field():
    assert umxtitle.sniff_title(af.s3m_module("Vandenberg")) == ("Vandenberg", "S3M")


def test_xm_reads_its_own_name_field():
    assert umxtitle.sniff_title(af.xm_module("Hong Kong")) == ("Hong Kong", "XM")


def test_it_wins_when_multiple_magics_present():
    """IT is checked first (the DX case). A buffer carrying both IMPM and SCRM reads as IT."""
    buf = af.it_module("Naval Base") + af.s3m_module("shadow")
    assert umxtitle.sniff_title(buf) == ("Naval Base", "IT")


def test_unrecognised_container_is_none_unknown_not_a_blank():
    assert umxtitle.sniff_title(b"\x00\x01not a module\xff" * 4) == (None, "unknown")


def test_an_empty_title_field_is_absence_not_the_empty_string():
    """An all-NUL IT name is an ABSENT title (None) but the format is still known — the caller can
    report `format: IT, title: (none)` rather than a blank that reads as no module."""
    assert umxtitle.sniff_title(af.it_module("")) == (None, "IT")


def test_the_magic_is_found_when_embedded_after_a_package_header():
    """In a real .umx the module sits inside the package body, not at offset 0 — sniff scans."""
    buf = b"\x9e\x2a\x83\xc1" + b"\x00" * 200 + af.it_module("DuClare")
    assert umxtitle.sniff_title(buf) == ("DuClare", "IT")

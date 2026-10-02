from uedcli.uuid7 import uuid7


def test_uuid7_is_36_char_hyphenated():
    u = uuid7()
    assert len(u) == 36 and u.count("-") == 4


def test_uuid7_version_nibble_is_7():
    u = uuid7()
    assert u[14] == "7"


def test_uuid7_monotonic_by_timestamp():
    a = uuid7(ms=1000)
    b = uuid7(ms=2000)
    assert a < b   # lexicographic order tracks time


def test_uuid7_unique():
    assert len({uuid7(ms=1000) for _ in range(1000)}) == 1000

"""The CLI token grammar: one `KEY[.PATH][=VALUE]` argument → a `PropToken`, plus the two
whole-invocation checks (hard-rejected keys, overlapping targets)."""
from __future__ import annotations

from dataclasses import dataclass

from .base import HARD_REJECT, PropEditError, _IDENT_RE, _INT_RE, _PAREN_ANY_RE


@dataclass(frozen=True)
class PropToken:
    base: str                            # the property name as typed
    segs: tuple[object, ...]             # path segments: int (index) or str (member name)
    value: str | None                    # None for unset/get tokens
    raw: str                             # the original token, for error messages


# ── token grammar ────────────────────────────────────────────────────────────────────────────

def parse_token(text: str, *, expect_value: bool) -> PropToken:
    """One CLI token → a `PropToken`. `expect_value` (set) demands `KEY=VALUE`; get/unset
    forbid `=`."""
    if expect_value:
        if "=" not in text:
            raise PropEditError(f"expected KEY=VALUE, got: {text!r}")
        key, value = text.split("=", 1)
    else:
        if "=" in text:
            raise PropEditError(f"unexpected '=' in {text!r} (only `set` takes values)")
        key, value = text, None
    key = key.strip()
    if _PAREN_ANY_RE.search(key):
        hint = _PAREN_ANY_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", key)
        raise PropEditError(f"{key}: the (N) index form is not accepted — "
                            f"use the dot form: {hint}")
    parts = key.split(".")
    base = parts[0]
    if not _IDENT_RE.match(base):
        raise PropEditError(f"bad property key: {key!r}")
    segs: list[object] = []
    for seg in parts[1:]:
        if _INT_RE.match(seg):
            iv = int(seg)
            if iv < 0:
                raise PropEditError(f"{key}: negative array index {iv} is invalid")
            segs.append(iv)
        elif _IDENT_RE.match(seg):
            segs.append(seg)
        else:
            raise PropEditError(f"bad path segment {seg!r} in {key!r}")
    return PropToken(base=base, segs=tuple(segs), value=value, raw=text)


def check_hard_reject(tok: PropToken) -> None:
    if tok.base.casefold() in HARD_REJECT:
        raise PropEditError(f"property {tok.base} cannot be accessed via `actor prop` "
                            "(Name/Brush are internal; author mover keys with `mover key`)")


def check_overlaps(tokens: list[PropToken]) -> None:
    """Intra-invocation conflict rule (set/unset only, spec §3.1): two tokens whose targets
    overlap — same base with one path a prefix of the other (or equal) — exit 2."""
    seen: list[tuple[PropToken, tuple]] = []
    for t in tokens:
        ident = (t.base.casefold(),) + tuple(
            s if isinstance(s, int) else s.casefold() for s in t.segs)
        for prev, pid in seen:
            short, long_ = (pid, ident) if len(pid) <= len(ident) else (ident, pid)
            if long_[:len(short)] == short:
                raise PropEditError(f"conflicting tokens in one invocation: "
                                    f"{prev.raw!r} and {t.raw!r}")
        seen.append((t, ident))

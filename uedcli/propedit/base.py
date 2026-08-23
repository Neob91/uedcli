"""The primitives every other propedit layer builds on: the user-facing error, the hard-reject set,
the token/struct-text regexes, the two value-parsing helpers, and the lazy per-class schema bundle
`ClassCtx` that eleven symbols across three layers take as an argument."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable

from ..uprops import Prop, SchemaError


# The ONLY hard rejects, applied to ALL THREE subcommands (spec §2.1): the actor Name
# (identity), the internal Brush binding, and the mover-key GEOMETRY/view bookkeeping (author
# those with `mover key`). `NumKeys` is NOT rejected — it is a first-class settable count, routed
# through the shared `movers.set_num_keys` bounds/canonical-form setter (spec 2026-07-20), so
# `actor prop set NumKeys=` and `mover key count` are identical in effect. Case-folded (FName).
HARD_REJECT = frozenset({"name", "brush", "keypos", "keyrot", "keynum"})


# §3.1 probe RESULT (live 2026-07-18, spikes/2026-07-18-partial-value-import-semantics/):
# the editor's T3D import is MEMBER-WISE ONTO THE CLASS DEFAULT — members unmentioned in a
# stored-partial struct value, and elements unmentioned in a sparse static array, resolve to
# the CLASS DEFAULT (not zero). `get`'s full-form rendering and member fall-through follow it.
# (The constant anchors the probe result; "zero" was the pre-probe placeholder and the
# alternative the probe REFUTED — kept as a named switch so the semantics stay greppable.)
STRUCT_FILL = "default"


# float32 representability bound (the engine stores floats): a numeric value beyond this can
# never be a meaningful engine value, and an unbounded Decimal would balloon the trunk file
# (review finding: `Location=1e999,0,0` wrote a ~1000-digit line).
_NUM_BOUND = Decimal("3.4e38")


_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")


_INT_RE = re.compile(r"^-?\d+$")


_PAREN_KEY_RE = re.compile(r"^([A-Za-z_]\w*)\((\d+)\)$")


_PAREN_ANY_RE = re.compile(r"([A-Za-z_]\w*)\((\d+)\)")


class PropEditError(Exception):
    """A named, user-facing prop-verb error (exit 2 at dispatch — never a traceback)."""


def _dequote(s: str) -> str:
    """Strip ONE genuine wrapping quote pair — a leading+trailing quote strips only when the
    interior holds no quote characters (review B10: `"a" and "b"` must keep ALL its quotes —
    its outer quotes belong to different words, not a wrapper; only `"whole value"`
    dequotes)."""
    t = s.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"' and '"' not in t[1:-1]:
        return t[1:-1]
    return t


def _dec_finite(text: str, label: str) -> Decimal:
    """Parse a REQUIRED finite, engine-representable number (review: `nan`/`inf` pass
    `Decimal()` and traceback later in emit/normalize; absurd exponents balloon the trunk)."""
    try:
        d = Decimal(_dequote(text))
    except InvalidOperation:
        raise PropEditError(f"{label}: expected a number, got {text!r}") from None
    if not d.is_finite():
        raise PropEditError(f"{label}: expected a finite number, got {text!r}")
    if abs(d) > _NUM_BOUND:
        raise PropEditError(f"{label}: {text!r} is out of the engine float range (±3.4e38)")
    return d


@dataclass
class ClassCtx:
    """Lazy per-class schema bundle. `schema()`/`defaults()` load-and-memoize on first use so
    typed-field-only and hard-reject paths never touch the install; `members(prop)` resolves a
    StructProperty's ordered member Props; `enums(prop)` resolves enum value names
    cross-package (an UNRESOLVABLE imported enum degrades to `()` — spec §4: get prints the
    ordinal, set accepts on type, matching the deliberately-partial validation stance)."""
    cls: str
    load_schema: Callable[[], dict[str, Prop]]
    load_defaults: Callable[[], dict[tuple[str, int], str]]
    load_members: Callable[[Prop], list[Prop]]
    load_enums: Callable[[Prop], tuple[str, ...]]
    _schema: dict[str, Prop] | None = None
    _defaults: dict[tuple[str, int], str] | None = None
    _members: dict[int, list[Prop]] = field(default_factory=dict)
    _enums: dict[int, tuple[str, ...]] = field(default_factory=dict)

    def schema(self) -> dict[str, Prop]:
        if self._schema is None:
            self._schema = self.load_schema()
        return self._schema

    def defaults(self) -> dict[tuple[str, int], str]:
        if self._defaults is None:
            self._defaults = self.load_defaults()
        return self._defaults

    def members(self, prop: Prop) -> list[Prop]:
        key = id(prop)
        if key not in self._members:
            self._members[key] = self.load_members(prop)
        return self._members[key]

    def enums(self, prop: Prop) -> tuple[str, ...]:
        if prop.kind != "ByteProperty" or prop.type_ref == 0:
            return ()                                # nothing to resolve — never load a package
        if prop.enum_value_names:                    # local enum, decoded eagerly
            return prop.enum_value_names
        key = id(prop)                               # imported enum → cross-package resolve
        if key not in self._enums:
            try:
                self._enums[key] = self.load_enums(prop)
            except SchemaError:                      # unresolvable enum: un-enumerable, not fatal
                self._enums[key] = ()
        return self._enums[key]


_VR_STRUCTS = {"vector", "rotator"}

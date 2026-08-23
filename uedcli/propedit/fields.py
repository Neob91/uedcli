"""The typed-field registry (spec §6): the model fields `actor prop` routes through instead of the
stored props — `Location` (a plain vector) and `MainScale`/`PostScale` (a `transform.FScale`)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .base import PropEditError, _dec_finite, _dequote
from .structtext import emit_struct_text, split_struct_text
from .tokens import PropToken


# ── the typed-field registry (spec §6) ───────────────────────────────────────────────────────

def _fmt_dec(d) -> str:
    """A Decimal/number → trimmed canonical text (`4`, `-17`, `32.5`). A non-finite value
    (only reachable from a hand-authored trunk) renders as its raw text rather than raising."""
    try:
        dd = Decimal(str(d))
        if not dd.is_finite():
            return str(d)
        if dd == dd.to_integral_value():
            return str(int(dd))
        return format(dd.normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(d)


@dataclass(frozen=True)
class TypedField:
    """A typed model field routed through the prop verbs (Location today; one registry entry
    per future field — spec §6). Pure vector semantics: whole-value set ZERO-FILLS unmentioned
    axes (ruling R2), member set bases on the current value, member unset zeroes the axis,
    whole unset resets to the zero (origin). `attr` names the `model.Actor` attribute the registry
    routes through; `dump_always` keeps Location in the `get` dump even when unset (a scale field is
    dumped only when the actor actually carries it)."""
    name: str                                        # canonical spelling ("Location")
    axes: tuple[str, ...] = ("X", "Y", "Z")
    attr: str = "location"                           # the model.Actor attribute this field routes to
    dump_always: bool = True

    def _axis_of(self, tok: PropToken) -> str | None:
        """The single member axis of `tok`'s path (None = whole field). Validates the path."""
        if not tok.segs:
            return None
        if len(tok.segs) > 1:
            raise PropEditError(f"{tok.raw}: {self.name} takes at most one member segment")
        seg = tok.segs[0]
        if isinstance(seg, int):
            raise PropEditError(f"{tok.raw}: {self.name} is not a static array")
        hit = next((a for a in self.axes if a.casefold() == seg.casefold()), None)
        if hit is None:
            raise PropEditError(f"unknown member {seg} of {self.name} "
                                f"(valid: {', '.join(self.axes)})")
        return hit

    def _tuple(self, location) -> tuple:
        return location if location is not None else (Decimal(0),) * len(self.axes)

    def text(self, location) -> str:
        vals = self._tuple(location)
        return emit_struct_text([(a, _fmt_dec(v)) for a, v in zip(self.axes, vals)])

    def get(self, tok: PropToken | None, location) -> tuple[str, str]:
        """(canonical key, value text) — the whole field, or one axis bare."""
        if tok is None:
            return self.name, self.text(location)
        axis = self._axis_of(tok)
        if axis is None:
            return self.name, self.text(location)
        vals = dict(zip([a.casefold() for a in self.axes], self._tuple(location)))
        return f"{self.name}.{axis}", _fmt_dec(vals[axis.casefold()])

    def _parse_whole(self, value: str) -> tuple:
        """A whole-value text → the axis tuple. Struct form `(X=1)` ZERO-FILLS unmentioned
        axes (ruling R2); the bare positional comma form requires every axis. Components must
        be finite, engine-range numbers."""
        t = _dequote(value)
        pairs = split_struct_text(t)
        if pairs is not None:
            vals = {a.casefold(): Decimal(0) for a in self.axes}
            for k, v in pairs:
                if k.casefold() not in vals:
                    raise PropEditError(f"unknown member {k} of {self.name} "
                                        f"(valid: {', '.join(self.axes)})")
                vals[k.casefold()] = _dec_finite(v, f"{self.name}.{k}")
            return tuple(vals[a.casefold()] for a in self.axes)
        parts = [p.strip() for p in t.split(",")]
        if len(parts) != len(self.axes):
            raise PropEditError(f"{self.name}={value}: expected (X=..,Y=..,Z=..) or the "
                                f"positional X,Y,Z form (all {len(self.axes)} components)")
        return tuple(_dec_finite(p, self.name) for p in parts)

    def apply(self, tok: PropToken, mode: str, location):
        """Apply a set/unset token; returns the new location tuple (None == origin reset)."""
        axis = self._axis_of(tok)
        if mode == "unset":
            if axis is None:
                return None                          # whole unset → origin
            vals = list(self._tuple(location))
            vals[[a.casefold() for a in self.axes].index(axis.casefold())] = Decimal(0)
            return tuple(vals)
        assert tok.value is not None
        if axis is None:
            return self._parse_whole(tok.value)
        v = _dec_finite(tok.value, tok.raw)
        vals = list(self._tuple(location))
        vals[[a.casefold() for a in self.axes].index(axis.casefold())] = v
        return tuple(vals)

    def match(self, tok: PropToken, location) -> bool:
        """`find --prop` comparison for the typed field: numeric, member-wise. A value that
        cannot parse RAISES (a never-matchable token is a typo, not an empty result — review
        finding)."""
        assert tok.value is not None
        axis = self._axis_of(tok)
        if axis is None:
            want = self._parse_whole(tok.value)
            return tuple(self._tuple(location)) == tuple(want)
        vals = dict(zip([a.casefold() for a in self.axes], self._tuple(location)))
        return vals[axis.casefold()] == _dec_finite(tok.value, tok.raw)


@dataclass(frozen=True)
class ScaleField:
    """A typed `MainScale`/`PostScale` field (a `transform.FScale`: `Scale` FVector + `SheerRate` +
    `SheerAxis`) routed through the prop verbs (spec §10). Paths: whole; `.Scale`, `.Scale.X|Y|Z`;
    `.SheerRate`; `.SheerAxis`. Member set bases on the current value; member unset reverts that
    member to its class default (scale 1.0, rate 0, axis SHEER_ZX); whole unset resets to identity.
    The stored value is a `transform.FScale` (or None == identity/absent). Shares the TypedField
    interface (`get`/`apply`/`match`, `attr`, `dump_always`)."""
    name: str                                        # "MainScale" / "PostScale"
    attr: str                                        # "main_scale" / "post_scale"
    dump_always: bool = False                        # dump only when the actor carries the field

    def _fs(self, value):
        from ..transform import IDENTITY
        return value if value is not None else IDENTITY

    def _member(self, tok: PropToken):
        """The lowercased member chain of the path (validated). () = whole field."""
        segs = tok.segs
        if not segs:
            return ()
        if any(isinstance(s, int) for s in segs):
            raise PropEditError(f"{tok.raw}: {self.name} has no static-array member")
        low = tuple(s.casefold() for s in segs)
        if low[0] == "scale":
            if len(low) == 1:
                return ("scale",)
            if len(low) == 2 and low[1] in ("x", "y", "z"):
                return ("scale", low[1])
            raise PropEditError(f"{tok.raw}: {self.name}.Scale members are X, Y, Z")
        if low[0] in ("sheerrate", "sheeraxis") and len(low) == 1:
            return (low[0],)
        raise PropEditError(f"unknown member {segs[0]} of {self.name} "
                            f"(valid: Scale, Scale.X/Y/Z, SheerRate, SheerAxis)")

    def _whole_text(self, fs) -> str:
        sx, sy, sz = (_fmt_dec(c) for c in fs.scale)
        return (f"(Scale=(X={sx},Y={sy},Z={sz}),"
                f"SheerRate={_fmt_dec(fs.sheer_rate)},SheerAxis={fs.sheer_axis})")

    def get(self, tok: PropToken | None, value) -> tuple[str, str]:
        fs = self._fs(value)
        chain = () if tok is None else self._member(tok)
        if chain == ():
            return self.name, self._whole_text(fs)
        if chain == ("scale",):
            sx, sy, sz = (_fmt_dec(c) for c in fs.scale)
            return f"{self.name}.Scale", f"(X={sx},Y={sy},Z={sz})"
        if chain[0] == "scale":
            idx = {"x": 0, "y": 1, "z": 2}[chain[1]]
            return f"{self.name}.Scale.{chain[1].upper()}", _fmt_dec(fs.scale[idx])
        if chain == ("sheerrate",):
            return f"{self.name}.SheerRate", _fmt_dec(fs.sheer_rate)
        return f"{self.name}.SheerAxis", fs.sheer_axis

    def _parse_whole(self, value: str):
        """A whole-value text → a validated `FScale`. Struct form `(Scale=(…),SheerRate=,SheerAxis=)`
        validates every member (unknown member / non-numeric → PropEditError, never a silent
        identity); the bare comma form is the Scale axes. Shared by set + find-match so a garbage
        value is a NAMED error, not a silent no-op (CLAUDE.md: errors name the offending value)."""
        from ..transform import DEFAULT_SHEER_AXIS, FScale
        pairs = split_struct_text(_dequote(value))
        if pairs is None:                                # bare comma form → Scale axes
            return FScale(self._parse_scale_vec(value), Decimal(0), DEFAULT_SHEER_AXIS)
        scale, rate, axis = [Decimal(1), Decimal(1), Decimal(1)], Decimal(0), DEFAULT_SHEER_AXIS
        for k, v in pairs:
            kl = k.casefold()
            if kl == "scale":
                scale = list(self._parse_scale_vec(v))
            elif kl == "sheerrate":
                rate = _dec_finite(v, f"{self.name}.SheerRate")
            elif kl == "sheeraxis":
                av = _dequote(v).strip()
                if not av.upper().startswith("SHEER_"):
                    raise PropEditError(f"{self.name}.SheerAxis must be a SHEER_* value, got {v!r}")
                axis = av.upper()
            else:
                raise PropEditError(f"unknown member {k} of {self.name} "
                                    f"(valid: Scale, SheerRate, SheerAxis)")
        return FScale(tuple(scale), rate, axis)

    def _parse_scale_vec(self, value: str) -> tuple:
        pairs = split_struct_text(_dequote(value))
        if pairs is not None:
            vals = {"x": Decimal(1), "y": Decimal(1), "z": Decimal(1)}
            for k, v in pairs:
                if k.casefold() not in vals:
                    raise PropEditError(f"unknown member {k} of {self.name}.Scale (valid: X, Y, Z)")
                vals[k.casefold()] = _dec_finite(v, f"{self.name}.Scale.{k}")
            return (vals["x"], vals["y"], vals["z"])
        parts = [p.strip() for p in _dequote(value).split(",")]
        if len(parts) != 3:
            raise PropEditError(f"{self.name}.Scale={value}: expected (X=..,Y=..,Z=..) or X,Y,Z")
        return tuple(_dec_finite(p, f"{self.name}.Scale") for p in parts)

    def apply(self, tok: PropToken, mode: str, value):
        from ..transform import IDENTITY, FScale
        fs = self._fs(value)
        chain = self._member(tok)
        if mode == "unset":
            if chain == ():
                return IDENTITY
            if chain == ("scale",):
                return FScale((Decimal(1),) * 3, fs.sheer_rate, fs.sheer_axis)
            if chain[0] == "scale":
                sc = list(fs.scale); sc[{"x": 0, "y": 1, "z": 2}[chain[1]]] = Decimal(1)
                return FScale(tuple(sc), fs.sheer_rate, fs.sheer_axis)
            if chain == ("sheerrate",):
                return FScale(fs.scale, Decimal(0), fs.sheer_axis)
            return FScale(fs.scale, fs.sheer_rate, "SHEER_ZX")
        assert tok.value is not None
        if chain == ():
            return self._parse_whole(tok.value)          # validates (no silent identity on garbage)
        if chain == ("scale",):
            return FScale(self._parse_scale_vec(tok.value), fs.sheer_rate, fs.sheer_axis)
        if chain[0] == "scale":
            sc = list(fs.scale)
            sc[{"x": 0, "y": 1, "z": 2}[chain[1]]] = _dec_finite(tok.value, tok.raw)
            return FScale(tuple(sc), fs.sheer_rate, fs.sheer_axis)
        if chain == ("sheerrate",):
            return FScale(fs.scale, _dec_finite(tok.value, tok.raw), fs.sheer_axis)
        axis = _dequote(tok.value).strip()
        if not axis.upper().startswith("SHEER_"):
            raise PropEditError(f"{tok.raw}: SheerAxis must be a SHEER_* value, got {tok.value!r}")
        return FScale(fs.scale, fs.sheer_rate, axis.upper())

    def match(self, tok: PropToken, value) -> bool:
        """`find --prop` comparison for the FScale field: numeric member-wise, axis case-fold."""
        assert tok.value is not None
        chain = self._member(tok)
        fs = self._fs(value)
        want = _dequote(tok.value).strip()

        def _d(x) -> Decimal:
            return x if isinstance(x, Decimal) else Decimal(str(x))

        if chain == ():
            w = self._parse_whole(tok.value)             # validates: garbage → error, not no-match
            return (tuple(_d(c) for c in fs.scale) == tuple(_d(c) for c in w.scale)
                    and _d(fs.sheer_rate) == _d(w.sheer_rate)
                    and fs.sheer_axis.casefold() == w.sheer_axis.casefold())
        if chain == ("scale",):
            return tuple(_d(c) for c in fs.scale) == tuple(_d(c) for c in self._parse_scale_vec(want))
        if chain[0] == "scale":
            return _d(fs.scale[{"x": 0, "y": 1, "z": 2}[chain[1]]]) == _dec_finite(tok.value, tok.raw)
        if chain == ("sheerrate",):
            return _d(fs.sheer_rate) == _dec_finite(tok.value, tok.raw)
        return fs.sheer_axis.casefold() == want.casefold()


TYPED_FIELDS: dict[str, TypedField | ScaleField] = {
    "location": TypedField(name="Location"),
    "mainscale": ScaleField(name="MainScale", attr="main_scale"),
    "postscale": ScaleField(name="PostScale", attr="post_scale"),
}

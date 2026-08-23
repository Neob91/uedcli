"""Path resolution against the class schema: a parsed token's dot path → the canonical spelling,
the base property, the optional array index and the struct-member chain it addresses."""
from __future__ import annotations

from dataclasses import dataclass

from ..uprops import Prop
from .base import ClassCtx, PropEditError, _PAREN_KEY_RE
from .tokens import PropToken


# ── path resolution against the schema ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MemberStep:
    prop: Prop                           # the member Prop (canonical spelling in .name)
    index: int | None                    # element index when the MEMBER is a static array

    @property
    def text_key(self) -> str:
        """The member's spelling inside a struct-text value (`Marks(1)` for an indexed
        member-array element, else the bare name)."""
        return self.prop.name if self.index is None else f"{self.prop.name}({self.index})"


@dataclass(frozen=True)
class ResolvedPath:
    prop: Prop                           # the base property
    index: int | None                    # base-level array index, if any
    members: tuple[MemberStep, ...]      # the struct member chain after the (optional) index
    canonical: str                       # canonical dot spelling, e.g. "Nest.Marks.1"

    @property
    def leaf(self) -> Prop:
        return self.members[-1].prop if self.members else self.prop

    @property
    def is_whole(self) -> bool:
        return self.index is None and not self.members


def resolve_path(tok: PropToken, ctx: ClassCtx) -> ResolvedPath:
    """Validate `tok`'s base + path against the class schema; returns canonical spellings and
    the leaf Prop. Raises `PropEditError` naming the failing segment. State machine: an int
    segment indexes the CURRENT slot when it is an un-indexed static array (the base prop or a
    member array); an identifier segment requires the current slot to be a struct."""
    schema = ctx.schema()
    prop = schema.get(tok.base.casefold())
    if prop is None:
        raise PropEditError(f"unknown property {tok.base} on class {ctx.cls}")
    segs = list(tok.segs)
    index: int | None = None
    if segs and isinstance(segs[0], int):
        if prop.array_dim <= 1:
            raise PropEditError(f"{prop.name} is not a static array (cannot index "
                                f"{tok.base}.{segs[0]})")
        if segs[0] >= prop.array_dim:
            raise PropEditError(f"{tok.base}.{segs[0]}: index out of bounds "
                                f"(array size {prop.array_dim}, valid 0..{prop.array_dim - 1})")
        index = segs.pop(0)
    members: list[MemberStep] = []
    cur = prop
    for seg in segs:
        if isinstance(seg, int):
            last = members[-1] if members else None
            if last is not None and last.index is None and last.prop.array_dim > 1:
                if seg >= last.prop.array_dim:
                    raise PropEditError(
                        f"{tok.raw}: index {seg} out of bounds for {last.prop.name} "
                        f"(array size {last.prop.array_dim})")
                members[-1] = MemberStep(prop=last.prop, index=seg)
                continue
            raise PropEditError(f"{tok.raw}: unexpected index .{seg} "
                                f"({cur.name} is not an indexable static array here)")
        if cur.kind != "StructProperty":
            raise PropEditError(f"{cur.name} is not a struct (cannot take member .{seg})")
        last = members[-1] if members else None
        if last is not None and last.prop.array_dim > 1 and last.index is None:
            raise PropEditError(f"{tok.raw}: {last.prop.name} is a static array — index it "
                                f"({last.prop.name}.N) before taking member .{seg}")
        mlist = ctx.members(cur)
        m = next((mm for mm in mlist if mm.name.casefold() == seg.casefold()), None)
        if m is None:
            valid = ", ".join(mm.name for mm in mlist)
            raise PropEditError(f"unknown member {seg} of {cur.type_name or cur.name} "
                                f"(valid: {valid})")
        members.append(MemberStep(prop=m, index=None))
        cur = m
    canonical = prop.name
    if index is not None:
        canonical += f".{index}"
    for step in members:
        canonical += f".{step.prop.name}"
        if step.index is not None:
            canonical += f".{step.index}"
    return ResolvedPath(prop=prop, index=index, members=tuple(members), canonical=canonical)


def _member_map(members: list[Prop]) -> dict[str, Prop]:
    return {m.name.casefold(): m for m in members}


def _text_key_ident(k: str) -> tuple[str, int | None]:
    m = _PAREN_KEY_RE.match(k)
    if m is not None:
        return m.group(1).casefold(), int(m.group(2))
    return k.casefold(), None

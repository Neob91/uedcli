"""Mover domain helpers: identify a Mover, read/write its keyframes, and canonicalize an ingested
mover to KeyNum=0. Identification is SCHEMA-AWARE — `is_mover` resolves the actor's class against
`Engine.Mover` through a `classindex.ClassIndex`, so it needs the game's `.u` packages on the
composed search path. Movers store the base pose in the ordinary Location/Rotation fields
(KeyNum=0); keyframe i>=1 is a relative offset in KeyPos(i)/KeyRot(i). BasePos/BaseRot are
editor-derived and SavedPos/SavedRot are engine-stamped by `AMover::PostLoad` (all four stripped by
normalize), never written here. See the 2026-06-25 spec + spike, and the 2026-07-25
`spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/` spike."""
from __future__ import annotations

from decimal import Decimal

from .classindex import CORE_OBJECT, ClassRefError
from .model import Actor
from . import rotation

MAX_KEYS = 8            # KeyPos[8]/KeyRot[8] are fixed-size arrays in Engine.u
MIN_KEYS = 2            # a mover needs at least 2 keys; use a brush for static geometry

MOVER_BASE = "Engine.Mover"     # the engine root every mover class descends from

# One canonical message for "this run has no class resolver, so mover-ness cannot be decided".
# Raised (never warned) because an index that resolves nothing answers `False` for EVERY actor —
# a real mover would silently read as a static brush (`direction.md` "No silent half-answers").
NO_MOVER_RESOLVER = (
    f"cannot resolve {MOVER_BASE}: deciding whether an actor is a Mover needs the game's code "
    f"packages (`.u`) on the composed search path — check the per-user games config "
    f"(~/.uedctl/config.toml) `paths` and that the project targets a game")

_ZERO_POS = (Decimal(0), Decimal(0), Decimal(0))


def _mover_by_ancestry(index, fqcn: str) -> bool:
    """`fqcn` descends from `Engine.Mover`, per its resolved ancestor chain.

    Raises `ClassRefError` when the chain is INCOMPLETE — `ClassIndex.ancestry` silently truncates
    at a missing/unparseable ancestor package, and a truncated chain that hasn't reached
    `Engine.Mover` yet is unknown, not `False`. Every real UE1 chain ends at `Core.Object`, so a
    chain ending anywhere else means a package on it is off the search path."""
    chain = index.ancestry(fqcn)
    base = MOVER_BASE.casefold()
    if any(a.casefold() == base for a in chain):
        return True
    if chain[-1].casefold() != CORE_OBJECT.casefold():
        raise ClassRefError(
            f"cannot decide whether class {fqcn} is a Mover: its ancestor chain stops at "
            f"{chain[-1]} instead of the {CORE_OBJECT} root, so a package on the chain is missing "
            f"from the composed search path (check the project `paths` and the games config)")
    return False


def is_mover(actor: Actor, index) -> bool:
    """True when the actor's class IS `Engine.Mover` or descends from it.

    `index` is a `classindex.ClassIndex` — the offline class hierarchy read out of the game's own
    `.u` packages. This is the SINGLE shared predicate (doctor, dispatch, event graph, the native
    build and the native preview all use it — no per-substrate class list), and it is deliberately
    SCHEMA-AWARE rather than a name guess: the old `bare.endswith("Mover")` test rejected real
    movers whose class name doesn't end in `Mover` (`CaroneElevatorSet.CEDoor`,
    `CaroneElevatorSet.CaroneElevator`, `DeusEx.BreakableGlass`, `DeusEx.BreakableWall`) and would
    have accepted any unrelated class that happened to end in it. *(decisions.md 2026-07-25 10:18
    UTC.)*

    A BARE class name (an unqualified `Class=Mover`, as UnrealEd's own `MAP EXPORT` writes and as an
    un-qualifiable collision leaves in the trunk) is resolved through the index's bare→FQCN map. An
    empty class (a classless brush) is not a mover.

    **It answers, or it raises — it never guesses.** `ClassRefError` (→ a clean exit 2, never a
    traceback) is raised whenever the answer is not knowable: the index cannot resolve
    `Engine.Mover` at all (no usable resolver); the actor's own class does not resolve (its package
    is off the search path); its ancestor chain truncates before reaching the `Core.Object` root; or
    a bare name's candidates DISAGREE about mover-ness. Returning `False` in any of those cases
    would report a real mover as a static brush — invisibly, since nothing downstream re-checks."""
    if not index.class_exists(MOVER_BASE):
        raise ClassRefError(NO_MOVER_RESOLVER)
    cls = (actor.cls or "").strip()
    if not cls:
        return False
    if "." in cls:
        if not index.class_exists(cls):
            raise ClassRefError(
                f"cannot decide whether class {cls} is a Mover: that class is not on the composed "
                f"package search path (check the project `paths` and the games config)")
        return _mover_by_ancestry(index, cls)
    candidates = sorted(index.bare_to_fqcn().get(cls.casefold(), ()))
    if not candidates:
        raise ClassRefError(
            f"cannot decide whether class {cls} is a Mover: no class of that name exists in any "
            f"package on the composed search path")
    verdicts = {_mover_by_ancestry(index, fqcn) for fqcn in candidates}
    if len(verdicts) > 1:                      # a cross-package bare-name collision, one of each
        raise ClassRefError(
            f"cannot decide whether the bare class {cls} is a Mover: it resolves to "
            f"{', '.join(candidates)}, and they disagree — qualify the actor's class")
    return verdicts.pop()


def num_keys(actor: Actor) -> int:
    for k, v in actor.props:
        if k == "NumKeys":
            try:
                return int(v)
            except ValueError:
                return 2
    return 2            # Engine default


def _get(actor: Actor, key: str) -> str | None:
    for k, v in actor.props:
        if k == key:
            return v
    return None


def _set(actor: Actor, key: str, value: str | None) -> None:
    """Replace (or remove if value is None) a prop, preserving position-insensitive order."""
    actor.props = [(k, v) for k, v in actor.props if k != key]
    if value is not None:
        actor.props.append((key, value))


def _set_numkeys(actor: Actor, n: int) -> None:
    # NumKeys default is 2 — omit it when 2 so it matches the editor's export (no spurious line).
    _set(actor, "NumKeys", None if n == 2 else str(n))


def _ensure_numkeys(actor: Actor, n: int) -> None:
    if n > num_keys(actor):
        _set_numkeys(actor, n)


def check_num_keys(n: int) -> None:
    """Validate a NumKeys count against the fixed KeyPos[8]/KeyRot[8] array bounds. Raises
    ValueError naming the offending value. The single shared validator for both `mover key count`
    and `actor prop set NumKeys=` (spec 2026-07-20), so the two routes reject identically."""
    if not (MIN_KEYS <= n <= MAX_KEYS):
        raise ValueError(f"NumKeys must be {MIN_KEYS}..{MAX_KEYS}, got {n}")


def set_num_keys(actor: Actor, n: int) -> None:
    """Set NumKeys to n (validated MIN_KEYS..MAX_KEYS via `check_num_keys`), keeping the
    omit-when-2 canonical form the editor exports. NON-DESTRUCTIVE: it changes only the count,
    never the stored KeyPos/KeyRot values — lowering the count leaves the now-inactive keys'
    lines dormant so a later raise restores them."""
    check_num_keys(n)
    _set_numkeys(actor, n)


def key_pos(actor: Actor, i: int):
    """Relative position offset of key i (Decimal triple); (0,0,0) if absent or i==0."""
    if i == 0:
        return _ZERO_POS
    v = _get(actor, f"KeyPos({i})")
    return rotation.parse_fvector(v) if v else _ZERO_POS


def key_rot(actor: Actor, i: int) -> tuple[int, int, int]:
    """Relative rotation offset of key i (UU triple); (0,0,0) if absent or i==0."""
    if i == 0:
        return (0, 0, 0)
    v = _get(actor, f"KeyRot({i})")
    return rotation.parse_frotator(v) if v else (0, 0, 0)


def mover_keys(actor: Actor) -> list[tuple]:
    """[(idx, off_pos Decimal-triple, off_rot UU-triple)] for idx 0..num_keys-1."""
    return [(i, key_pos(actor, i), key_rot(actor, i)) for i in range(num_keys(actor))]


def set_key_pos(actor: Actor, i: int, offset) -> None:
    """Write KeyPos(i) from a relative Decimal-triple offset (omit/clear if all-zero); ensure
    NumKeys >= i+1."""
    s = rotation.emit_fvector(offset)
    _set(actor, f"KeyPos({i})", None if s == "()" else s)
    _ensure_numkeys(actor, i + 1)


def set_key_rot(actor: Actor, i: int, offset_uu: tuple[int, int, int]) -> None:
    """Write KeyRot(i) from a relative UU-triple offset (omit/clear if all-zero); ensure
    NumKeys >= i+1."""
    s = rotation.emit_frotator(offset_uu)
    _set(actor, f"KeyRot({i})", None if s == "()" else s)
    _ensure_numkeys(actor, i + 1)


def remove_key(actor: Actor, i: int) -> None:
    """Remove key i (i>=1) and compact: keys above i shift down by one; NumKeys decrements."""
    n = num_keys(actor)
    # capture surviving offsets, drop i, re-index contiguously
    survivors = [(j, key_pos(actor, j), key_rot(actor, j)) for j in range(1, n) if j != i]
    for j in range(1, n):                    # clear all current indexed props
        _set(actor, f"KeyPos({j})", None)
        _set(actor, f"KeyRot({j})", None)
    _set_numkeys(actor, n - 1)
    for new_idx, (_old, off_pos, off_rot) in enumerate(survivors, start=1):
        set_key_pos(actor, new_idx, off_pos)
        set_key_rot(actor, new_idx, off_rot)


def emit_or_none_pos(actor: Actor, i: int) -> str | None:
    return _get(actor, f"KeyPos({i})")


def emit_or_none_rot(actor: Actor, i: int) -> str | None:
    return _get(actor, f"KeyRot({i})")


def canonicalize_mover(actor: Actor, index) -> None:
    """Fold a KeyNum=k!=0 mover back to KeyNum=0: rewrite Location/Rotation to the base pose and
    drop KeyNum. Idempotent. Other keys' offsets are unchanged (base-relative, base unchanged).
    `index` is the `classindex.ClassIndex` the `is_mover` gate resolves against."""
    if not is_mover(actor, index):
        return
    knum = _get(actor, "KeyNum")
    k = int(knum) if knum and knum.isdigit() else 0
    if k == 0:
        _set(actor, "KeyNum", None)          # normalize away an explicit KeyNum=0
        return
    # Location := Location - KeyPos(k)
    loc = actor.location or _ZERO_POS
    off = key_pos(actor, k)
    actor.location = (loc[0] - off[0], loc[1] - off[1], loc[2] - off[2])
    # Rotation := Rotation - KeyRot(k)  (FRotator field subtraction)
    rot_uu = rotation.actor_rotation_uu(actor)
    base_uu = rotation.subtract_uu(rot_uu, key_rot(actor, k))
    rstr = rotation.emit_frotator(base_uu)
    _set(actor, "Rotation", None if rstr == "()" else rstr)
    _set(actor, "KeyNum", None)

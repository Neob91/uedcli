"""Pure, offline shot model for `level preview` — the SHOT-token grammar (`at:…;rot:…` /
`look:` / `orbit:`), the free-pose trig (`pose_from_lookat` / `pose_from_orbit`), and the
output-filename rule. No editor, no I/O (fully unit-tested). The grammar is shared verbatim
with the future `--game` tier (board item `level-preview-game` §3) so the same
tokens pose either backend. (The old `TARGET[:MODE][=NAME]` auto-frame grammar and the
editor-screenshot backend were deleted at the `--native` cutover, 2026-07-16.)"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

def _uu_to_deg(uu: float) -> float:
    """Pose-grammar angle: unreal rotation units → signed degrees (16384 = 90°). No wrap, so a
    negative like -16384 stays -90° (right for pitch clamping; yaw periodicity makes the sign
    irrelevant there). Local (not imported from `rotation`) so this module stays standalone-importable,
    matching `game/preview_batch.py`'s own `_deg_to_uu`."""
    return uu * 360.0 / 65536.0

# A filename stem is safe iff it is only these chars (FNames are alnum/underscore).
_SLUG_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


# --- the SHOT-token grammar (shared with the --game tier; in-game spec §3) ---------------

_MIGRATION_HINT = ("preview grammar changed: pose each shot with "
                   "'at:X,Y,Z;rot:PITCH,YAW', 'at:X,Y,Z;look:X,Y,Z|@Actor', or "
                   "'orbit:@Actor;radius:R;azimuth:A[;elev:B]' (angles in unreal rotation units, 16384 = 90°; "
                   "add ';name:STEM' for the output name)")

_SHOT_KEYS = {"at", "rot", "look", "orbit", "radius", "azimuth", "elev", "name"}


@dataclass(frozen=True, kw_only=True)
class Shot:
    """One validated SHOT token. Exactly one of `rot`/`look`/`orbit` is set (grammar rule).
    `look` is a world point or an actor name (the `@` stripped, `look_at_actor=True`);
    `orbit` is always an actor name. Actor names resolve later (all-or-nothing) in the
    dispatch front half; `resolve_pose` then turns the Shot into a `ResolvedShot`."""
    at: tuple[float, float, float] | str | None = None  # camera eye: point, @actor name, or None (orbit:)
    rot: tuple[float, float] | None = None          # (pitch, yaw) — input in UU, stored as degrees
    look: tuple[float, float, float] | str | None = None
    orbit: str | None = None                        # actor name (ring centre)
    radius: float | None = None
    azimuth: float | None = None
    elev: float = 0.0
    name: str | None = None                         # output-stem override


@dataclass(frozen=True, kw_only=True)
class ResolvedShot:
    """A Shot with every actor ref resolved and the pose trig done: a camera eye + FRotator
    angles in degrees. This is the one shape both preview backends consume."""
    eye: tuple[float, float, float]
    pitch: float
    yaw: float
    name: str | None = None


def _parse_floats(val: str, n: int, what: str, token: str) -> tuple:
    parts = [p.strip() for p in val.split(",")]
    if len(parts) != n or any(not p for p in parts):
        raise ValueError(f"{what} needs {n} comma-separated numbers, got {val!r} "
                         f"in shot {token!r}")
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise ValueError(f"{what} has a non-numeric component {val!r} in shot {token!r}") from None


def _parse_float(val: str, what: str, token: str) -> float:
    try:
        return float(val)
    except ValueError:
        raise ValueError(f"{what} must be a number, got {val!r} in shot {token!r}") from None


def parse_shot(token: str) -> Shot:
    """One SHOT token → a validated `Shot`. Raises ValueError (→ clean exit 2) naming the
    offending token; a token in the OLD `TARGET[:MODE][=NAME]` grammar gets a migration hint.
    Delimiters `;`/`:`/`,`/`@` never occur in FNames or numeric literals (in-game spec §3)."""
    fields: dict[str, str] = {}
    for part in token.split(";"):
        if ":" not in part:
            raise ValueError(f"shot {token!r} looks like the old TARGET[:MODE][=NAME] grammar "
                             f"({part!r} is not a key:value field) — {_MIGRATION_HINT}")
        key, val = part.split(":", 1)
        key = key.strip().lower()
        if key not in _SHOT_KEYS:
            raise ValueError(f"unknown field {key!r} in shot {token!r} — {_MIGRATION_HINT}")
        if key in fields:
            raise ValueError(f"duplicate field {key!r} in shot {token!r}")
        if not val.strip():
            raise ValueError(f"empty value for {key!r} in shot {token!r}")
        fields[key] = val.strip()

    pose_keys = [k for k in ("rot", "look", "orbit") if k in fields]
    if len(pose_keys) != 1:
        raise ValueError(f"shot {token!r} needs exactly one of rot:/look:/orbit: "
                         f"(got {', '.join(pose_keys) or 'none'})")
    name = fields.get("name")
    if name is not None and not _SLUG_SAFE.match(name):
        raise ValueError(f"invalid name {name!r} in shot {token!r}; use only letters, digits, "
                         f"'_', '-', '.'")

    if "orbit" in fields:
        bad = [k for k in ("at", "rot", "look") if k in fields]
        if bad:
            raise ValueError(f"orbit: is self-contained — drop {', '.join(bad)} in shot {token!r}")
        target = fields["orbit"]
        if not target.startswith("@") or len(target) < 2:
            raise ValueError(f"orbit: takes @ActorName, got {target!r} in shot {token!r}")
        missing = [k for k in ("radius", "azimuth") if k not in fields]
        if missing:
            raise ValueError(f"orbit: needs {', '.join(missing)} in shot {token!r}")
        radius = _parse_float(fields["radius"], "radius", token)
        if radius <= 0:
            raise ValueError(f"radius must be > 0, got {radius:g} in shot {token!r}")
        return Shot(orbit=target[1:], radius=radius,   # azimuth/elev in unreal rotation units
                    azimuth=_uu_to_deg(_parse_float(fields["azimuth"], "azimuth", token)),
                    elev=_uu_to_deg(_parse_float(fields["elev"], "elev", token)) if "elev" in fields else 0.0,
                    name=name)

    for k in ("radius", "azimuth", "elev"):
        if k in fields:
            raise ValueError(f"{k}: only applies to orbit: shots (shot {token!r})")
    if "at" not in fields:
        raise ValueError(f"shot {token!r} needs at:X,Y,Z (the camera eye position)")
    at_val = fields["at"]
    if at_val.startswith("@"):                          # eye AT an actor (resolved by the game/trunk)
        if len(at_val) < 2:
            raise ValueError(f"at:@ needs an actor name in shot {token!r}")
        at: tuple | str = at_val[1:]
    else:
        at = _parse_floats(at_val, 3, "at", token)
    if "rot" in fields:
        pitch_uu, yaw_uu = _parse_floats(fields["rot"], 2, "rot", token)   # unreal rotation units
        return Shot(at=at, rot=(_uu_to_deg(pitch_uu), _uu_to_deg(yaw_uu)), name=name)
    look_val = fields["look"]
    if look_val.startswith("@"):
        if len(look_val) < 2:
            raise ValueError(f"look:@ needs an actor name in shot {token!r}")
        return Shot(at=at, look=look_val[1:], name=name)
    return Shot(at=at, look=_parse_floats(look_val, 3, "look", token), name=name)


# --- pose trig (backend-agnostic; degrees in eye space) ----------------------------------
# UE1 FRotator semantics: yaw 0 = +X, increasing towards +Y (Rz); positive pitch looks UP
# (+Z) — the spike-pinned convention `rotation.euler_to_matrix_uu` renders (forward = R·x̂,
# so yaw = atan2(dy,dx), pitch = atan2(dz, hypot(dx,dy))). Straight up/down keeps yaw from
# the ring/last term (atan2(0,0) = 0 → yaw 0), a defined, unit-tested value.

def pose_from_lookat(eye, target) -> tuple[float, float]:
    """(pitch, yaw) in degrees for a camera at `eye` aimed at `target`. Raises ValueError
    when the two coincide (no direction)."""
    dx, dy, dz = (target[0] - eye[0], target[1] - eye[1], target[2] - eye[2])
    horiz = math.hypot(dx, dy)
    if horiz == 0.0 and dz == 0.0:
        raise ValueError("look target coincides with the camera position")
    return (math.degrees(math.atan2(dz, horiz)), math.degrees(math.atan2(dy, dx)))


def pose_from_orbit(target, radius: float, azimuth: float, elev: float = 0.0
                    ) -> tuple[tuple[float, float, float], float, float]:
    """Camera on a ring of `radius` around `target`, aimed inward → (eye, pitch, yaw) in
    degrees. `azimuth` is the ring angle (0° puts the camera on the target's +X side, 90°
    on +Y — matching yaw's sense); `elev` lifts the ring (+90° = straight above)."""
    az, el = math.radians(azimuth), math.radians(elev)
    eye = (target[0] + radius * math.cos(el) * math.cos(az),
           target[1] + radius * math.cos(el) * math.sin(az),
           target[2] + radius * math.sin(el))
    # Aim back at the centre: exact opposite of the ring direction. Computing from the ring
    # angles directly (not pose_from_lookat) keeps straight-above/below (cos(el)≈0) exact.
    pitch = -elev
    yaw = (azimuth + 180.0) % 360.0
    return eye, pitch, yaw


def resolve_pose(shot: Shot, actor_point) -> ResolvedShot:
    """Turn a validated Shot into the backend-facing ResolvedShot. `actor_point(name)` maps
    an actor name to its aim point (brush → world-AABB centre, point actor → Location) and
    raises KeyError on an unknown name — the caller (dispatch front half) converts that to
    the named exit-2, all-or-nothing across the batch."""
    if shot.orbit is not None:
        eye, pitch, yaw = pose_from_orbit(actor_point(shot.orbit), shot.radius,
                                          shot.azimuth, shot.elev)
        return ResolvedShot(eye=eye, pitch=pitch, yaw=yaw, name=shot.name)
    eye = actor_point(shot.at) if isinstance(shot.at, str) else shot.at   # at:@actor → its Location
    if shot.rot is not None:
        return ResolvedShot(eye=eye, pitch=shot.rot[0], yaw=shot.rot[1], name=shot.name)
    target = actor_point(shot.look) if isinstance(shot.look, str) else shot.look
    try:
        pitch, yaw = pose_from_lookat(eye, target)
    except ValueError as e:
        raise ValueError(f"{e} (at:{eye[0]:g},{eye[1]:g},{eye[2]:g})") from None
    return ResolvedShot(eye=eye, pitch=pitch, yaw=yaw, name=shot.name)


def shot_filename(shot: Shot, index: int, taken: set[str]) -> str:
    """Output stem for shot `index` (0-based): `name:STEM` override, else `shot-NN`
    (1-based, zero-padded). Collisions get a `-<k>` disambiguator — never silently
    overwrites within a run. (Same dedup semantics as the legacy `frame_filename`.)"""
    stem = shot.name if shot.name else f"shot-{index + 1:02d}"
    base, k = stem, 2
    while stem in taken:
        stem, k = f"{base}-{k}", k + 1
    taken.add(stem)
    return f"{stem}.png"

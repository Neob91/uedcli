"""Tests for the SHOT-token grammar + pose trig in `preview_shots` (the `--native`/`--game`
shared front half). The legacy `parse_frame` grammar keeps its own tests in
`test_preview_shots.py` until the S6 cutover deletes both together."""
from __future__ import annotations

import math

import pytest

from uedcli.preview_shots import (ResolvedShot, Shot, parse_shot, pose_from_lookat,
                                  pose_from_orbit, resolve_pose, shot_filename)


# --- parse_shot: valid forms -----------------------------------------------------------


def test_parse_absolute_rot():
    s = parse_shot("at:100,-200,50;rot:-8192,16384")     # UU in → -45°, 90°
    assert s == Shot(at=(100.0, -200.0, 50.0), rot=(-45.0, 90.0))


def test_parse_look_point_with_name():
    s = parse_shot("at:0,0,0;look:512,0,128;name:hall")
    assert s.at == (0.0, 0.0, 0.0)
    assert s.look == (512.0, 0.0, 128.0)
    assert s.name == "hall"


def test_parse_look_actor():
    s = parse_shot("at:64,64,32;look:@Keep_8ghqei")
    assert s.look == "Keep_8ghqei"


def test_parse_orbit_full():
    s = parse_shot("orbit:@Tower;radius:600;azimuth:8192;elev:4096;name:ring")   # UU in → 45°, 22.5°
    assert (s.orbit, s.radius, s.azimuth, s.elev, s.name) == ("Tower", 600.0, 45.0, 22.5, "ring")


def test_parse_orbit_elev_defaults_to_zero():
    assert parse_shot("orbit:@T;radius:10;azimuth:0").elev == 0.0


def test_parse_keys_case_insensitive_and_spaced():
    s = parse_shot("AT: 1,2,3 ;ROT: 0, 32768")     # UU in → 180°
    assert s.at == (1.0, 2.0, 3.0) and s.rot == (0.0, 180.0)


# --- parse_shot: every malformed form names the token ------------------------------------


@pytest.mark.parametrize("token,match", [
    ("Keep_8ghqei", "old TARGET"),                        # old bare-target grammar
    ("all", "old TARGET"),                                # old reserved word
    ("Keep:wire=hero", "unknown field"),                  # old mode/name form
    ("512,0,256@top", "old TARGET"),                      # ancient POS@ROT form
    ("at:0,0,0", "exactly one of rot:/look:/orbit:"),     # no aim
    ("at:0,0,0;rot:0,0;look:1,1,1", "exactly one"),       # two aims
    ("rot:0,0", "needs at:"),                             # rot without eye
    ("at:0,0;rot:0,0", "3 comma-separated"),              # short vector
    ("at:0,0,x;rot:0,0", "non-numeric"),                  # bad number
    ("at:0,0,0;rot:5", "2 comma-separated"),              # rot needs pitch,yaw
    ("at:0,0,0;rot:0,0;rot:1,1", "duplicate field"),
    ("at:0,0,0;look:@", "needs an actor name"),
    ("orbit:Tower;radius:1;azimuth:0", "takes @ActorName"),
    ("orbit:@T;azimuth:0", "needs radius"),
    ("orbit:@T;radius:1", "needs azimuth"),
    ("orbit:@T;radius:0;azimuth:0", "radius must be > 0"),
    ("orbit:@T;radius:-5;azimuth:0", "radius must be > 0"),
    ("orbit:@T;radius:1;azimuth:0;at:0,0,0", "self-contained"),
    ("at:0,0,0;rot:0,0;radius:9", "only applies to orbit"),
    ("at:0,0,0;rot:0,0;name:../evil", "invalid name"),
    ("at:0,0,0;rot:0,0;name:", "empty value"),
    ("at:0,0,0;zoom:2", "unknown field"),
])
def test_parse_shot_rejects(token, match):
    with pytest.raises(ValueError, match=match):
        parse_shot(token)


def test_every_parse_error_names_the_token():
    for token in ("Keep", "at:0,0,0", "orbit:@T;radius:1", "at:1,2;rot:0,0"):
        with pytest.raises(ValueError) as e:
            parse_shot(token)
        assert token in str(e.value)


# --- pose trig ---------------------------------------------------------------------------


def test_lookat_along_plus_x_is_zero_zero():
    assert pose_from_lookat((0, 0, 0), (100, 0, 0)) == (0.0, 0.0)


def test_lookat_along_plus_y_is_yaw_90():
    pitch, yaw = pose_from_lookat((0, 0, 0), (0, 100, 0))
    assert (pitch, yaw) == (0.0, 90.0)


def test_lookat_up_45():
    pitch, yaw = pose_from_lookat((0, 0, 0), (100, 0, 100))
    assert pitch == pytest.approx(45.0)
    assert yaw == 0.0


def test_lookat_straight_down_and_up():
    pitch, yaw = pose_from_lookat((0, 0, 500), (0, 0, 0))
    assert (pitch, yaw) == (-90.0, 0.0)                   # yaw defined (0) at the pole
    pitch, yaw = pose_from_lookat((0, 0, 0), (0, 0, 500))
    assert (pitch, yaw) == (90.0, 0.0)


def test_lookat_negative_x_is_yaw_180():
    pitch, yaw = pose_from_lookat((100, 0, 0), (0, 0, 0))
    assert (pitch, abs(yaw)) == (0.0, 180.0)


def test_lookat_coincident_raises():
    with pytest.raises(ValueError, match="coincides"):
        pose_from_lookat((5, 5, 5), (5, 5, 5))


def test_orbit_azimuth_zero_puts_eye_plus_x_aims_back():
    eye, pitch, yaw = pose_from_orbit((0, 0, 0), 100, 0)
    assert eye == pytest.approx((100.0, 0.0, 0.0))
    assert (pitch, yaw) == (0.0, 180.0)                   # aimed back at the centre


def test_orbit_elev_lifts_and_pitches_down():
    eye, pitch, yaw = pose_from_orbit((0, 0, 0), 100, 90, 30)
    assert eye[2] == pytest.approx(50.0)                  # sin(30°)·100
    assert pitch == -30.0
    assert yaw == pytest.approx(270.0)
    # the aim really points back at the centre: cross-check vs pose_from_lookat
    lp, ly = pose_from_lookat(eye, (0, 0, 0))
    assert lp == pytest.approx(pitch, abs=1e-9)
    assert math.cos(math.radians(ly)) == pytest.approx(math.cos(math.radians(yaw)))
    assert math.sin(math.radians(ly)) == pytest.approx(math.sin(math.radians(yaw)))


def test_orbit_straight_above_is_exact():
    eye, pitch, yaw = pose_from_orbit((10, 20, 30), 100, 0, 90)
    assert eye == pytest.approx((10.0, 20.0, 130.0))
    assert pitch == -90.0                                 # straight down, no gimbal ambiguity
    assert yaw == 180.0


# --- resolve_pose ------------------------------------------------------------------------


def _points(mapping):
    def actor_point(name):
        return mapping[name]
    return actor_point


def test_resolve_rot_passthrough():
    r = resolve_pose(parse_shot("at:1,2,3;rot:-8192,8192;name:x"), _points({}))   # UU in → -45°, 45°
    assert r == ResolvedShot(eye=(1.0, 2.0, 3.0), pitch=-45.0, yaw=45.0, name="x")


def test_resolve_look_actor_uses_actor_point():
    r = resolve_pose(parse_shot("at:0,0,0;look:@Tgt"), _points({"Tgt": (0, 200, 0)}))
    assert (r.pitch, r.yaw) == (0.0, 90.0)


def test_resolve_orbit_uses_actor_point():
    r = resolve_pose(parse_shot("orbit:@Tgt;radius:100;azimuth:0"), _points({"Tgt": (50, 0, 0)}))
    assert r.eye == pytest.approx((150.0, 0.0, 0.0))
    assert (r.pitch, r.yaw) == (0.0, 180.0)


def test_resolve_look_at_own_eye_raises_with_position():
    with pytest.raises(ValueError, match="coincides.*at:5,5,5"):
        resolve_pose(parse_shot("at:5,5,5;look:5,5,5"), _points({}))


def test_resolve_unknown_actor_propagates_keyerror():
    with pytest.raises(KeyError):
        resolve_pose(parse_shot("at:0,0,0;look:@Nope"), _points({}))


# --- shot_filename -----------------------------------------------------------------------


def test_filename_default_is_zero_padded_index():
    taken: set = set()
    assert shot_filename(Shot(rot=(0, 0), at=(0, 0, 0)), 0, taken) == "shot-01.png"
    assert shot_filename(Shot(rot=(0, 0), at=(0, 0, 0)), 11, taken) == "shot-12.png"


def test_filename_name_override_and_dedup():
    taken: set = set()
    assert shot_filename(Shot(rot=(0, 0), at=(0, 0, 0), name="hero"), 0, taken) == "hero.png"
    assert shot_filename(Shot(rot=(0, 0), at=(0, 0, 0), name="hero"), 1, taken) == "hero-2.png"
    assert shot_filename(Shot(rot=(0, 0), at=(0, 0, 0), name="hero"), 2, taken) == "hero-3.png"


def test_parse_at_actor():
    s = parse_shot("at:@PathNode7;rot:-8192,16384")     # UU in → -45°, 90°
    assert s.at == "PathNode7" and s.rot == (-45.0, 90.0)


def test_resolve_at_actor_uses_actor_point():
    r = resolve_pose(parse_shot("at:@Spawn;rot:0,8192"), _points({"Spawn": (10, 20, 30)}))   # UU in → yaw 45°
    assert r.eye == (10, 20, 30) and r.yaw == 45.0

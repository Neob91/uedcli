"""One STATIC frame for UnrealEngine-1's PROCEDURAL (bitmap-less) texture classes.

`Fire.u` ships four texture classes the engine paints every frame in native C++ instead of
storing a bitmap: `FireTexture`, `WaveTexture`, `WetTexture` and `IceTexture` (their bases
`FractalTexture` and `WaterTexture` are never instantiated in either shipped corpus). Their mips
serialize with `DataCount == 0`, so `utexture` has nothing to decode — which is why the draft
renderers used to paint them a flat placeholder colour.

This module paints one representative frame instead, so a barrel fire reads as fire and a pool
reads as water. It is PURE PIXEL MATH: it takes already-decoded inputs (`ProceduralInput`) and
returns `(rgb, mask)` in the shape `utexture`'s bitmap decoders return, and knows nothing about
packages, refs or resolvers.

WHAT IS MEASURED FACT AND WHAT IS APPROXIMATION
-----------------------------------------------
`Fire.dll` is native code we have no disassembly of, so the per-pixel algorithms below are NOT
reverse-engineered. What IS measured — over the 216 procedural exports in the `Textures/` trees
of a Deus Ex install and an Unreal Gold one (124 `FireTexture`, 81 `WetTexture`, 5 `WaveTexture`,
6 `IceTexture`), with the counter-examples counted rather than waved past:

* A `FireTexture` body carries a `TArray<FSpark>` after its (empty) mip array: a compact count
  that equals the body's own `NumSparks` on all 124, then 8 bytes per spark. Byte 0 equals the
  texture's `SparkType`; bytes 2/3 are X/Y, and every one of them lands inside `USize`x`VSize` on
  all 124 — so the spark POSITIONS are real stored data. Byte 1 is that spark's own heat: it
  equals the texture's `FX_Heat` on 94 of the 121 that carry any sparks, and genuinely varies per
  spark on the other 27 (`NaliFX.fireplace`: 73 sparks over six heats under an `FX_Heat` of 125).
  The renderer reads the per-spark byte, so the exceptions cost nothing — but "byte 1 IS
  `FX_Heat`" would be wrong.
* A `WaterTexture` (`WaveTexture`/`WetTexture`) carries its drops as a static-array property
  `Drops[]`, 8 bytes each, of which the first `NumDrops` are live. Byte 0 is the drop's own type,
  byte 1 its depth, bytes 2/3 its X/Y — and those land inside `USize/2` x `VSize/2` on all 92, so
  the wave field is simulated at HALF the texture resolution.
* Every one of the 216 carries a decodable `Palette`, and every `WetTexture`/`IceTexture` a
  `SourceTexture` (`IceTexture` also a `GlassTexture`) — all decoded and used here.

(Those counts are of texture EXPORTS in `Textures/*.utx` only. Counting a whole install, code
packages included, gives more of each — `package-format.md`'s 208 `FireTexture` is that wider
sweep of the Deus Ex tree, not a contradiction.)

Everything else — how a spark becomes a flame, how a drop becomes a ripple, how the ripple is
shaded — is a REASONED APPROXIMATION built to match the behaviour Epic's own "Animating
Real-Time Textures" manual describes (mirrored at
<https://www.zx.net.nz/mirror/unreal.epicgames.com/Fire/AnimatingTextures.htm>): fire rises; a
wave texture is "a pseudo-phong-shaded rendering of a physically simulated water surface" whose
rest height is 128; a wet texture distorts its source HORIZONTALLY ONLY; an ice texture distorts
its source by a `GlassTexture` read as "an 8-bit distortion vector field". It is not claimed to
match the engine pixel for pixel, and it is not animated: one frame, derived only from what the
file stores, so the same package always renders the same pixels.

WHY THERE IS NO ELAPSED-TIME PARAMETER
---------------------------------------
A `t` (seconds elapsed) argument was considered so `class preview`/`level photo --native` could
render "well into a live game" instead of an arbitrary instant. The manual confirms fire and water
are real iterative sims that "need some warming-up time to attain a stable appearance" but — its
own words — never reach a true steady state (sparks/drops keep perturbing the field forever). None
of that per-tick state (spark emission timing, drop spawn/decay, wave propagation speed) is in the
package — the body stores only the CURRENT spark/drop positions and a `t=0` `FX_Phase`/
`UPosition`/`VPosition`, no history — so a `t` parameter would have to invent a timing/speed
constant nowhere in the file: not a more correct frame, a differently-fabricated one.
`_render_fire`'s closed-form fixed point already renders the diffusion's long-run pattern (see its
own comment) rather than frame 0 — as close to "well after ignition" as an honest single frame
gets. `_wave_field`'s radial cosine-times-decay is the same kind of long-run envelope for a
continuously-sourced ripple; advancing it by any `t` would only rotate its phase, the same pattern
you get from picking a different `FX_Phase`. So nothing here takes a time argument.

The `FX_*` bytes have no recoverable defaults — those classes' numeric defaults are native C++
with empty script `defaultproperties` — so a property the body omits falls to a stand-in
constant here (`_DEFAULTS`), named and gathered in one place rather than scattered.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

_TAU = 2.0 * math.pi

# Stand-ins for the `FX_*`/render bytes a body omits. UE1 omits any property equal to its class
# default, and these classes' defaults live in native C++ with nothing script-side to read
# (`dev/docs/unrealed/leveldesign/kb/textures.md` §6.4), so an absent property's real value is
# not recoverable offline. These are the draft renderer's stand-ins, not measured defaults.
_DEFAULTS = {
    "RenderHeat": 255, "FX_Size": 96,
    "FX_Frequency": 8, "FX_Phase": 0, "FX_Radius": 128, "FX_Amplitude": 255,
    "WaveAmp": 128, "BumpMapLight": 0, "BumpMapAngle": 128, "PhongRange": 128, "PhongSize": 32,
    "Amplitude": 255,
}

# Draft-render work bounds. The renderers are called from `class preview` / `level photo
# --native`, which decode many textures per picture, so the ripple pass is capped rather than
# allowed to scale with a 256-drop 256x256 texture (which would cost seconds in Python). Both
# caps only reduce how much of the surface is disturbed; neither changes the shading model.
MAX_DROPS = 96
MAX_RIPPLE_REACH = 24                    # half-resolution texels


# --- inputs ---------------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class Spark:
    """One live `FSpark` out of a `FireTexture` body's trailing array. `x`/`y` are texel
    coordinates in the texture's own `USize`x`VSize` grid; `heat` is the spark's intensity as a
    palette-index-scale byte (see the module docstring for how the layout was measured)."""
    kind: int
    heat: int
    x: int
    y: int


@dataclass(frozen=True, kw_only=True)
class Drop:
    """One live `ADrop` out of a `WaterTexture` body's `Drops[]` static array. `x`/`y` are
    HALF-resolution grid coordinates (`USize/2` x `VSize/2`) — measured, see the module
    docstring — and `depth` is the drop's own displacement byte."""
    kind: int
    depth: int
    x: int
    y: int


@dataclass(frozen=True, kw_only=True)
class SampledTexture:
    """An already-decoded texture this generator reads pixels out of — a resolved
    `SourceTexture`/`GlassTexture`. Same buffer shapes as `utexture.DecodedTexture`
    (`width*height*3` RGB, `width*height` mask, 1 = opaque), carried as a plain value so this
    module never touches the resolver."""
    width: int
    height: int
    rgb: bytes
    mask: bytes


@dataclass(frozen=True, kw_only=True)
class ProceduralInput:
    """Everything a generator paints from. `props` is the body's decoded tagged-property dict
    (`name -> (ptype, value)`, exactly `utexture.TextureObj.props`); `palette` is the texture's
    own decoded palette; `sparks`/`drops` are the live stored particles; `sources` maps an
    object-ref property NAME (`"SourceTexture"`, `"GlassTexture"`) to the texture it resolved
    to, and carries exactly the keys that generator's `Generator.ref_props` declares."""
    width: int
    height: int
    props: Mapping[str, tuple]
    palette: Sequence[tuple[int, int, int]] = ()
    sparks: Sequence[Spark] = ()
    drops: Sequence[Drop] = ()
    sources: Mapping[str, SampledTexture] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Generator:
    """A procedural class's renderer plus what the caller must decode for it first.

    `render` returns `(rgb, mask)`, or None when the body carries nothing to paint FROM — a fire
    with an empty spark array, a wave with no drops. Those textures say nothing about how they
    look, so the caller falls back to its placeholder rather than this module inventing a
    pattern. `ref_props` names the object-ref properties whose textures must be resolved into
    `ProceduralInput.sources`; `needs_palette` says whether the texture's own palette is read (a
    `WetTexture`/`IceTexture` takes its colours from its source instead)."""
    render: Callable[[ProceduralInput], tuple[bytes, bytes] | None]
    ref_props: tuple[str, ...] = ()
    needs_palette: bool = True


# --- body-blob parsing ----------------------------------------------------------------------

SPARK_BYTES = 8


def _compact_index(buf: bytes, pos: int) -> tuple[int, int]:
    """FCompactIndex (UE1's signed variable-length int), the one field this module decodes
    itself — the spark array is a raw blob handed over as bytes."""
    b = buf[pos]; pos += 1
    neg, val = b & 0x80, b & 0x3F
    if b & 0x40:
        shift = 6
        while pos < len(buf):
            b = buf[pos]; pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
    return (-val if neg else val), pos


def parse_sparks(trailing: bytes, count: int) -> tuple[Spark, ...]:
    """A `FireTexture` body's trailing `TArray<FSpark>` → its sparks.

    `trailing` starts at the array's compact-index count, which the caller has already read as
    `count` (it equals the body's `NumSparks` on every sample measured); this re-reads it only
    to find where the elements begin, and trusts whichever of the two is SMALLER so a truncated
    or over-declared array yields fewer sparks rather than reading past the blob.
    """
    if not trailing:
        return ()
    stored, pos = _compact_index(trailing, 0)
    n = max(0, min(stored, count, (len(trailing) - pos) // SPARK_BYTES))
    return tuple(Spark(kind=trailing[pos + k * 8], heat=trailing[pos + k * 8 + 1],
                       x=trailing[pos + k * 8 + 2], y=trailing[pos + k * 8 + 3])
                 for k in range(n))


def parse_drops(elements: Mapping[int, bytes], count: int) -> tuple[Drop, ...]:
    """A `WaterTexture` body's `Drops[]` elements (raw 8-byte values keyed by static-array index)
    → the LIVE drops, those at indices `0..count-1`.

    Two things separate the live drops from the rest. The array keeps stale slots past `NumDrops`
    — `WaterRings2` stores 137 of them behind a `NumDrops` of 6 — and UE1 omits an element
    equal to its all-zero default, so an index inside the live range can be missing. A missing one
    is a zero-depth drop that displaces nothing: it is skipped, never shifting its neighbours.
    """
    out = []
    for k in range(max(0, count)):
        raw = elements.get(k)
        if raw is not None and len(raw) >= 4:
            out.append(Drop(kind=raw[0], depth=raw[1], x=raw[2], y=raw[3]))
    return tuple(out)


# --- shared helpers -------------------------------------------------------------------------

def _byte(props: Mapping[str, tuple], name: str) -> int:
    """A stored byte property, or its `_DEFAULTS` stand-in when the body omits it — or when it
    stores something that is not a number at all, which an untrusted package is free to do."""
    value = props.get(name, (0, None))[1]
    if not isinstance(value, int) or isinstance(value, bool):
        value = _DEFAULTS.get(name, 0)
    return max(0, min(255, value))


def _pan(props: Mapping[str, tuple], name: str) -> int:
    """An `IceTexture`'s saved scroll position as a whole-texel offset. Absent, non-numeric,
    infinite or NaN all mean "no offset" — a package is untrusted input and `int(inf)` raises."""
    value = props.get(name, (0, None))[1]
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
        return 0
    return int(value) if -1e9 < value < 1e9 else 0


def _palette_pixels(indices: Sequence[int],
                    palette: Sequence[tuple[int, int, int]]) -> tuple[bytes, bytes]:
    """Palette indices → `(rgb, mask)`, the same P8 convention `utexture._decode_linear1` uses:
    index 0 is the transparent texel. A short palette is padded with black so a hostile or
    truncated one cannot index out of range."""
    pal = list(palette) + [(0, 0, 0)] * max(0, 256 - len(palette))
    rgb = bytearray(len(indices) * 3)
    mask = bytearray(len(indices))
    for i, idx in enumerate(indices):
        r, g, b = pal[idx]
        rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2] = r, g, b
        mask[i] = 1 if idx else 0
    return bytes(rgb), bytes(mask)


def _copy_texel(src: SampledTexture, su: int, sv: int,
                rgb: bytearray, mask: bytearray, dst: int) -> None:
    o = (sv * src.width + su) * 3
    rgb[dst * 3:dst * 3 + 3] = src.rgb[o:o + 3]
    mask[dst] = src.mask[sv * src.width + su] if sv * src.width + su < len(src.mask) else 1


# --- FireTexture ----------------------------------------------------------------------------
# APPROXIMATION. The manual states the behaviour (`bRising` picks between two algorithms, the
# rising one making the fire visibly climb; `RenderHeat` tunes overall flame size; `FX_Heat`
# sets spark brightness) but no formula. What is painted here is the steady state a rising
# heat-diffusion filter converges to: each spark deposits its stored heat at its stored
# position, then ONE bottom-to-top sweep carries each row's heat into the row above through a
# 3-tap horizontal blur scaled by a per-row carry factor < 1. That is the classic Unreal-era
# fire filter collapsed from "iterate until steady" to its fixed point, which costs one pass
# over the image instead of one per row. This already IS the "well after ignition" frame: no
# separate elapsed-time parameter is needed (module docstring, "WHY THERE IS NO ELAPSED-TIME
# PARAMETER").

_CARRY_RISING = 0.955
_CARRY_STILL = 0.900              # `bRising` false — the manual's "less upward movement"


def _deposit(heat: list[float], w: int, h: int, cx: int, cy: int,
             amount: float, radius: int) -> None:
    """Add one spark's heat over a small disc, falling off linearly to its edge. Wraps both
    axes — a UE1 texture tiles, so a spark at the edge lights the opposite one."""
    for dy in range(-radius, radius + 1):
        yy = ((cy + dy) % h) * w
        for dx in range(-radius, radius + 1):
            d = math.hypot(dx, dy)
            if d <= radius:
                k = yy + (cx + dx) % w
                heat[k] = min(255.0, heat[k] + amount * (1.0 - d / (radius + 1.0)))


def _render_fire(pin: ProceduralInput) -> tuple[bytes, bytes] | None:
    if not any(sp.heat for sp in pin.sparks):
        # No spark, or every stored spark at heat 0 -- nothing to burn, and the heat a spark
        # would have had is a native default we cannot read. Both shapes ship: `UnrealShare.u`'s
        # `BlueShield` stores 56 sparks all at heat 0. See `Generator.render`.
        return None
    w, h = pin.width, pin.height
    heat = [0.0] * (w * h)
    radius = max(1, min(4, 1 + _byte(pin.props, "FX_Size") // 96))
    for sp in pin.sparks:
        _deposit(heat, w, h, sp.x % w, sp.y % h, float(sp.heat), radius)
    # `bRising` is stored on 25 of the 124 sampled fire textures and always as True, so its
    # native default is False (UE1 omits a property equal to its default) — hence the still
    # carry for a body that does not mention it.
    carry = _CARRY_RISING if pin.props.get("bRising", (0, False))[1] else _CARRY_STILL
    for y in range(h - 2, -1, -1):
        row, below = y * w, (y + 1) * w
        for x in range(w):
            # Saturating, because the engine's heat buffer is a byte per texel: without the
            # clamp a cluster of overlapping sparks sums into the thousands and the plume above
            # it stays pinned at the palette's hottest entry for the whole texture.
            heat[row + x] = min(255.0, heat[row + x]
                                + carry * (0.50 * heat[below + x]
                                           + 0.25 * heat[below + (x - 1) % w]
                                           + 0.25 * heat[below + (x + 1) % w]))
    gain = _byte(pin.props, "RenderHeat") / 255.0
    return _palette_pixels([int(v * gain) for v in heat], pin.palette)


# --- the shared water height field ----------------------------------------------------------
# APPROXIMATION. The engine runs a wave simulation whose drops are sources; a static frame
# cannot replay that, so each live drop contributes a radially damped cosine centred on its
# stored position — the standing ripple such a source settles into. The grid is half the
# texture's resolution because that is where the stored drop coordinates live (module
# docstring). `FX_Frequency` sets the ripple wavelength, `FX_Radius` how far it reaches,
# `FX_Phase` its phase, `WaveAmp` and the drop's own depth byte its amplitude. No elapsed-time
# parameter: this envelope already is the long-run pattern a continuous point source settles
# into, and advancing it by any `t` would only rotate `FX_Phase` by an unmeasurable amount
# (module docstring, "WHY THERE IS NO ELAPSED-TIME PARAMETER").

def _wave_field(pin: ProceduralInput) -> tuple[list[float], int, int]:
    """The half-resolution displacement field, and its dimensions."""
    hw, hh = max(1, pin.width // 2), max(1, pin.height // 2)
    field = [0.0] * (hw * hh)
    # Four half-resolution texels is the shortest ripple the grid can carry without aliasing
    # into a checkerboard; `WaterRings2`'s `FX_Frequency` of 166 asks for less than one.
    wavelength = max(4.0, 64.0 / max(1, _byte(pin.props, "FX_Frequency")))
    decay = max(2.0, 1.0 + _byte(pin.props, "FX_Radius") / 8.0)
    reach = max(1, min(int(decay * 3.0), MAX_RIPPLE_REACH, hw, hh))
    phase = _byte(pin.props, "FX_Phase") / 256.0 * _TAU
    ripple = [math.cos(_TAU * r / wavelength + phase) * math.exp(-r / decay)
              for r in range(reach + 1)]
    gain = _byte(pin.props, "WaveAmp") / 255.0
    span, reach2 = range(-reach, reach + 1), reach * reach
    for drop in pin.drops[:MAX_DROPS]:
        amp = gain * drop.depth / 255.0
        cx, cy = drop.x % hw, drop.y % hh
        for dy in span:
            base = ((cy + dy) % hh) * hw
            for dx in span:
                d2 = dx * dx + dy * dy
                if d2 <= reach2:
                    field[base + (cx + dx) % hw] += amp * ripple[math.isqrt(d2)]
    return field, hw, hh


def _slopes(field: list[float], hw: int, hh: int) -> tuple[list[float], list[float], float]:
    """Central-difference slope of the field in x and y (wrapped), plus a normalising scale.

    The scale is twice the slope's RMS, so a typical slope lands around 0.5 whatever the
    texture's amplitude scale is. That is a draft-render exposure choice, not engine
    behaviour: without it a low-amplitude pool shades to one flat tone and a violent one
    clips to solid highlight."""
    gx, gy = [0.0] * (hw * hh), [0.0] * (hw * hh)
    total = 0.0
    for y in range(hh):
        row, up, down = y * hw, ((y - 1) % hh) * hw, ((y + 1) % hh) * hw
        for x in range(hw):
            ax = field[row + (x + 1) % hw] - field[row + (x - 1) % hw]
            ay = field[down + x] - field[up + x]
            gx[row + x], gy[row + x] = ax, ay
            total += ax * ax + ay * ay
    rms = math.sqrt(total / (hw * hh)) if total else 0.0
    return gx, gy, (1.0 / (2.0 * rms) if rms else 0.0)


# --- WaveTexture ----------------------------------------------------------------------------
# APPROXIMATION of the manual's "pseudo-phong-shaded rendering of a physically simulated water
# surface". The surface is bump-map shaded from the slope field above: `BumpMapLight` is the
# incident light's in-plane angle and `BumpMapAngle` the viewer's, per the manual, and the
# highlight sits where the slope faces their halfway direction. `PhongRange` is spent exactly
# as the manual describes it — as the share of the palette reserved for the highlight, so the
# diffuse term gets the remaining `255 - PhongRange` indices — and `PhongSize` tightens the
# highlight's falloff.

def _render_wave(pin: ProceduralInput) -> tuple[bytes, bytes] | None:
    if not pin.drops:
        return None                  # a flat surface carries no shape -- see `Generator.render`
    w, h = pin.width, pin.height
    field, hw, hh = _wave_field(pin)
    gx, gy, scale = _slopes(field, hw, hh)
    light = _byte(pin.props, "BumpMapLight") / 256.0 * _TAU
    view = _byte(pin.props, "BumpMapAngle") / 256.0 * _TAU
    lx, ly = math.cos(light), math.sin(light)
    hx, hy = lx + math.cos(view), ly + math.sin(view)
    norm = math.hypot(hx, hy) or 1.0
    hx, hy = hx / norm, hy / norm
    phong = _byte(pin.props, "PhongRange")
    diffuse_span = 255 - phong
    exponent = 1.0 + _byte(pin.props, "PhongSize") / 16.0

    shaded = [0] * (hw * hh)
    for i in range(hw * hh):
        sx, sy = gx[i] * scale, gy[i] * scale
        # Soft-clipped into -1..1 (`t/(1+|t|)`): a hard clamp turns the steep slopes right at a
        # drop into flat black and white bands instead of a crest.
        lit = sx * lx + sy * ly
        lit /= 1.0 + abs(lit)
        spec = sx * hx + sy * hy
        spec = max(0.0, spec / (1.0 + abs(spec))) ** exponent
        shaded[i] = max(0, min(255, int((0.5 + 0.5 * lit) * diffuse_span + spec * phong)))
    indices = bytearray(w * h)
    for y in range(h):
        src = min(hh - 1, y * hh // h) * hw
        row = y * w
        for x in range(w):
            indices[row + x] = shaded[src + min(hw - 1, x * hw // w)]
    return _palette_pixels(indices, pin.palette)


# --- WetTexture -----------------------------------------------------------------------------
# APPROXIMATION of "the distortion is horizontal only" (manual): the same wave field displaces
# each row's lookup into the `SourceTexture` sideways and nothing else. Colours come from the
# resolved source, so the wet texture's own palette is not read — the engine reindexes the
# source through it, but the source's decoded pixels are the closer answer for a draft frame.

def _render_wet(pin: ProceduralInput) -> tuple[bytes, bytes]:
    w, h = pin.width, pin.height
    src = pin.sources["SourceTexture"]
    field, hw, hh = _wave_field(pin)
    peak = max((abs(v) for v in field), default=0.0)
    swing = (max(1, w // 16) * _byte(pin.props, "FX_Amplitude") / 255.0 / peak) if peak else 0.0
    rgb, mask = bytearray(w * h * 3), bytearray(w * h)
    for y in range(h):
        row, wave = y * w, min(hh - 1, y * hh // h) * hw
        sv = min(src.height - 1, y * src.height // h)
        for x in range(w):
            shift = int(field[wave + min(hw - 1, x * hw // w)] * swing)
            su = (x * src.width // w + shift) % src.width
            _copy_texel(src, su, sv, rgb, mask, row + x)
    return bytes(rgb), bytes(mask)


# --- IceTexture -----------------------------------------------------------------------------
# APPROXIMATION of "distorts a SourceTexture using GlassTexture, interpreted as an 8-bit
# distortion vector field" (manual). One byte cannot BE a 2-D vector, so the vector taken here
# is the glass image's own local gradient — the refraction a bumpy pane gives — scaled by
# `Amplitude`. The pan is not invented: `UPosition`/`VPosition` are stored floats holding where
# the ice had scrolled to when the package was saved, so the frame is the saved one.
# `Frequency`/`HorizPanSpeed`/`VertPanSpeed`/`PanningStyle` drive the motion over time and have
# nothing to say about a single frame, so they are not read.

def _render_ice(pin: ProceduralInput) -> tuple[bytes, bytes]:
    w, h = pin.width, pin.height
    src, glass = pin.sources["SourceTexture"], pin.sources["GlassTexture"]
    gw, gh = glass.width, glass.height
    lum = [(glass.rgb[i * 3] * 2 + glass.rgb[i * 3 + 1] * 5 + glass.rgb[i * 3 + 2]) / 8.0
           for i in range(gw * gh)]
    swing = max(1, w // 8) * _byte(pin.props, "Amplitude") / 255.0 / 128.0
    pan_u, pan_v = _pan(pin.props, "UPosition"), _pan(pin.props, "VPosition")
    rgb, mask = bytearray(w * h * 3), bytearray(w * h)
    for y in range(h):
        row = y * w
        gy = min(gh - 1, y * gh // h)
        up, down = ((gy - 1) % gh) * gw, ((gy + 1) % gh) * gw
        for x in range(w):
            gx = min(gw - 1, x * gw // w)
            du = (lum[gy * gw + (gx + 1) % gw] - lum[gy * gw + (gx - 1) % gw]) * swing
            dv = (lum[down + gx] - lum[up + gx]) * swing
            su = (x * src.width // w + int(du) + pan_u) % src.width
            sv = (y * src.height // h + int(dv) + pan_v) % src.height
            _copy_texel(src, su, sv, rgb, mask, row + x)
    return bytes(rgb), bytes(mask)


# --- the registry ---------------------------------------------------------------------------
# Keyed by CASEFOLDED bare class name. `FractalTexture` deliberately has no entry: the base
# class is never instantiated in either shipped corpus, so there is no content to check a
# renderer for it against. Anything absent from here keeps `utexture`'s existing `no-mip-data`
# behaviour, placeholder and all.

GENERATORS: dict[str, Generator] = {
    "firetexture": Generator(render=_render_fire),
    "wavetexture": Generator(render=_render_wave),
    "wettexture": Generator(render=_render_wet, ref_props=("SourceTexture",),
                            needs_palette=False),
    "icetexture": Generator(render=_render_ice,
                            ref_props=("SourceTexture", "GlassTexture"), needs_palette=False),
}


def generator_for(class_name: str) -> Generator | None:
    """The generator for a bare texture class name, or None when we do not paint that class."""
    return GENERATORS.get(class_name.casefold())

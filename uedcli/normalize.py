"""Canonical normalization so diffs/drift are authored-only and stable.

Verified (spec Appendix B): no-op exports differ only in LevelInfo volatile
fields; after IMPORTADD+REBUILD untouched brushes "change" only in computed
polygon Link indices. A faithful audit ignores those.
"""
from __future__ import annotations

import copy
import hashlib
import re
import struct
from dataclasses import dataclass
from decimal import Decimal

from .model import Actor, Level
from .emit import emit_actor, emit_brush
from .typedprops import ActorValues, prop_key, typed_value

# M2 (design D-H): a live MAP EXPORT writes the level's own structural object refs with the
# `MyLevel.` package prefix; an offline UCC batchexport of the saved .dx writes the on-disk
# package STEM instead. The stem is not authored content — rewrite it to a fixed sentinel so a
# UCC export hashes EQUAL to a live MAP EXPORT (else base/theirs/post-verify never match and
# every apply fails). Only the level's own structural classes are self-refs; refs into OTHER
# packages (Texture'Engine.X', Music'Pkg.Y') are real dependencies and are left verbatim.
# DeusExLevelInfo BEFORE LevelInfo: `\bLevelInfo` can't match the LevelInfo suffix inside
# `DeusExLevelInfo'…'` (no word boundary at X→L), so match the full class token, longest first.
# NOTE: matches only the single-segment `Class'pkg.Obj'` form (the self-ref classes here are
# direct children of the level package, no Group segment). A future grouped self-ref class would
# need the object group widened to `(\.[A-Za-z0-9_]+)+'`.
_SELF_REF_CLASSES = ("DeusExLevelInfo", "LevelInfo", "Model", "Brush")
_SELF_REF = re.compile(
    r"(\b(?:%s)')([A-Za-z0-9_]+)(\.[A-Za-z0-9_]+')" % "|".join(_SELF_REF_CLASSES))
_CANONICAL_PKG = "MyLevel"


def canonicalize_self_refs(t3d: str) -> str:
    """Rewrite the package stem of the level's own structural object refs to `MyLevel` (M2)."""
    return _SELF_REF.sub(lambda m: f"{m.group(1)}{_CANONICAL_PKG}{m.group(3)}", t3d)

# Computed/volatile actor properties — stripped before diffing. NavigationPointList/PawnList are
# LevelInfo runtime actor-list heads, rebuilt on load (LevelInfo extraction spike) — pure noise.
# next/prevNavigationPoint (added 2026-06-21) are the SAME kind of runtime pathnode-graph link,
# just per-actor instead of per-level: UE1 rebuilds the NavigationPoint doubly-linked list via
# `PATHS DEFINE`, which materialize.py never runs, so it never survives a `MAP NEW` + FULL
# RE-IMPORT (confirmed live: present in a base-content map's `result/` snapshot, absent from
# its freshly re-exported .dx). `Level`/`bSelected` added 2026-06-21 (debugging a
# never-before-materialized actor's first apply): `Level=LevelInfo'MyLevel.<name>'` is the
# level's own self-reference, recomputed on every import/materialize regardless of authored
# intent; `bSelected=True` is GUI selection state left over from the just-completed
# paste/import, never meaningful level content.
# `Tag` is NOT in this set — it's real, sometimes-authored content (`tests/fixtures/
# add_light.t3d` carries a deliberate `Tag=SpikeProbe`; GPT-5.4 review, 2026-06-21, caught an
# earlier version of this fix that stripped it unconditionally, which would have silently
# erased it from every actor on its next normalization/canonical emit). Only the editor's
# OWN default-stamp — `Tag` equal to the actor's bare class name, which it sets on any actor
# that never had an explicit `Tag` — is noise, and even that is dropped ONLY on the throwaway
# compare view (`_actor_values`, which also guards it on the class not defaulting `Tag`), never
# here: this list feeds the durable trunk emit.
# What the post-verify COMPARES is only AUTHORED content. A property is authored iff it is
# `var()`-EDITABLE (CPF_Edit in the schema, `ClassInfo.editable`) OR one of the few authored through
# UnrealEd's SPECIAL editors — which the UnrealScript compiler marks non-editable: `PrePivot` (the
# pivot tool) and a mover's `KeyPos`/`KeyRot` (the keyframe tool). Every OTHER non-editable property
# is engine-managed state the level author never sets — `Region`/`OldLocation`/`bSelected` (load),
# `SavedPos`/`BasePos` (mover PostLoad), the nav-graph arrays (PATHS BUILD),
# `DistanceFromPlayer`/`LastRenderTime` (per-frame), `FootRegion` (load) — and is dropped from the
# compare. This one schema-read rule replaces a hand-maintained computed-prop list (owner ruling
# 2026-08-24: "exclude non-editable properties automatically").
_RETAIN_NONEDIT: frozenset[str] = frozenset({"prepivot", "keypos", "keyrot"})
# Engine-managed props with NO schema entry to read a flag from, so they stay matched by name:
# `AIProfile(N)` (indexed navigation weight) by prefix, `prevNavigationPoint` (native; its pair
# `nextNavigationPoint` IS a `var` and the edit-rule drops it) exactly.
_COMPUTED_PREFIXES = ("aiprofile",)
_COMPUTED_GLOBAL: frozenset[str] = frozenset({"prevnavigationpoint"})
# INGEST strip (`normalize_actor`) is schema-free — it feeds the durable trunk and the generator
# snippet reader with no project context — so it can only match by NAME. It drops the long-known
# engine-managed names so they never enter the git-tracked trunk (hygiene only; the compare's
# edit-rule is the complete guarantee). Newer transient props (DistanceFromPlayer, …) are left in
# the trunk and stripped at compare, so no re-import churns the tree.
_INGEST_NAMES: frozenset[str] = frozenset({
    "timeseconds", "summary", "region", "oldlocation", "navigationpointlist", "pawnlist",
    "nextnavigationpoint", "prevnavigationpoint", "level", "bselected",
    "basepos", "baserot", "savedpos", "savedrot"})

# The red builder brush's actor Name is editor-version/counter-dependent (Brush0/Brush1/…),
# so it is NOT a reliable discriminator (Task 4a). Its inner brush MODEL is the reserved
# unnumbered "Brush"; that + no CsgOper identifies it (see is_builder_brush).
BUILDER_BRUSH_NAME = "Brush0"          # kept for the `actor add` snippet skip in dispatch
BUILDER_BRUSH_MODEL_NAME = "Brush"


def is_computed_key(key: str) -> bool:
    """INGEST strip (schema-free, feeds the durable trunk): whether `key` is a long-known
    engine-managed prop matched by NAME. **Case-insensitive** (FName semantics). Shared by
    `normalize`'s strip AND `actor prop`'s "won't persist" warning (decision 2026-06-26 12:41 UTC).
    The compare uses the schema-based edit-rule (`is_authored_prop`) instead."""
    k = key.casefold()
    if k in _INGEST_NAMES:
        return True
    return any(k.startswith(p) for p in _COMPUTED_PREFIXES)


def is_authored_prop(name_casefold: str, *, editable: bool | None) -> bool:
    """COMPARE rule: whether property `name_casefold` is AUTHORED content the post-verify compares.
    True iff it is `var()`-editable (`editable`, from `ClassInfo.editable`) or a special-editor
    exception (`PrePivot`, mover `KeyPos`/`KeyRot`). An unknown property (`editable is None`) is kept
    and compared untyped. Non-editable engine state — and the schema-less `AIProfile`/
    `prevNavigationPoint` — is not authored."""
    if name_casefold in _RETAIN_NONEDIT:
        return True
    if name_casefold in _COMPUTED_GLOBAL:
        return False
    if any(name_casefold.startswith(p) for p in _COMPUTED_PREFIXES):
        return False
    return editable is None or editable


def normalize_actor(a: Actor) -> None:
    """Strip computed props in place. Polygon Link indices are never emitted
    by emit_actor, so geometry normalization is implicit on re-emit.

    **NOTHING ELSE IS DROPPED HERE.** This function feeds `canonical_actor_t3d`, which is the
    durable git-tracked trunk emit AND the `MAP IMPORT` payload (`apply.py`) AND `actor show`, so
    anything omitted here is omitted from the map the engine actually builds — and the engine
    substitutes the CLASS DEFAULT for an omitted property, which is not zero for every class. Two
    such omissions used to live here and both silently built a wrong map (2026-07-25):

    * an all-zero `Location` was cleared to `None`, so an `Engine.Camera` (which defaults
      `Location=(X=-500,Y=-300,Z=300)`) authored at the origin re-imported 655 uu away;
    * a `Tag` equal to the actor's bare class name was deleted as the editor's default-stamp, but
      `TNM.Trestkon` defaults `Tag='Player'` (5 TNM classes default `Tag` at all), so an authored
      `Tag=Trestkon` — real content, since `Tag` drives trigger/event wiring — was erased and the
      actor came back tagged `Player`.

    Both jobs now belong to the TYPED COMPARE (`_actor_values`), which runs on the throwaway
    compare view only and resolves an omitted property to the real class default instead of to
    zero. The cost of keeping them here is one extra emitted line for actors whose value really is
    the default — which is exactly what UnrealEd's own importer accepts."""
    a.props = [(k, v) for k, v in a.props if not is_computed_key(k)]


def is_builder_brush(a: Actor) -> bool:
    """The red builder brush is a transient editing tool, not level content. Identify it by
    `Class=Brush` AND the reserved UNNUMBERED inner model name `Brush` (content brushes use
    `Model<N>`) AND no explicit `CsgOper` (its op is CSG_Active, which UnrealEd writes by
    OMISSION while every world brush carries an explicit CSG_Add/CSG_Subtract).

    Task 4a (spike, 2026-06-18) corrected the plan's `Name == "Brush0"` rule: a fresh editor
    numbers the builder brush `Brush1+`, so the exact name is NOT a constant — keying on it
    would FAIL to strip the builder brush in the common fresh-level case. The inner model name
    `Brush` is the strongest single signal; pair it with no-CsgOper. Name is no longer used.

    Matched by the BARE class name, so it fires whether the class arrives bare (`Class=Brush` from
    `MAP EXPORT`) or fully qualified (`Engine.Brush`, from the offline `.dx` decode the post-verify
    now uses)."""
    if (a.cls or "").rsplit(".", 1)[-1] != "Brush" or a.brush is None:
        return False
    if any(k == "CsgOper" for k, _ in a.props):
        return False
    return a.brush.model_name == BUILDER_BRUSH_MODEL_NAME


def normalize_level(level: Level) -> None:
    """Drop the transient builder brush, strip computed props, impose stable actor ordering."""
    level.actors = {n: a for n, a in level.actors.items() if not is_builder_brush(a)}
    for a in level.actors.values():
        normalize_actor(a)
    # Stable ordering: actors sorted by Name.
    level.actors = {name: level.actors[name] for name in sorted(level.actors)}


def level_order(level: Level) -> list[str]:
    """ALL actor Names in full export order (insertion order of level.actors), EXCLUDING the
    builder brush (via is_builder_brush — the SAME predicate normalize_level strips by, so the
    order set always equals the normalized content set; closes C-1 without name-only fragility).
    Every other actor is ordered (C2) — the brush subsequence is CSG precedence; non-brush order
    is preserved for determinism/stability. MUST be called BEFORE normalize_level re-sorts."""
    return [name for name, a in level.actors.items() if not is_builder_brush(a)]


# The engine Actors[0] singleton class (short name). NOT `DeusExLevelInfo`: that is a subclass
# but ships as an ORDINARY non-Actors[0] actor alongside a plain `LevelInfo` (verified against
# every DX/Maps/*.dx), so only the engine LevelInfo's engine-managed Name is canonicalized here.
_ENGINE_LEVELINFO = "LevelInfo"
# The fixed sentinel the singleton LevelInfo's actor Name is rewritten to for the compare.
# uedcli-allocated names always carry a `_<suffix>` and the engine's is `LevelInfo0`, so neither
# collides. A hand-authored NON-LevelInfo actor literally named `LevelInfo` COULD collide, and the
# compare view is a dict keyed by the canonical name — one entry would SILENTLY overwrite the other,
# making the post-verify blind to every change in that actor (a false pass, the exact failure this
# path exists to catch). `compare_view` therefore REFUSES a collision loudly instead (exit 2 naming
# the actor), rather than paying for a costlier unique name on every level.
LEVELINFO_CANONICAL_NAME = "LevelInfo"


def _is_levelinfo_actor(a: Actor) -> bool:
    return (a.cls or "").rsplit(".", 1)[-1] == _ENGINE_LEVELINFO


def _levelinfo_rename(level: Level) -> dict[str, str]:
    """The engine-managed LevelInfo singleton's actor NAME is NOT authored content, so it is
    canonicalized to a fixed sentinel before hashing/compare — exactly like the builder brush
    name is ignored (`is_builder_brush`). uedcli auto-names it on capture (`LevelInfo_4dosan`);
    a `MAP NEW` + FULL RE-IMPORT re-exports it under the editor's OWN name (`LevelInfo0`, confirmed
    live 2026-07-14) — so a level and its own faithful re-materialization carry DIFFERENT LevelInfo
    names and would spuriously fail post-verify without this. Returns `{}` (no rewrite) unless
    EXACTLY one LevelInfo is present: zero needs none, and 2+ is a separate error that
    `assert_at_most_one_levelinfo` surfaces — silently merging two names here would hide it."""
    names = [n for n, a in level.actors.items() if _is_levelinfo_actor(a)]
    return {names[0]: LEVELINFO_CANONICAL_NAME} if len(names) == 1 else {}


def canonical_level_hash(level: Level) -> str:
    """Stable, **order-DEPENDENT** IDENTITY hash of a level's full state (content + order).
    Actors are serialized by Name for a deterministic SERIALIZATION, then `level.order`
    is folded in — because a reorder is a real CSG state change (order is sacred), so two
    levels with identical actors but different order MUST hash differently.

    **PURE and SCHEMA-FREE — it hashes exactly `canonical_actor_t3d`, nothing folded, nothing
    expanded, no class defaults, no packages.** This is not the post-verify's comparison (that is
    `compare_view`): it is an IDENTITY of the authored bytes, and its main consumer is
    `preview_game.materialized_dx`, which names the built map
    `materialized__<level>__<hash12>.dx` and REUSES that file whenever the hash matches. Every
    equivalence folded in here would be a pair of semantically different levels collapsing onto one
    cache entry — i.e. a preview silently showing the wrong map. Being stricter than the compare
    can only cost an extra rebuild, never serve a stale one, so the hash deliberately errs strict.

    L-3 (Pi review): content and order are hashed SEPARATELY and combined, so there is no
    in-band text delimiter an actor name or T3D body could collide with."""
    content = hashlib.sha256(
        "\n".join(canonical_actor_t3d(a) for _, a in sorted(level.actors.items())).encode("utf-8")
    ).hexdigest()
    order = hashlib.sha256("\n".join(level.order).encode("utf-8")).hexdigest()
    return hashlib.sha256(f"{content}:{order}".encode("utf-8")).hexdigest()


def _to_f32(d) -> Decimal:
    """A coordinate quantized to IEEE single precision — the precision UnrealEd stores ALL
    geometry at. A brush vertex/Origin authored at full decimal precision (e.g. a rotated
    slab's `43.552099`) is stored by the editor as `float32` and re-exports as `43.552097`, so a
    level and its own faithful re-materialization would differ by ~1e-6 per coord and fail
    post-verify (confirmed live 2026-07-14). Quantizing BOTH sides to float32 here makes the
    comparison exact at the only precision the round-trip can preserve — it never changes an
    integer/grid coord (`float32(64.0) == 64.0`). Called only via `_geometry_text` from the compare
    path (`compare_view`, which the post-verify reads) on a throwaway copy — never on the durable
    trunk, the editor import, the identity hash, or generator output. (A float PROPERTY is
    quantized the same way, by `typedprops.typed_value`.)"""
    f = struct.unpack("f", struct.pack("f", float(d)))[0]
    return Decimal(repr(f))


def _f32_vec(v):
    return None if v is None else tuple(_to_f32(c) for c in v)



@dataclass
class CompareView:
    """A level reduced to the form the H3 post-verify compares: `{canonical actor name ->
    typedprops.ActorValues}` plus the canonicalized actor order. Two views are equal iff the built
    map and the intended level would IMPORT TO THE SAME OBJECTS — every property's effective TYPED
    value agrees, and so does the geometry.

    Deliberately NOT `frozen=True`: its fields are a mutable dict and list, so a generated `__hash__`
    would be a trap that only fires when someone eventually hashes one. Equality is all that is
    needed."""
    actors: dict[str, ActorValues]
    order: list[str]


def compare_view(level: Level, *, defaults, ignore: frozenset[tuple[str, str]] = frozenset()
                 ) -> CompareView:
    """The ONE compare view the post-verify uses — equality check and diagnostic diff both read
    THIS (no hand-mirrored second copy that can drift out of step with it).

    Each actor becomes a TYPED EFFECTIVE-VALUE view (`_actor_values`): for every property, the
    stored value if the actor states one, else the class default, decoded by the property's
    DECLARED TYPE. That dissolves the whole class of spelling differences the editor's
    default-diffing export creates — `StayOpenTime=4.0` against a default rendered `4`, an explicit
    `LightRadius=0` against an omitted line, `(Pitch=0,Yaw=16384,Roll=0)` against `(Yaw=16384)` —
    rather than tolerating them with a text-canonicalization pass. The caller's `Level` is never
    touched (only the brush is deep-copied, to float32-quantize the geometry text).

    Two further reductions, both of them things the editor itself does:

    * the singleton LevelInfo's engine-managed actor Name is rewritten to a fixed sentinel
      (`_levelinfo_rename`) — the editor renames it on every re-import;
    * geometry is float32-quantized and the editor-recomputed poly `Normal` dropped
      (`_geometry_text`).

    `defaults` is a `classdefaults.ClassDefaults` (anything with `.for_class(fqcn) -> ClassInfo`).
    It is REQUIRED and has NO fallback: fabricating "the default is zero" for a class we cannot
    resolve is the exact bug this view exists to catch, and it would re-introduce it on the one path
    whose job is to detect wrongness. An unresolvable class raises `SchemaError` naming the ACTOR as
    well as the class, for the caller to surface as a clean exit 2.

    A canonical-name COLLISION (only reachable when a non-LevelInfo actor is literally named
    `LevelInfo`, which the rename then aliases onto) raises rather than letting one body overwrite
    the other in the dict — a silently dropped body would make the verify blind to every change in
    that actor and pass a wrong map."""
    from .uprops import SchemaError
    rename = _levelinfo_rename(level)
    actors: dict[str, ActorValues] = {}
    for n, a in sorted(level.actors.items(), key=lambda kv: kv[0]):
        name = rename.get(n, n)
        try:
            info = defaults.for_class(a.cls)
        except SchemaError as e:
            raise SchemaError(f"cannot verify actor {name!r} — {e}") from None
        if name in actors:
            raise ValueError(
                f"cannot verify: two actors both canonicalize to the name {name!r} — rename the "
                f"non-LevelInfo one (the engine's LevelInfo singleton owns that name in the "
                f"compare)")
        actors[name] = _actor_values(a, info, ignore)
    return CompareView(actors=actors, order=[rename.get(n, n) for n in level.order])


def _stated_axes(a: Actor) -> str:
    """WHICH `Location` AXES THE SOURCE STATED — `"XYZ"` unless it omitted some.

    `Actor.location_text` is the verbatim `Location=` text as parsed, and is SELF-INVALIDATING: it
    is trusted only while it still parses back to the current `location` triple. Any mutation moves
    the actor, the two stop agreeing, and the actor is then compared with all three axes stated —
    which is correct, because every uedcli write path emits all three (`emit.emit_actor`). When the
    source really did omit an axis (an editor export omits an axis equal to the class default
    member), knowing that is what lets the typed expansion fill the axis from the CLASS DEFAULT
    instead of from zero — the `Engine.Camera` ingest bug."""
    if a.location_text is not None:
        from .rotation import parse_fvector
        if parse_fvector(a.location_text) == tuple(a.location):
            return "".join(ax for ax in "XYZ" if f"{ax}=" in a.location_text)
    return "XYZ"


def _location_text(a: Actor) -> str:
    """The `Location=` value to compare: the stated axes only, each rendered exactly as the trunk
    emit renders it (`emit.fmt_loc` = `clean` + 6dp).

    Going through `fmt_loc` is not cosmetic. `clean` snaps a coordinate within `CLEAN_EPS` (0.001)
    of an integer onto it — editor/float round-trip NOISE — and the trunk emit already did that when
    the value was written, so the trunk holds `Y=7216.000000` where the editor's re-export holds
    `Y=7215.999512`. Both sides must pass through the same snap or every actor the editor nudged
    sub-grid fails the post-verify (measured: 49 of 5125 actors on a real retail export)."""
    from .emit import fmt_loc
    stated = _stated_axes(a)
    return "(" + ",".join(f"{ax}={fmt_loc(c)}" for ax, c in zip("XYZ", a.location)
                          if ax in stated) + ")"


def _fscale_text(fs) -> str:
    """A `transform.FScale` model field rendered with EVERY member stated, at the editor's 6dp
    (`transform.emit_fscale`'s own precision — the compare must not be finer-grained than the
    serialization both sides went through). `transform.parse_fscale` already filled the members the
    source omitted with the engine's own identity defaults, so the model value is complete — writing
    it out in full keeps the typed expansion from re-filling a member from the class default and
    overwriting what the model actually holds."""
    sx, sy, sz = (Decimal(str(c)) for c in fs.scale)
    return (f"(Scale=(X={sx:.6f},Y={sy:.6f},Z={sz:.6f}),"
            f"SheerRate={Decimal(str(fs.sheer_rate)):.6f},SheerAxis={fs.sheer_axis})")


def _geometry_text(a: Actor) -> str:
    """The actor's brush as canonical compare text ("" for a point actor), built on a THROWAWAY copy:

    * every coordinate float32-quantized (`_to_f32`) — the precision the editor stores geometry at;
    * each poly's `Normal` DROPPED. The polygon Normal is NOT authored content: the importer ignores
      it and RECOMPUTES it from the vertex winding (unrealed/t3d.md "Winding defines the face, not
      Normal"), so an authored normal and the editor's recomputed one differ STRUCTURALLY, not just
      in precision (confirmed live 2026-07-14: a roof brush authored `Normal (0.707,0.707,0)`
      re-exported as `(0.541,0.541,0.643)` — the true slope from its vertices). Winding (the
      vertices, kept) is the authoritative face direction, so dropping the derived Normal loses no
      authored information."""
    if a.brush is None:
        return ""
    b = copy.deepcopy(a.brush)
    for p in b.polys:
        p.origin = _f32_vec(p.origin)
        p.normal = None
        p.texture_u = _f32_vec(p.texture_u)
        p.texture_v = _f32_vec(p.texture_v)
        p.vertices = [_f32_vec(v) for v in p.vertices]
    # Self-ref canonicalization is applied to the geometry text as well as to each property, so the
    # compare covers exactly what the whole-actor text compare used to. A `Class'pkg.Obj'` ref inside
    # a `Begin Brush` block is not a form the exporter is known to write (poly headers carry bare
    # `Texture=Pkg.Group.Name`), so this is normally a no-op — but if one ever appeared, the UCC
    # export's on-disk package stem would differ from a live `MAP EXPORT`'s `MyLevel.` and abort
    # every build.
    return canonicalize_self_refs(emit_brush(b))


def _actor_values(a: Actor, info, ignore: frozenset[tuple[str, str]] = frozenset()) -> ActorValues:
    """One actor's TYPED EFFECTIVE VALUES (`typedprops.ActorValues`) — what the post-verify compares.

    Only the properties the actor itself states are decoded here; every other property of the class
    resolves through the shared per-class `info.typed_default(key)` on demand, so the cost is per
    STATED property rather than per class property (a Pawn has ~400). Two actors that both omit a
    property both get the same class default, so a property neither states can never be a
    difference. Three model-typed properties (`Location`, `MainScale`, `PostScale`) live outside
    `props` and are re-rendered from their typed fields.

    Three things are dropped, none of them authored content the compare should check:

    * NON-authored props — every property that is not `var()`-editable and not a special-editor
      exception (`is_authored_prop`): `Region`/`bSelected`/`SavedPos`/nav-graph/`DistanceFromPlayer`/…;
    * a per-game IGNORE prop (`(declaring class, prop)` in `ignore`) — an authored `var()` property
      the game's engine adds to a base class that the materialize editor's engine package lacks, so
      it can never round-trip (e.g. DeusEx `Engine.Actor.bOwned` under UED22). The caller warns;
    * the editor's own `Tag=<bare class name>` default-stamp, which every actor that never had an
      explicit `Tag` comes back from the editor carrying. It is dropped ONLY when the class does not
      itself default `Tag` — `TNM.Trestkon` defaults `Tag='Player'` (5 TNM classes default it), so
      `Tag=Trestkon` there is authored event-wiring content and must survive. Dropping the stamp
      makes that side fall through to the same class default the unstamped side already resolves
      to, so the two agree."""
    own: dict[tuple[str, int], object] = {}
    raw: dict[tuple[str, int], str] = {}
    spelled: dict[tuple[str, int], str] = {}
    bare = (a.cls or "").rsplit(".", 1)[-1].casefold()

    def put(key, text, field, name):
        own[key] = typed_value(text, field, info.defaults.get(key))
        raw[key] = text
        spelled[key] = name

    for k, v in a.props:
        key = prop_key(k)
        owner = info.owners.get(key[0])
        if not is_authored_prop(key[0], editable=info.editable.get(key[0])):
            continue
        if ignore and owner and (owner.casefold(), key[0]) in ignore:
            continue
        text = canonicalize_self_refs(v)
        if key == ("tag", 0) and key not in info.defaults and text.casefold() == bare:
            continue                                  # the editor's default-stamp, not content
        put(key, text, info.field(key[0]), k)
    if a.location is not None:
        put(("location", 0), _location_text(a), info.field("location"), "Location")
    for name, spell, fs in (("mainscale", "MainScale", a.main_scale),
                            ("postscale", "PostScale", a.post_scale)):
        if fs is not None:
            put((name, 0), _fscale_text(fs), info.field(name), spell)
    return ActorValues(cls=(a.cls or "").casefold(), info=info, own=own, raw=raw, spelled=spelled,
                       brush=_geometry_text(a))


def canonical_actor_t3d(a: Actor) -> str:
    """Normalized, deterministic single-actor T3D — the per-actor source blob. It is the unit BOTH
    the identity hash is built from, AND the FAITHFUL emit for the durable trunk
    (`trunk.dump_actor_body`), the editor/game
    import payload (`apply._materialize` `result`), stash, and query output.

    It therefore keeps authored geometry INTACT — full-precision coordinates and the poly `Normal`
    line — so it does NOT mutate durable/imported data. The round-trip-noise reduction that makes a
    level compare-equal to its own re-materialization (float32 quantization + dropping the
    editor-recomputed `Normal`) lives in `compare_view` (`_geometry_text`), applied to a throwaway
    copy ONLY at compare time — never here. (An earlier version folded that prep in here, which
    silently float32-rounded coords and
    stripped `Normal` from the git-tracked trunk and the import; cold review 2026-07-14 caught it.)

    Properties sorted by key; geometry emitted in declared order (winding is authored data and must
    not be reordered). The emitter drops Link, so the output is grid-exact and
    computed-prop-free. Calling this multiple times with the same input yields identical output.
    """
    b = copy.deepcopy(a)
    normalize_actor(b)
    # Props sorted by key for a deterministic serialization. Indexed keys (KeyPos(1)..) sort
    # lexically; for movers indices are 1..7 (8-key cap) so lexical == numeric. For uncapped
    # arrays (MultiSkins) a >=10 index would sort (10)<(2) — harmless: it only reorders the hash
    # serialization, never round-trip content.
    b.props = sorted(b.props, key=lambda kv: kv[0])
    return canonicalize_self_refs(emit_actor(b))

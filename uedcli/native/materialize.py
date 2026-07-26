"""Top-level native materialize orchestrator + the always-on offline self-check (§6 gate 1).

`run_materialize_native(level, out_path)` reads the built inputs, drives the (Rust) CSG/BSP
build, assembles the package, runs the self-check, and atomically swaps the artifact in.
`self_check(pkg_bytes)` is the ONLY runtime correctness gate: re-parse to EOF, resolve
refs, assert the Actors[0]=LevelInfo / Actors[1]=Brush / PlayerStart invariants.

The Rust compute lives in the `uedcli_native` extension (built via maturin).  Until the
N-1 CSG port reaches parity, `run_materialize_native` builds geometry only for the trivial
single-subtract-box case (Python, M0); a non-trivial trunk raises `NativeBuildNotReady`
naming what is missing (never a bare traceback — repo rule).
"""
from __future__ import annotations

import os
import struct
import uuid
from pathlib import Path

from . import assemble as ASM
from . import umodel as UM
from .actor_write import Prop, PT_STRUCT, struct_vector, struct_pointregion
from .codec import read_ci, deref
from .level_write import URL
from .pkg_write import parse_package
from .props import PropError, convert_actor_props
from ..movers import is_mover

# ECsgOper ordinals == the Rust `build_geometry` oper codes (1=Add..4=Deintersect).
_CSG_OPER = {"CSG_Active": 0, "CSG_Add": 1, "CSG_Subtract": 2,
             "CSG_Intersect": 3, "CSG_Deintersect": 4}
_IDENTITY_ROT = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _f32(x: float) -> float:
    """Round to float32 — the editor's `FCoords` scale arithmetic is single-precision, so the
    covariant normal map's per-axis reciprocals must be built at f32 to match it (§92 §43)."""
    return struct.unpack("f", struct.pack("f", float(x)))[0]


def _pointxform_f32(actor):
    """The editor's `FModelCoords.PointXform` linear map, built in UnrealEd's f32 `FCoords` op-order
    `((UnitCoords·PostScale)·Rotation)·MainScale` (`ABrush::BuildCoords`, Engine.dll 0x111390; §92 §45),
    NOT `rotation.actor_linear`'s Python-DOUBLE matmul.

    Both compute the SAME map `L = diag(PostScale)·R·diag(MainScale)`; the difference is WHERE f32
    rounding lands.  The effective element is `M[i][k] = f32( f32(PostScale_i · R[i][k]) · MainScale_k )`:
    PostScale scales row `i`, `R` is the GMath rotation matrix, MainScale scales column `k`.  Two things
    the double matmul gets wrong (§92 §45 review):
      * **The dominant lever for DX content (the ONE that moves the bit): the scale INPUTS are f32-cast
        before the multiply.**  The editor stores `FVector Scale` as float32, so it multiplies by
        `f32(0.249997)` where `rotation.actor_linear` multiplies by the raw double `0.249997`.  On the
        cardinal cross-term `R[0][1] = -sin(180°) = 8.742278e-08` (§42), `f32(f32(PS)·R)` = `0x32bbbc9b`
        vs the double's `0x32bbbc9a` — 1 ULP, which a ~2000uu vertex amplifies into the node-`w` twin
        (UNATCO Brush541/Brush348).  EVERY DX rot+scale brush has MainScale=identity, so this input cast
        is the whole effect there.
      * **The intermediate f32 round after `PostScale·Rotation`, before `MainScale`** — a genuine
        SECOND rounding that bites ONLY when both PostScale and MainScale are non-unit on the SAME
        crossed off-axis (`f32(f32(PS·R)·MS)` ≠ `f32(PS·R·MS)`).  No DX brush exercises it (all have
        MS=identity), but reproducing it keeps the general case editor-faithful.
    `FCoords::operator*(FScale)` multiplies each axis per-column by Scale (0x18180);
    `FCoords::operator*(FCoords)` composes via `TransformVectorBy` (0x2dd50) with `M_Rotation = Rᵀ`, so
    the compose reproduces `diag(PS)·R` (a diagonal `M_A` makes each compose a single f32 multiply — the
    two zero terms add exactly).

    Non-sheared only (every DX MainScale/PostScale has SheerRate=0; the caller rejects sheer for every
    scaled brush).  Returns a 3×3 list of f32 floats — the `rot` matrix the Rust `FPoly::transform`
    applies as `world = L·(v−PrePivot)+Loc`."""
    from .. import rotation as ROT
    Rm = ROT.actor_matrix(actor)                         # GMath rotation 3×3 (None == identity)
    R = _IDENTITY_ROT if Rm is None else [[_f32(float(x)) for x in row] for row in Rm]
    PS = [_f32(float(c)) for c in ROT.actor_post_scale(actor).scale]
    MS = [_f32(float(c)) for c in ROT.actor_main_scale(actor).scale]
    return [[_f32(_f32(PS[i] * R[i][k]) * MS[k]) for k in range(3)] for i in range(3)]


def _in_world_csg(actor, index) -> bool:
    """Does this actor's brush get carved into the world BSP (fed to the CSG core)?

    A static `Brush` actor does; a **Mover** (`Engine.Mover` / a subclass like `DeusExMover`,
    `ElevatorMover`) does NOT.  A Mover is a DYNAMIC actor (a door, elevator, lift): UnrealEd
    keeps its brush as the Mover's OWN private Model and never CSGs it into the world — so the
    Mover is still emitted as a level actor (see `_trunk_to_actorspecs`, which is independent of
    this predicate), it is only kept OUT of the world-CSG input here.  Feeding movers into world
    CSG fills their doorways/openings solid and shatters empty-space connectivity into spurious
    zones and disconnected leaf-blobs (measured on HK/WanChai-Market: excluding the 23 movers
    takes leaf-blobs 21→2 and zones 24→5, matching the editor's own build).

    NOTE: the native `assemble` currently writes every non-default brush actor's OWN private Model
    EMPTY (`assemble.py` reserves `{shape}Polys` with `write_upolys_body([])`) — a static brush's
    geometry lives in the world BSP, so that is fine for them, but a mover excluded from world CSG
    then has its brush geometry in NEITHER the world model NOR its private Model, so a native-built
    mover is currently a geometry-less actor (no visible/collidable door yet).  That is a separate,
    pre-existing native-build gap (populating a Mover's animated private Model + BSP is unbuilt
    native-mover work), not a regression of the CSG exclusion — excluding movers is still correct
    (the alternative is a solid blob welded into the world that walls the doorway).  Tracked in
    `board/inbox.md`.

    Uses the shared substrate-generic `movers.is_mover` predicate (the same one doctor + dispatch
    use — no per-substrate class list).  Since 2026-07-25 that predicate is SCHEMA-AWARE — it walks
    the class hierarchy to `Engine.Mover` through the `classindex.ClassIndex` passed as `index` — so
    a Mover subclass whose class name does not end in "Mover" (`DeusEx.BreakableGlass`,
    `CaroneElevatorSet.CEDoor`) is now caught too; the old bare-name suffix test let those leak into
    world CSG (measured immaterial to HK zones/leaf-blobs, but wrong).  `index` must resolve the
    game's code `.u` packages, else `is_mover` raises rather than reporting every mover as static."""
    if actor.brush is None:
        return False
    if not actor.cls:                                    # classless brush ⇒ default Brush ⇒ world CSG
        return True
    return not is_mover(actor, index)


class BuildError(Exception):
    """A native-build failure carrying the offending value (surfaces as a clean exit-2)."""


class NativeBuildNotReady(BuildError):
    """The native CSG/BSP path cannot yet build this level (N-1 port incomplete)."""


# --- always-on offline self-check (§6 gate 1) ------------------------------

def _parse_level_export(pkg):
    lvl = [i for i, e in enumerate(pkg.exports) if pkg.class_of_export(i) == "Level"]
    if not lvl:
        raise BuildError("assembled package has no Engine.Level export")
    i0 = lvl[0]
    e = pkg.exports[i0]
    buf, pos, end = pkg.buf, e["soff"], e["soff"] + e["ssize"]
    _none, pos = read_ci(buf, pos)                       # UObject prop None
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    _max = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    refs = []
    for _ in range(num):
        r, pos = read_ci(buf, pos); refs.append(r)
    # skip FURL (4 fstrings + ops + 2 i32)
    for _ in range(4):
        length, pos = read_ci(buf, pos)
        pos += (-length) * 2 if length < 0 else length
    opcount, pos = read_ci(buf, pos)
    for _ in range(opcount):
        length, pos = read_ci(buf, pos)
        pos += (-length) * 2 if length < 0 else length
    pos += 8                                             # Port, Valid
    model_ref, pos = read_ci(buf, pos)
    return refs, model_ref


def self_check(pkg_bytes: bytes) -> None:
    """Re-parse the written package and assert self-consistency.  Raises BuildError
    (naming the failure) on any violation.  No editor, no external deps."""
    try:
        pkg = parse_package(pkg_bytes)                   # asserts reach-EOF
    except Exception as ex:
        raise BuildError(f"self-check: package does not re-parse to EOF: {ex}") from ex

    actor_refs, model_ref = _parse_level_export(pkg)
    if len(actor_refs) < 2:
        raise BuildError(f"self-check: ULevel.Actors has {len(actor_refs)} slots (need >=2 "
                         "for LevelInfo + Default Brush)")

    def class_of_ref(r):
        d = deref(r)
        if d is None:
            return None
        kind, idx = d
        if kind == "export":
            return pkg.class_of_export(idx)
        return pkg.name_of_ref(r)

    c0 = class_of_ref(actor_refs[0])
    if c0 != "LevelInfo":
        raise BuildError(f"self-check: Actors[0] class is {c0!r}, must be exactly LevelInfo")
    c1 = class_of_ref(actor_refs[1])
    if c1 != "Brush":
        raise BuildError(f"self-check: Actors[1] class is {c1!r}, must be a Brush")

    classes = [class_of_ref(r) for r in actor_refs]
    if not any(c == "PlayerStart" for c in classes):
        raise BuildError("self-check: no PlayerStart in the Actors array (player cannot spawn)")

    d = deref(model_ref)
    if d is None or d[0] != "export":
        raise BuildError(f"self-check: ULevel.ModelRef {model_ref} does not point to an export")
    mi = d[1]
    if pkg.class_of_export(mi) != "Model":
        raise BuildError(f"self-check: ModelRef export class is "
                         f"{pkg.class_of_export(mi)!r}, must be Model")
    me = pkg.exports[mi]
    try:
        model = UM.parse_model_body(pkg.buf, me["soff"], me["ssize"])
    except Exception as ex:
        raise BuildError(f"self-check: level Model body does not re-parse: {ex}") from ex

    # surf ref sanity: iLightMap resolves (unlit surf = -1, else indexes LightMap), iActor in
    # bounds, geometry indices ok
    nvec, npts = len(model.vectors), len(model.points)
    nsurf = len(model.surfs)
    nlm = len(model.light_map)
    nimp, nexp = len(pkg.imports), len(pkg.exports)
    for si, s in enumerate(model.surfs):
        if s.i_light_map != -1 and not (0 <= s.i_light_map < nlm):
            raise BuildError(f"self-check: surf {si} iLightMap={s.i_light_map} out of range "
                             f"[0,{nlm}) (LightMap has {nlm} records)")
        if not (-1 <= s.p_base < npts):
            raise BuildError(f"self-check: surf {si} pBase={s.p_base} out of range [0,{npts})")
        if not (-1 <= s.v_normal < nvec):
            raise BuildError(f"self-check: surf {si} vNormal={s.v_normal} out of range [0,{nvec})")
        td = deref(s.texture_ref)                        # texture is IMPORTED (or 0=none)
        if td is not None:
            kind, idx = td
            n = nimp if kind == "import" else nexp
            if not (0 <= idx < n):
                raise BuildError(f"self-check: surf {si} texture_ref {s.texture_ref} does not "
                                 f"resolve to a valid {kind}")
    for ni, n in enumerate(model.nodes):
        if n.i_surf != -1 and not (0 <= n.i_surf < nsurf):
            raise BuildError(f"self-check: node {ni} iSurf={n.i_surf} out of range [0,{nsurf})")
        if n.i_vert_pool + n.num_vertices > len(model.verts):
            raise BuildError(f"self-check: node {ni} vertex pool overruns Verts")

    # lightmap sanity (N-4): each record's data span + light run resolve; light refs are exports.
    nbits, nlights = len(model.light_bits), len(model.lights)
    for ri, rec in enumerate(model.light_map):
        if rec.i_light_actors == -1:
            continue                                     # dark record: no bits, no run
        if not (0 <= rec.data_offset <= nbits):
            raise BuildError(f"self-check: LightMap[{ri}] DataOffset={rec.data_offset} out of "
                             f"range [0,{nbits}]")
        if not (0 <= rec.i_light_actors < nlights):
            raise BuildError(f"self-check: LightMap[{ri}] iLightActors={rec.i_light_actors} out "
                             f"of range [0,{nlights})")
        row_bytes = (rec.u_size + 7) // 8
        # count lights in this run (up to the NULL/0 terminator) and check the byte span fits.
        n = 0
        j = rec.i_light_actors
        while j < nlights and model.lights[j] != 0:
            n += 1
            j += 1
        if rec.data_offset + n * row_bytes * rec.v_size > nbits:
            raise BuildError(f"self-check: LightMap[{ri}] bit-plane span "
                             f"({n}x{row_bytes}x{rec.v_size}) overruns LightBits ({nbits})")
    for li, ref in enumerate(model.lights):
        d = deref(ref)                                   # 0 = NULL terminator; else an export
        if d is not None and (d[0] != "export" or not (0 <= d[1] < nexp)):
            raise BuildError(f"self-check: lights[{li}] ref {ref} does not resolve to an export")


# --- M0: a trivial carved-room level Model (single subtracted box) ----------

def carved_box_model(size: float = 512.0, height: float = 256.0) -> UM.Model:
    """Build the world BSP arrays for a single subtracted box directly in Python (M0
    stand-in for the Rust CSG build).  Six inward-facing walls; one leaf; single zone.

    This is NOT a genuine BSP partition — it is a structurally-consistent Model that
    passes the offline self-check and re-parses cleanly (the M0 gate).  A real partition
    is the N-1 CSG port's job."""
    hx = hy = size / 2.0
    hz = height / 2.0
    # 8 cube corners
    pts = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
           (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    # face definitions: (inward normal, a base point index, 4 corner indices CCW)
    faces = [
        ((0, 0, 1), 0, [0, 1, 2, 3]),      # floor, normal up
        ((0, 0, -1), 4, [7, 6, 5, 4]),     # ceiling
        ((1, 0, 0), 0, [0, 3, 7, 4]),      # -X wall, normal +X (inward)
        ((-1, 0, 0), 1, [2, 1, 5, 6]),     # +X wall
        ((0, 1, 0), 0, [1, 0, 4, 5]),      # -Y wall
        ((0, -1, 0), 3, [3, 2, 6, 7]),     # +Y wall
    ]
    vectors = []          # normals + texture axes (deduped trivially: one per face)
    surfs = []
    nodes = []
    verts = []
    for fi, (normal, base_pt, corners) in enumerate(faces):
        n_idx = len(vectors); vectors.append(normal)
        u_idx = len(vectors); vectors.append((1.0, 0.0, 0.0))
        v_idx = len(vectors); vectors.append((0.0, 1.0, 0.0))
        surfs.append(UM.BspSurf(texture_ref=0, poly_flags=0, p_base=base_pt,
                                v_normal=n_idx, v_texture_u=u_idx, v_texture_v=v_idx,
                                i_actor=0, i_brush_poly=fi, i_zone=(0, 0), i_light_map=-1))
        vp = len(verts)
        for c in corners:
            verts.append(UM.BspVert(i_vertex=c, i_side=-1))
        w = normal[0] * pts[base_pt][0] + normal[1] * pts[base_pt][1] + normal[2] * pts[base_pt][2]
        nodes.append(UM.BspNode(plane=(float(normal[0]), float(normal[1]), float(normal[2]),
                                       float(w)), i_surf=fi, i_vert_pool=vp,
                                num_vertices=len(corners), i_zone=(0, 0),
                                i_front=-1, i_back=-1))
    return UM.Model(vectors=vectors, points=[tuple(map(float, p)) for p in pts],
                    nodes=nodes, surfs=surfs, verts=verts, num_shared_sides=0,
                    zones=[], field_0x54=0, leaves=[UM.BspLeaf(i_zone=0)],
                    bbox_min=(-hx, -hy, -hz), bbox_max=(hx, hy, hz))


def build_carved_box_package(*, version: int = 68, size: float = 512.0,
                             height: float = 256.0) -> bytes:
    """M0: assemble a complete, self-check-passing `.dx` for a single carved room with a
    PlayerStart at the centre."""
    model = carved_box_model(size, height)
    ps = ASM.ActorSpec(
        name="PlayerStart0", qualified_class="Engine.PlayerStart",
        props=[Prop("Location", PT_STRUCT, struct_vector(0.0, 0.0, -height / 2.0 + 40.0),
                    struct_name="Vector")],
        is_player_start=True)
    pkg = ASM.assemble_level(level_model=model, actors=[ps], brush_shapes=[],
                             version=version)
    self_check(pkg)
    return pkg


# --- full orchestrator (trunk -> package) ----------------------------------

def _atomic_write(out_path: Path, data: bytes) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.parent / f".{uuid.uuid4().hex}.uedcli-native.tmp"
    try:
        tmp.write_bytes(data)
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)


def default_schema_lookup(level=None):
    """A cached `fqcn -> {casefold(name): uprops.Prop}` schema lookup over the resolved project's
    real game `.u` files (the same seam `dispatch._class_schema` uses).  A bare (unqualified)
    class or an unresolvable package yields an EMPTY schema (every prop then skips with a warning)
    rather than a hard failure — a level still materializes, just with un-typed props dropped."""
    import os
    from .. import config, packages, uprops
    cache: dict[str, dict] = {}

    def lookup(fqcn: str) -> dict:
        if "." not in fqcn:
            return {}
        if fqcn not in cache:
            try:
                project = config.resolve_project(
                    env_project=os.environ.get("UEDCLI_PROJECT"), cwd=os.getcwd())
                user_config = config.load_user_config()
                resolver = packages.schema_resolver(project, user_config)
                props = uprops.resolve_class_properties(fqcn, resolver=resolver)
                cache[fqcn] = {p.name.casefold(): p for p in props}
            except Exception:                            # unresolvable schema -> empty (skip props)
                cache[fqcn] = {}
        return cache[fqcn]
    return lookup


# Engine pseudo-classes that are NOT normal UClass exports in any `.u` (so the class->package scan
# never finds them) yet are genuinely defined by `Engine` — falling back to `Engine.<X>` is correct
# and must not warn.  `Level`/`LevelInfo` are the ones a trunk can name.
_ENGINE_PSEUDO_CLASSES = {"level", "levelinfo"}


def default_class_packages():
    """The `classname.casefold() -> defining-package-stem` index over the resolved project's real
    game `.u` code packages (the SAME composed search path `default_schema_lookup` uses), so a bare
    actor class resolves to its true owning package (`DeusExMover` -> `DeusEx`) instead of defaulting
    to `Engine` (spike section 88).  Returns `{}` when no project/game is resolvable (tests /
    harness with no config) — then every class falls back to `Engine`, the pre-fix behaviour."""
    import os
    from .. import config, packages
    from .pkgref import build_class_package_index
    try:
        project = config.resolve_project(
            env_project=os.environ.get("UEDCLI_PROJECT"), cwd=os.getcwd())
        user_config = config.load_user_config()
    except Exception:
        return {}                       # no resolvable project/user config (tests/harness) -> no oracle
    # NB: the scan itself is deliberately NOT swallowed — a genuine failure here (vs. the legitimate
    # "no game configured" empty case) must not silently degrade every class back to `Engine.<X>`.
    # `schema_search_dirs` is `[]` when no game is selected (→ empty index, the pre-fix behaviour);
    # `build_class_package_index` already tolerates an individual bad/locked `.u` per-file.
    dirs = packages.schema_search_dirs(project, user_config)
    return build_class_package_index(dirs)


def run_materialize_native(*, level, out_path: str, class_index, overwrite: bool = False,
                           version: int = 68, schema_lookup=None, class_packages=None,
                           no_light: bool = False, no_paths: bool = True,
                           pkg_dirs=None, core: str = "bspcsg") -> list[str]:
    """Materialize a trunk `level` into `out_path` natively (no editor).  Returns the list of
    non-fatal warnings (skipped props, etc.).  Raises BuildError / NativeBuildNotReady (naming the
    cause) on any failure; the caller maps that to a clean exit-2 message.

    `class_index` is a `classindex.ClassIndex` over the game's `.u` packages — REQUIRED, because
    movers are excluded from world CSG and mover-ness is decided against the real class hierarchy
    (`movers.is_mover`).  An index that cannot resolve `Engine.Mover` raises rather than silently
    carving every mover into the world.

    `no_light` (default False = LIT) runs the native `LIGHT APPLY` lightmap bake (N-4, spike
    section 20).  Lit maps render CLEAN in the DeusEx software renderer as of 2026-07-16: the
    per-frame `Render.dll FLightManager::SetupForSurf` access violation that used to block lit
    output was a `FBspSurf` on-disk **field-order** bug — `iLightMap` and `iActor` were serial-
    swapped, so the game read `iLightMap` from the (large) brush-actor ref → out-of-range
    `Model.LightMap` → bad `Model.Lights[]` pointer → the AV.  Fixed in `umodel._enc_surf`/
    `_parse_surf` + Rust `model_write.rs` (verified vs real maps; `+seh` re-measure = 0 AVs, was
    254).  See spike section 20 §14; the earlier "minimal-Model / FP-singularity" framing (§11–§13)
    was wrong.  Pass `no_light=True` for an explicitly UNLIT build.  `no_paths` defaults True
    (reachspec build is N-5; a minimum-viable subset — see decisions 2026-07-16 03:03)."""
    out = Path(out_path)
    if out.exists() and not overwrite:
        raise BuildError(f"refusing to overwrite existing file: {out_path} "
                         "(pass --overwrite to rebuild in place)")
    if schema_lookup is None:
        schema_lookup = default_schema_lookup(level)
    if class_packages is None:
        class_packages = default_class_packages()

    actors, brush_actors, warnings = _trunk_to_actorspecs(level, schema_lookup)
    if not any(a.is_player_start for a in actors + brush_actors):
        raise BuildError("level has no PlayerStart — the game cannot spawn the player")

    model, csg_brushes, light_names, zone_actors = _build_level_model(
        level, index=class_index, bake_light=not no_light, core=core)
    url = URL(map=("Index.unr" if version >= 69 else "Index.dx"))
    # Resolve each texture's real GROUP from the packages on the search path, so a poly's 2-part
    # `Package.Name` texture ref is emitted as the game-required `Package.Group.Name` import
    # (else the game raises "Can't find Texture in file").  `pkg_dirs` are the project's package
    # search dirs (overlay first); absent, textures fall back to no-group (only valid for
    # top-level textures / textureless maps).
    from .pkgref import build_texture_group_index
    texture_groups = build_texture_group_index(pkg_dirs) if pkg_dirs else {}
    # A BARE actor class not in the class->package index is imported under the default `Engine`
    # package (`Resolver._package_of_class`).  Correct for the engine's native pseudo-classes
    # (`Level`/`LevelInfo`), but for any OTHER unknown class it means the defining package is absent
    # from the search path — a misclassed import that will fail the engine linker.  Surface those
    # (minus the benign pseudo-classes) so the culprit is visible rather than a silent revert-to-boot
    # at load (spike section 88).
    if class_packages:
        for a in actors + brush_actors:
            cls = a.qualified_class
            if "." not in cls and cls.casefold() not in class_packages \
                    and cls.casefold() not in _ENGINE_PSEUDO_CLASSES:
                w = (f"class {cls!r} not found in any package on the search path — imported as "
                     f"Engine.{cls} (its defining package may be missing; the game may fail to link)")
                if w not in warnings:
                    warnings.append(w)
    try:
        pkg = ASM.assemble_level(level_model=model, actors=actors + brush_actors,
                                 brush_shapes=[], version=version, url=url,
                                 csg_brushes=csg_brushes, light_names=light_names,
                                 texture_groups=texture_groups, class_packages=class_packages,
                                 zone_actors=zone_actors)
    except ValueError as ex:
        raise BuildError(f"assembly failed: {ex}") from ex
    self_check(pkg)
    _atomic_write(out, pkg)
    return warnings


def _trunk_to_actorspecs(level, schema_lookup):
    """Convert trunk Actors to ActorSpecs, carrying TYPED FPropertyTags (N-3): each raw T3D
    `(key,value)` prop is typed via the class schema (`props.convert_actor_props`); `Location`
    is routed from the actor's typed field.  Returns `(point_actors, brush_actors, warnings)`."""
    actors, brush_actors, warnings = [], [], []
    for name, a in level.actors.items():
        cls = a.cls or "Engine.Actor"
        short = cls.split(".")[-1]
        props = []
        if a.location is not None:
            x, y, z = (float(c) for c in a.location)
            if (x, y, z) != (0.0, 0.0, 0.0):
                props.append(Prop("Location", PT_STRUCT, struct_vector(x, y, z),
                                  struct_name="Vector"))
        # Every PLACED actor in a real map carries a `Region` (PointRegion) prop; the engine
        # RECOMPUTES it on setLocation at load, so a placeholder (Zone=None, iLeaf=-1,
        # ZoneNumber=0) is correct (spike section 30 §2.2).  A synthesized light with NO Region
        # is a candidate for the lit-render `Model.Lights`/AddLight bad-pointer crash (spike
        # section 20 §12) — real lights all carry it; ours did not.
        props.append(Prop("Region", PT_STRUCT, struct_pointregion(0, -1, 0),
                          struct_name="PointRegion"))
        raw_props = a.props
        if a.brush is not None:
            # DROP the trunk's `Brush=Model'MyLevel.<shape>'` string prop for a brush actor.
            # `assemble._brush_body` re-synthesizes the brush-shape link as a LOCAL export ref
            # (ObjRef(shape)).  If we let this string through, `convert_prop` types it as an
            # ObjectProperty and resolves `MyLevel.<shape>` to a package IMPORT — inventing a
            # bogus import of a nonexistent "MyLevel" package.  That import's name collides with
            # the ULevel export (also named "MyLevel"), so the engine cannot resolve the level
            # and game-load aborts: `Failed to load 'Level None.MyLevel': Failed to find object
            # 'Level None.MyLevel'` (observed live 2026-07-15; real maps carry no such import).
            raw_props = [(k, v) for (k, v) in raw_props if k != "Brush"]
        # MainScale/PostScale are typed model fields now (spec §10), not props — re-inject them as
        # T3D strings so they still serialize into the object's FPropertyTags (a Scale struct via
        # `props.convert_prop`), exactly as when they lived in `props`.
        from ..transform import emit_fscale
        for _key, _fs in (("MainScale", a.main_scale), ("PostScale", a.post_scale)):
            if _fs is not None:
                raw_props = list(raw_props) + [(_key, emit_fscale(_fs))]
        typed, w = convert_actor_props(cls, raw_props, schema_lookup)
        props += typed
        warnings += w
        spec = ASM.ActorSpec(
            name=name, qualified_class=cls, props=props,
            is_level_info=(short == "LevelInfo"),
            is_brush=(a.brush is not None),
            is_player_start=(short == "PlayerStart"))
        (brush_actors if spec.is_brush else actors).append(spec)
    return actors, brush_actors, warnings


def _parse_vec3(raw: str | None, default=(0.0, 0.0, 0.0)) -> tuple:
    if not raw:
        return default
    from .props import _parse_struct_fields, _f
    f = _parse_struct_fields(raw)
    d = {k: (default[i] if k not in f else 0.0) for i, k in enumerate("XYZ")}
    return tuple(_f(f.get(ax, ""), d[ax]) for ax in "XYZ")


def _build_brush_input(name, actor):
    """One CSG BrushTuple for `uedcli_native.build_geometry` from a trunk brush actor.

    Applies the brush's `Rotation` FRotator as the world transform's rotation matrix `R`: the Rust
    `FPoly::transform` computes `world = Location + R·(v − PrePivot)`, so `R` is built from the URU
    Pitch/Yaw/Roll fields via `rotation.euler_to_matrix_uu` — the editor-verified UE1 convention
    (yaw = textbook Rz; pitch/roll sin-flipped; compose Rz·Ry·Rx; GMath sine table, not libm — see
    dev/docs/spikes/2026-06-19-frotator-convention.md).  A low-bit-only / absent Rotation renders
    identity (spike: GMath truncates the low 2 bits) and passes `_IDENTITY_ROT` unchanged.

    SCALE (`MainScale`/`PostScale`) — §87 §9 (`spikes/2026-07-15-native-materialize/`), the root of
    native over-solidification on real DX levels.  A scaled-up SUBTRACT brush that builds at UNIT
    size carves a tiny hole instead of the full room, so the room interior stays SOLID and the
    editor's open void reads solid in native (`shatter_probe.py` metric `[A]` — HK 74.5%, UNATCO
    15.3%).  The Rust core (`build.rs:786`) *rejects* a non-identity `scale` tuple and only applies
    the `rot` 3×3 to the brush's local polys, so we BAKE the brush's full linear map
    `L = PostScale·R·MainScale` (`rotation.actor_linear`) into `rot`: `FPoly::transform` then yields
    `world = Location + L·(v − PrePivot)`, the correct scaled world winding, and the `scale` tuple
    stays identity so the reject guard never fires (matching its own advice, "apply scale upstream").
    Result: HK `[A]` 74.5%→8.9% (surfs 2664→4723 toward the 5224 golden), UNATCO 15.3%→1.1%.

    GATED on non-identity scale: an UNSCALED brush (which is EVERY brush on the castle — 0 scaled
    brushes) takes the exact existing rotation-only path, so its build is byte-identical to baseline
    (verified: castle 485 surfs / 1156 nodes unchanged; only the package GUID differs).  For a SCALED
    brush we additionally DROP the authored per-poly normals and Origins (empty lists → the Rust
    core recomputes each from the TRANSFORMED winding): the authored local-space normal/Origin are
    PRE-scale and no longer describe the scaled face, and the core already re-derives every final
    surf `vNormal` from its winding (`build.rs` post-`bsp_merge_coplanars` plane pass + the oracle's
    `finalize`/`calc_normal`), so a winding-derived normal is exactly right and needs no
    inverse-transpose here; the surf `pBase` falls back to the poly's `verts[0]`.  A MIRRORED brush
    (`det(L) < 0`) has its per-poly ring PRE-reversed (see the `mirror` note below) so the post-`L`
    winding stays outward-CCW.  Texture axes (`TextureU`/`TextureV`) ride the SAME forward `L`
    through `FPoly::transform` — exact only for a PURE ROTATION; the editor treats them as covectors
    (`transform.bake` uses the inverse-transpose `(L⁻¹)ᵀ`), so under ANY non-identity scale (uniform
    included) forward-`L` differs.  This changes neither solidity nor surf COUNTS (the gated metrics)
    — it can shift the `Vectors`-pool dedup, i.e. a byte-PARITY / texture-appearance concern only —
    and is boarded separately (needs live editor evidence to pin the exact convention).  Scale lives
    in the typed `actor.main_scale`/`post_scale` fields (not `props`), so `raw.get("MainScale")` is
    absent and the `scale` tuple below stays identity."""
    raw = dict(actor.props)
    oper_name = raw.get("CsgOper", "CSG_Add")
    oper = _CSG_OPER.get(oper_name)
    if oper is None:
        raise BuildError(f"brush {name}: unknown CsgOper {oper_name!r}")
    try:
        poly_flags = int(raw.get("PolyFlags", "0"))
    except ValueError:
        poly_flags = 0
    from .. import rotation as ROT
    # A brush is "scaled" when either MainScale (local/pre-rotation) or PostScale (world/post-rotation)
    # is non-identity.  Only then do we bake the full linear map + drop authored normals/Origins;
    # every unscaled brush keeps the exact prior path (rotation-only), preserving byte-parity.
    scaled = not (ROT.actor_main_scale(actor).is_identity()
                  and ROT.actor_post_scale(actor).is_identity())
    mirror = False
    # Covariant pre-cancel for texture axes on SCALED brushes (§92 §34).  The Rust core transforms a
    # poly's TextureU/TextureV by the SAME forward map it applies to verts (`FPoly::transform` ->
    # `rot_only` with `rot = L`), i.e. it emits `L·texUV`.  But texture axes are COVECTORS: the editor
    # transforms them by the inverse-transpose `(L⁻¹)ᵀ` (`transform.bake`'s `NT`), so under a
    # non-identity scale forward-`L` SQUARES the scale into the axis magnitude (e.g. UNATCO Brush420
    # PostScale.x=1.4167, authored texU.x=1.4167 -> native 1.4167²=2.0069 vs the editor's
    # 1.4167/1.4167=1.0), producing extra Vectors-pool entries that never dedup (the +146 UNATCO
    # vector over-production is entirely these scaled-brush texture axes — see §92 §34).  Since Rust
    # will re-apply `L`, we PRE-CANCEL here: pass `P·texUV` with `P = L⁻¹·(L⁻¹)ᵀ = (LᵀL)⁻¹`, so that
    # `L·(P·texUV) = (L⁻¹)ᵀ·texUV` — exactly the editor's covariant axis.  GATED on `scaled`: an
    # unscaled brush (every castle brush; `tex_cov` stays None) keeps the identity path byte-for-byte.
    # SCOPE: this closes the +146 vector-COUNT over-production (the round-tripped axis dedups into the
    # editor's pool entry, well within `bsp_add_vector`'s 0.001 tol), but `L·(LᵀL)⁻¹·v` is NOT
    # bit-identical to the editor's direct `(L⁻¹)ᵀ·v` (sub-tol FP drift from the L round-trip) — full
    # axis-VALUE byte-parity is a separate concern (would need Rust to apply the covariant map directly).
    from ..transform import det3
    tex_cov = None
    vec_xform_flat: list[float] = []                     # scaled: (L⁻¹)ᵀ VectorXform for the normal
    if scaled:
        L = ROT.actor_linear(actor)                      # PostScale·R·MainScale (double; det/inverse/mirror)
        # §92 §45: build the vertex transform `R` (the editor's PointXform) in UnrealEd's f32 `FCoords`
        # op-order, NOT the double `L` above — the editor multiplies by the f32-cast `FVector Scale`
        # (and rounds per FCoords op), where the double matmul multiplies by the raw double scale; that
        # 1-ULP gap on the cardinal cross-term is the rot+scale node-`w` VERTEX twin (§92 §44/§45).  `L`
        # stays double for the covariant/mirror/det math below (tolerance-level; the normal is renormalized).
        R = _pointxform_f32(actor)
        # SHEER guard for EVERY scaled brush (mirror or not): `_pointxform_f32` (the vertex map) AND the
        # covariant `(L⁻¹)ᵀ` normal map below are built from the DIAGONAL scale only, so a non-zero
        # SheerRate would shear NEITHER the verts nor the normal — a silent mis-build.  Every DX
        # MainScale/PostScale has SheerRate=0 (transform.py), so reject cleanly (repo rule: no silent
        # wrong result).  Hoisted here to also cover the MIRROR case: pre-§45 only the non-mirror branch
        # rejected sheer (the mirror branch baked sheer into the double-`L` verts), but now BOTH branches
        # take the diagonal `_pointxform_f32` for `R`, so both must reject (§92 §45 review C3).
        if (float(ROT.actor_main_scale(actor).sheer_rate) != 0.0
                or float(ROT.actor_post_scale(actor).sheer_rate) != 0.0):
            raise BuildError(
                f"Brush {name}: sheared scale (non-zero SheerRate) is unsupported — the f32 PointXform "
                f"and covariant normal map are both built from the diagonal scale only")
        # A zero/degenerate scale axis makes L singular -> `ROT.inverse` would ZeroDivisionError and
        # reach the CLI user (repo rule: no bare traceback, name the offending value).  Reject cleanly.
        if abs(det3(L)) < 1e-12:
            raise BuildError(
                f"Brush {name}: non-invertible scale (zero or degenerate MainScale/PostScale axis, "
                f"det(L)={det3(L):.3g}) — cannot compute covariant texture axes")
        _Linv = ROT.inverse(L)
        tex_cov = ROT.matmul(_Linv, ROT.transpose(_Linv))  # (LᵀL)⁻¹ — pre-cancels Rust's forward L
        # MIRROR (odd number of negative scale axes → det(L) < 0): the linear map inverts winding
        # orientation, so the L-transformed vertex ring runs CW and `calc_normal` (CCW→outward) would
        # yield INWARD normals — a subtract would build inside-out.  The Rust core assumes Orientation
        # +1 (`bspcsg.rs:1589` "NO LOOP-1 reverse") and never re-flips, so we PRE-reverse each poly's
        # ring here (exactly as the model-side `transform.bake` does on `det3(L) < 0`) — after L the
        # winding is outward-CCW again and the recomputed normal is correct.  The OLD code rejected all
        # scaled brushes; this keeps a mirrored brush a correct build instead of a silent mis-build.
        mirror = det3(L) < 0.0
        # §92 §43: the editor computes each SCALED face's normal via `ABrush::BuildCoords`' VectorXform
        # `(L⁻¹)ᵀ` + `SafeNormalSlow` (covariant), NOT `calc_normal` over the L-warped world winding —
        # which yields `0.99999994` (1 ULP under unit) on a face made asymmetric by non-uniform scale
        # (Brush578's ±x/±y → the N=30 committed twins).  Pass `(L⁻¹)ᵀ` so the Rust core recomputes the
        # face normal the editor's way.
        #
        # `L = PostScale·R·MainScale = diag(PS)·R·diag(MS)`, so the covariant map is
        #   `(L⁻¹)ᵀ = diag(1/PS)·(R⁻¹)ᵀ·diag(1/MS) = diag(1/PS)·R·diag(1/MS)`  (R orthonormal).
        # We build it from CLEAN per-axis f32 reciprocals `1/PS`, `1/MS` (the editor's
        # `FCoords::operator/(FScale)` divides each axis by the scale — one `divss` per component) times
        # the SAME GMath `R` — NOT `ROT.transpose(ROT.inverse(L))`, whose adjugate/determinant mixes the
        # axes so `1/1.625` comes back 1 ULP off and `SafeNormalSlow` renormalizes an axis normal to
        # `0.99999994` (re-introducing the very twin).  GATED off a MIRROR (det<0): there the covariant
        # image flips orientation, so the ring-reverse + `calc_normal` path above stays (no DX
        # mirror-scaled brush exists — verified — so this is a safety gate, not an exercised branch).
        if not mirror:
            # (Sheer is already rejected above for every scaled brush.)  Build the covariant normal map
            # `(L⁻¹)ᵀ = diag(1/PS)·R·diag(1/MS)` from CLEAN per-axis f32 reciprocals.
            def _recip_diag(fs):
                s = fs.scale
                return [[(_f32(1.0 / _f32(float(s[j]))) if i == j else 0.0) for j in range(3)]
                        for i in range(3)]
            Rm = ROT.actor_matrix(actor)                 # GMath R (None == identity)
            R_only = _IDENTITY_ROT if Rm is None else [[float(x) for x in row] for row in Rm]
            _vx = ROT.matmul(_recip_diag(ROT.actor_post_scale(actor)),
                             ROT.matmul(R_only, _recip_diag(ROT.actor_main_scale(actor))))
            vec_xform_flat = [float(_vx[r][c]) for r in range(3) for c in range(3)]
    else:
        Rm = ROT.actor_matrix(actor)                     # None == renders-as-identity (low-bit fields)
        R = _IDENTITY_ROT if Rm is None else [[float(x) for x in row] for row in Rm]
    loc = tuple(float(c) for c in actor.location) if actor.location else (0.0, 0.0, 0.0)
    prepivot = _parse_vec3(raw.get("PrePivot"))
    # Scale is baked into `R` above (scaled brushes) or genuinely identity (unscaled); MainScale is a
    # typed field, never a prop, so this always resolves to identity and the Rust reject guard passes.
    scale = _parse_vec3(raw.get("MainScale"), default=(1.0, 1.0, 1.0))

    verts_flat: list[float] = []
    poly_sizes: list[int] = []
    normals_flat: list[float] = []
    # PER-POLY authored texture axes (the T3D `TextureU=`/`TextureV=` on each Polygon), in the
    # brush's LOCAL space — `FPoly::transform` rotates them into world space alongside the verts,
    # exactly as the editor's csgRebuild does.  Without them the Rust core synthesizes a default
    # in-plane basis from the normal (`default_texture_axes`); the authored axes are the
    # world/45°-aligned vectors that dedup into the editor's smaller Vectors pool (bspAddVector).
    # Emitted one 3-tuple per poly; an absent axis (None) is passed as (0,0,0), which the Rust
    # `have_u`/`have_v` check (dot > 1e-8) treats as "no authored axis" -> default basis.
    tex_u_flat: list[float] = []
    tex_v_flat: list[float] = []
    # PER-POLY PolyFlags (the T3D `Flags=` on each poly): Portal / FakeBackdrop / Translucent /
    # Masked / TwoSided / NotSolid / Semisolid vary per surface (e.g. the moat's water sheets are
    # `Portal|FakeBackdrop|Translucent|NotSolid`, the skybox is a FakeBackdrop face) — a single
    # brush-level `poly_flags` cannot represent them, and dropping them makes the skybox render as
    # a solid wall + breaks PF_Portal zone detection.  The Rust core ORs the brush-level flags onto
    # each of these (csg.rs), so we pass the per-poly value (brush-level is 0 for authored brushes).
    poly_flags_flat: list[int] = []
    # PER-POLY authored FPoly::Base (the T3D `Origin=` on each Polygon) in the brush's LOCAL space —
    # the surface's texture ORIGIN, a stored FVector that is usually NOT one of the polygon's
    # vertices.  `FPoly::transform` rotates it into world alongside the verts, then the Rust LOOP-1
    # base-snaps it onto the face plane, exactly as the editor's csgRebuild does.  `bspAddNode` stores
    # this point as the surf `pBase`, so it is load-bearing for `Points`/`pBase` byte-parity: without
    # it the Rust core defaults `base` to `verts[0]` (a CORNER), which welds pBase onto a ring vertex
    # instead of emitting the editor's distinct orphan origin point (e.g. the World shell's x=1150
    # face has Origin (0,0,210) -> snapped (1150,0,210), a point no ring vertex touches).  Passed only
    # when EVERY poly carries an Origin (mirrors the normals gate); else empty -> Rust keeps verts[0].
    origins_flat: list[float] = []
    have_all_origins = True
    have_all_normals = True
    def _axis(a):
        if a is None:
            return [0.0, 0.0, 0.0]                        # no authored axis -> Rust synthesizes default
        v = (float(a[0]), float(a[1]), float(a[2]))
        if tex_cov is not None:                           # scaled brush: covariant pre-cancel (§92 §34)
            v = ROT.matvec(tex_cov, v)
        return [float(v[0]), float(v[1]), float(v[2])]

    for poly in actor.brush.polys:
        poly_sizes.append(len(poly.vertices))
        poly_flags_flat.append(int(getattr(poly, "flags", 0) or 0) & 0xFFFFFFFF)
        # Reverse the ring for a mirrored (det<0) brush so the post-L world winding stays
        # outward-CCW (see the `mirror` note above); an unmirrored/unscaled brush keeps ring order.
        ring = list(reversed(poly.vertices)) if mirror else poly.vertices
        for v in ring:
            verts_flat += [float(v[0]), float(v[1]), float(v[2])]
        if poly.normal is not None:
            normals_flat += [float(poly.normal[0]), float(poly.normal[1]),
                             float(poly.normal[2])]
        else:
            have_all_normals = False
        origin = getattr(poly, "origin", None)
        if origin is not None:
            origins_flat += [float(origin[0]), float(origin[1]), float(origin[2])]
        else:
            have_all_origins = False
        tex_u_flat += _axis(getattr(poly, "texture_u", None))
        tex_v_flat += _axis(getattr(poly, "texture_v", None))
    if scaled or not have_all_normals:
        normals_flat = []                                # scaled: authored normal is pre-scale ->
        #                                                  Rust CalcNormal from the transformed winding
    if not have_all_origins:
        origins_flat = []                                # some poly lacks an authored Origin ->
        #                                                  Rust defaults base to verts[0]
    # §92 §45: a SCALED brush KEEPS its authored per-poly Origin (transformed by `L` in `FPoly::transform`,
    # exactly as the editor's `FPoly::Transform` maps `Base`).  Native used to drop it (base := verts[0]),
    # but the surf `pBase` the editor stores is the TRANSFORMED authored Origin, not a ring corner — and
    # because a scaled face's node normal carries tiny non-axis components (covariant map), `w = Normal·Base`
    # differs by ~1 ULP between the two base points.  Passing the authored Origin closed all 8 UNATCO N=105
    # scaled-brush vertex/`w` twins (Brush48/236/359/750).  (Unscaled brushes already keep their Origin.)
    # `tex_v_flat`, `origins_flat` and `vec_xform_flat` ride bundled in a triple (PyO3 tuple
    # FromPyObject caps at 12).  `vec_xform_flat` is 9 floats (the covariant face-normal map for a
    # scaled brush, §92 §43) or empty (unscaled -> Rust keeps the winding-normal path).
    return (verts_flat, poly_sizes, normals_flat, oper, poly_flags,
            list(loc), R, list(prepivot), list(scale), poly_flags_flat,
            tex_u_flat, (tex_v_flat, origins_flat, vec_xform_flat))


# --- light collection (N-4) ------------------------------------------------

_LIGHT_TYPE_NONE = "LT_None"
# Default LightRadius when a light actor omits it.  The correct source is the class default object
# (CDO), which the type-only schema does not carry — flagged for Andrzej (inbox: CDO-default read).
# 64 -> world radius (64+1)*25 = 1625uu, matching the classic UE1 Light default.
_DEFAULT_LIGHT_RADIUS = 64
_LIGHT_PROP_KEYS = ("LightRadius", "LightBrightness", "LightHue", "LightSaturation",
                    "LightEffect", "LightPeriod", "LightPhase")


def _light_radius(raw: dict) -> int:
    v = raw.get("LightRadius")
    if v is None:
        return _DEFAULT_LIGHT_RADIUS
    try:
        return max(0, min(255, int(float(str(v).strip()))))   # accept "48" and "48.0"
    except ValueError:
        return _DEFAULT_LIGHT_RADIUS


def _participating_lights(level):
    """Collect the actors that contribute to the static lightmap bake (spike section 20 §5:
    `LightType != LT_None`), in deterministic trunk order.  Returns `(lights, names)` where
    `lights[i] = ([x,y,z], radius_byte)` and `names[i]` is the actor name (for the assembly
    light-ref patch — the two lists share an index).

    Participation heuristic (the type-only schema does not carry class defaults — flagged): an
    actor participates when its `LightType` prop is present and not `LT_None`, or — if it omits
    `LightType` — it carries any light property or is a `*Light`-classed actor.  An explicit
    `LT_None` always excludes.  Actors with no Location are skipped (can't place a light)."""
    lights, names = [], []
    for name in level.order:
        a = level.actors.get(name)
        if a is None or a.brush is not None:
            continue
        raw = dict(a.props)
        lt = raw.get("LightType")
        if lt == _LIGHT_TYPE_NONE:
            continue
        short = (a.cls or "").split(".")[-1]
        looks_light = any(k in raw for k in _LIGHT_PROP_KEYS) or short.endswith("Light")
        if lt is None and not looks_light:
            continue
        if a.location is None:
            continue
        loc = [float(c) for c in a.location]
        lights.append((loc, _light_radius(raw)))
        names.append(name)
    return lights, names


def _build_level_model(level, *, index, bake_light: bool = True, core: str = "bspcsg"):
    """Build the world BSP via a Rust CSG core, optionally bake the surface lightmaps (N-4,
    `bake_lighting`), then bridge the built UModel body back into a Python `umodel.Model` (parse
    the Rust-serialized bytes) so assembly can patch surf texture/actor refs and the light-ref
    array.  Returns `(model, csg_brushes, light_names)` where `csg_brushes[i]` is
    `(brush_actor_name, [Polygon,...])` for the surf-ref patch (index i == the surf `iActor` the
    Rust build tags) and `light_names[i]` is the actor name of the i-th baked light (the index the
    Model's `lights` array carries until `_patch_light_refs` rewrites it to an export ref).

    `core` selects the CSG core (both emit the same UModel shape, so the downstream assemble +
    bake + zone/collision passes are unchanged):
      - `"bspcsg"` (DEFAULT) — the incremental `bspBrushCSG` core (`build_geometry_bspcsg`) that
        reproduces the editor's cleaner BSP (~485 surfs on the castle vs the coarse core's 438).
        This is the SHIPPING build: the coarse core's merge+single-rebuild LEAKS solid cells so
        the space just above interior ledges reads SOLID, over-occluding per-lumel light LOS and
        rendering those floor/ledge surfaces PURE BLACK in-game (spike section 20 §16).  The
        cleaner bspcsg BSP keeps that space empty so the bake lights them (decisions 2026-07-17).
      - `"coarse"` — the original `build_geometry` (§8.1) core, kept for the byte-identity pinning
        tests that compare `_build_level_model` against a direct `build_geometry` call.

    Falls back to the pure-Python M0 single-box path only when the extension is unavailable AND
    the trunk is a single brush (so the offline suite still exercises assembly)."""
    csg_order = [n for n in level.order if _in_world_csg(level.actors[n], index)]
    lights, light_names = _participating_lights(level) if bake_light else ([], [])
    try:
        import uedcli_native
    except ImportError:
        uedcli_native = None

    if uedcli_native is None:
        if len(csg_order) == 1:
            return carved_box_model(), None, [], {}
        raise NativeBuildNotReady(
            f"native CSG build of {len(csg_order)} brush(es) needs the uedcli_native extension "
            "(build it with `maturin develop` / `bin/test`); only a single-brush M0 stand-in "
            "runs without it")

    build_fn = {"bspcsg": uedcli_native.build_geometry_bspcsg,
                "coarse": uedcli_native.build_geometry}.get(core)
    if build_fn is None:
        raise BuildError(f"unknown CSG core {core!r} (expected 'bspcsg' or 'coarse')")
    brushes = [_build_brush_input(n, level.actors[n]) for n in csg_order]
    try:
        built = build_fn(brushes)
        if bake_light and lights:
            uedcli_native.bake_lighting(built, lights)     # mutates `built` in place (N-4)
        body = uedcli_native.serialize_model(built)
    except uedcli_native.BuildError as ex:
        raise BuildError(f"native CSG build failed: {ex}") from ex
    model = UM.parse_model_body(body, 0, len(body))
    csg_brushes = [(n, level.actors[n].brush.polys) for n in csg_order]
    zone_actors = _resolve_zone_actors(level, model)
    return model, csg_brushes, light_names, zone_actors


def _model_point_zone(model, p) -> int:
    """PointRegion descent on a built `umodel.Model`: the zone number at point `p` (0 = solid)."""
    if not model.nodes:
        return 0
    ni = 0
    while True:
        n = model.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx * p[0] + ny * p[1] + nz * p[2] - w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            lf = n.i_leaf[side]
            return model.leaves[lf].i_zone if 0 <= lf < len(model.leaves) else 0
        ni = child


def _resolve_zone_actors(level, model) -> dict:
    """Pass G (assembly-time): map zone_number -> the `ZoneInfo`/`SkyZoneInfo`/`WarpZoneInfo` actor
    whose `Location` PointRegion-resolves into that zone.  `LevelInfo` (also an AZoneInfo) is
    excluded — a default interior zone with no ZoneInfo keeps a NULL ZoneActor.  First actor wins
    per zone.  `assemble._patch_zone_refs` rewrites these names to export refs."""
    zone_actors: dict[int, str] = {}
    for name, a in level.actors.items():
        short = (a.cls or "").split(".")[-1]
        if short == "LevelInfo" or not short.endswith("ZoneInfo"):
            continue
        if a.location is None:
            continue
        loc = tuple(float(c) for c in a.location)
        z = _model_point_zone(model, loc)
        if z > 0 and z not in zone_actors:
            zone_actors[z] = name
    return zone_actors

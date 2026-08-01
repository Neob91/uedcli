"""Actor/brush generator post-processing — the cross-family generator orchestrator.

After a generator emits actors (actor build, prefab apply, the brush build shapes), two shared
post-processing steps run: `apply_generator_org` stamps `--folder`/`--label` sidecar fields, and
`apply_generator_rotate` sets the absolute `Rotation` prop and warns on newly off-grid geometry.
`offgrid_flags` and `rotation_prop_uu` are the small helpers those need; `offgrid_flags` is also used
by the brush-build swept advisory (still in dispatch). Callers use module-qualified lookup
(`generators.apply_generator_org(...)`). Imports only `errors` and lower services, never a command
family (spec "Dependency rules" 4-5).
"""
from __future__ import annotations

import sys

from .. import rotation
from .errors import CommandError


def rotation_prop_uu(rot_uu):
    """(pitch,yaw,roll) FRotator fields for a `--rotate PITCH,YAW,ROLL` triple given in **unreal
    rotation units** (16384 = 90°), rounded to the integer field and wrapped mod 65536."""
    return tuple(rotation.uu_field(c) for c in rot_uu)


def offgrid_flags(verts) -> list[bool]:
    """Per-vertex: is any component off the integer grid (> CLEAN_EPS from an integer)? World-vertex
    order is stable across a rotation (rotation moves coordinates, never reorders), so a pre- and a
    post-rotation call align element-wise for a "what did the rotation newly push off-grid?" diff."""
    return [any(abs(c - round(c)) > 1e-3 for c in w) for w in verts]


def apply_generator_org(actors, args) -> None:
    """Set the `folder`/`labels` sidecar fields on generator-emitted actors from `--folder`/`--label`
    (both validated with the same rules as `actor folder set`/`actor label add`), so `emit_actor_t3d`
    renders the `// uedcli-folder:`/`// uedcli-labels:` carriers that `actor add` reads back. Generators
    are the single place organization is authored; `actor add` no longer carries these flags. No-op for
    the flags left unset. Grammar errors surface as a CLI error naming the offending value."""
    from .. import folderlib, labellib
    folder = getattr(args, "folder", None)
    labels = getattr(args, "label", None) or []
    if folder is not None:
        try:
            folderlib.validate_folder_path(folder)
        except ValueError as e:
            raise CommandError(str(e))
    for lbl in labels:
        try:
            labellib.validate_label(lbl)
        except ValueError as e:
            raise CommandError(str(e))
    labelset = frozenset(labels)
    for actor in actors:
        if folder is not None:
            actor.folder = folder
        if labelset:
            actor.labels = actor.labels | labelset


def apply_generator_rotate(actors, rot_uu) -> None:
    """Feature 7: SET the emitted actors' Rotation field to the ABSOLUTE `rot_uu` — unreal rotation
    units, 16384 = 90° — a fresh generated actor is identity, so this is a plain set, not an add.
    Injects a `Rotation` prop (rotation is stored, NOT vertex-baked). No-op ONLY when `rot_uu` is
    None (the flag was not given): an EXPLICIT `--rotate 0,0,0` writes `(Pitch=0,Yaw=0,Roll=0)`,
    because omitting the property does not mean "unrotated" — it means "the CLASS DEFAULT", and
    `TNM.LavaSpitter` defaults `Rotation=(Pitch=16384,Yaw=0,Roll=0)`, so the omission would build it
    pitched 90° (2026-07-25; the same rule fixed in `actor rotate`). Warns (stderr) only when the
    rotation NEWLY carries a brush vertex off the integer grid (a shape whose own geometry is
    already fractional — e.g. a cylinder ring — is not blamed on `--rotate`)."""
    if rot_uu is None:
        return
    uu = rotation_prop_uu(rot_uu)
    deg_str = ",".join(str(c) for c in rot_uu)
    for actor in actors:
        # off-grid vertices BEFORE the rotation — the shape's own fractional geometry, if any
        before = offgrid_flags(rotation.world_vertices(actor)) if actor.brush is not None else []
        props = [(k, v) for k, v in actor.props if k != "Rotation"]
        idx = next((i for i, (k, _) in enumerate(props) if k == "Brush"), len(props))
        props.insert(idx, ("Rotation", f"(Pitch={uu[0]},Yaw={uu[1]},Roll={uu[2]})"))
        actor.props = props
        if actor.brush is not None:
            after = offgrid_flags(rotation.world_vertices(actor))
            if any(a and not b for b, a in zip(before, after)):   # rotation NEWLY pushed one off-grid
                print(f"warning: --rotate {deg_str} carries some of {actor.name}'s brush vertices "
                      f"off the integer grid; the editor will snap them on import/rebuild",
                      file=sys.stderr)

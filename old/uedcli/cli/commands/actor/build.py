"""`actor build` — a STATELESS generator: writes a point-actor T3D to stdout, no editor, no level.

No source is resolved (nothing is loaded or saved); `--prop` may resolve the project's class schema
through `cli.resources` when a token needs it. This module uses `cli.generators`/`cli.ingest`/
`cli.resources` and the `propedit`/`emit`/`model` services; it never imports another command family
or the router.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from ... import generators, ingest, resources
from ...errors import CommandError
from .... import propedit
from ....uprops import SchemaError


def run(args) -> int:
    """`actor build <Package.Name>` — emit one point actor as T3D. `--prop` adopts the `actor prop
    set` grammar + schema validation; `--rotate` sets Rotation absolutely; `--folder`/`--label`
    attach sidecar carriers. No level is touched."""
    from ....emit import emit_actor_t3d
    from ....model import Actor
    aclass = args.aclass
    parts = aclass.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise CommandError(f"actor build: class must be Package.Name, got: {aclass!r}")
    _pkg, cls = parts
    at = tuple(args.at) if args.at else (0.0, 0.0, 0.0)
    # --prop adopts the `actor prop set` grammar + schema validation (spec §7): tokens
    # compose onto the class-default base (a member edit materializes the default
    # explicitly); a Location token routes to the typed field, overriding --at. Grammar
    # errors surface before anything else (matching the old KEY=VALUE pre-check).
    try:
        toks = [propedit.parse_token(t, expect_value=True) for t in (args.prop or [])]
    except propedit.PropEditError as e:
        raise CommandError(f"actor build: {e}") from None
    actor = Actor(name=args.base_name or cls, cls=aclass, location=at, props=[], brush=None)
    ingest.validate_ingest_actors([actor], args)          # existence-validate the class before emit
    if toks:
        try:
            plan = propedit.plan_edit(actor, toks, "set", resources.class_ctx(aclass, args),
                                      propedit.TYPED_FIELDS)
        except propedit.PropEditError as e:
            raise CommandError(f"actor build: {e}") from None
        except SchemaError as e:
            raise CommandError(f"actor build: {e}") from None
        actor.props = plan.props
        for attr, val in plan.typed_updates.items():
            setattr(actor, attr, val)
        if actor.location is None:              # a whole `Location` unset → emit at the origin
            actor.location = (Decimal(0), Decimal(0), Decimal(0))
    # Feature 7: --rotate SETS the Rotation field absolutely (shorthand for --prop Rotation=…);
    # a point actor has no brush, so the off-grid warning never fires here.
    generators.apply_generator_rotate([actor], getattr(args, "rotate", None))
    generators.apply_generator_org([actor], args)             # --folder/--label → sidecar carriers
    sys.stdout.write(emit_actor_t3d(actor))
    return 0

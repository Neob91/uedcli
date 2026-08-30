"""`brush measure` — pure geometric measurement sub-verbs (no mutation, no verdicts)."""
import sys

from ...targets import resolve_target_names
from ...errors import CommandError
from .... import relation


def run(args, src) -> int:
    if args.measuresub == "relation":
        return _relation(args, src)
    raise CommandError(f"unimplemented brush measure sub-verb: {args.measuresub}")


def _relation(args, src) -> int:
    names = resolve_target_names(args.names)
    if not names:
        return 0
    names = list(dict.fromkeys(names))  # dedupe: naming the same brush twice would self-compare it
    if len(names) < 2:
        print("brush measure relation needs at least 2 brush names, got 1", file=sys.stderr)
        return 2
    top = None if args.top == "all" else args.top
    level = src.load()
    try:
        report = relation.compute(level, names, top=top)
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(relation.format_report(report))
    return 0

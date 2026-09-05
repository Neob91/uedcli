"""`uscript compile` — compile UnrealScript sources to a `.u` package, like UCC.

Fully offline: it wraps the native compiler (`uscript.compile.compile_package_dir` +
`uscript.serialize.serialize`), no editor and no docker. It owns the translation of every compiler
error — a parse/lex error, or an unsupported construct (`NotImplementedError`/`LowerError`) — into
the clean exit-2 `CommandError` the central guard prints, so a construct the compiler doesn't handle
yet names itself instead of tracebacking.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

from ..errors import CommandError


def run(args) -> int:
    if args.sub == "compile":
        return _compile(args)
    raise CommandError(f"unimplemented uscript sub-verb: {args.sub}")


def _compile(args) -> int:
    from ...uscript.compile import compile_conversation_siblings, compile_package_dir
    from ...uscript.env import InstallEnv
    from ...uscript.lexer import LexError
    from ...uscript.lower import LowerError
    from ...uscript.parser import ParseError
    from ...uscript.serialize import serialize

    src_dir = args.src
    if not os.path.isdir(src_dir):
        raise CommandError(f"not a directory: {src_dir}")
    paths = sorted(glob.glob(os.path.join(src_dir, "*.uc")))
    if not paths:
        raise CommandError(f"no *.uc sources in {src_dir}")
    classes: dict[str, str] = {}
    for p in paths:
        try:
            classes[os.path.basename(p)] = Path(p).read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise CommandError(f"source is not valid UTF-8 ({e.reason}): {p}") from None

    package = args.package or _package_name(src_dir)
    env = InstallEnv(_search_dirs(args.deps))

    try:
        pkg = compile_package_dir(classes, env, package_name=package)
        data = serialize(pkg)
        siblings = compile_conversation_siblings(classes, env, package_name=package,
                                                 con_files=_con_files(src_dir))
        sibling_data = {name: serialize(p) for name, p in siblings.items()}
    except (ParseError, LexError, LowerError, NotImplementedError, ValueError) as e:
        raise CommandError(f"compile failed ({package}): {e}") from None

    out_path = args.out or f"{package}.u"
    with open(out_path, "wb") as fh:
        fh.write(data)
    out_dir = os.path.dirname(out_path) or "."
    sibling_paths = []
    for name, sdata in sibling_data.items():                # emitted next to the main package
        sp = os.path.join(out_dir, f"{name}.u")
        with open(sp, "wb") as fh:
            fh.write(sdata)
        sibling_paths.append(sp)

    extra = f" + {len(sibling_paths)} conversation sibling(s)" if sibling_paths else ""
    print(f"compiled {len(classes)} class(es) → {len(data)} bytes{extra}", file=sys.stderr)
    if args.json:
        import json
        print(json.dumps({"package": package, "classes": len(classes), "bytes": len(data),
                          "path": out_path, "siblings": sibling_paths}))
    else:
        print(out_path)
        for sp in sibling_paths:
            print(sp)
    return 0


def _con_files(src_dir: str) -> dict[str, bytes]:
    """`.con` inputs a `#exec CONVERSATION IMPORT` may reference — from the sources dir and its parent
    (a package lays its `.con` beside `Classes/`), keyed by basename."""
    out: dict[str, bytes] = {}
    for d in (src_dir, os.path.dirname(os.path.abspath(src_dir))):
        for p in glob.glob(os.path.join(d, "*.con")) + glob.glob(os.path.join(d, "*.Con")):
            out.setdefault(os.path.basename(p), Path(p).read_bytes())
    return out


def _package_name(src_dir: str) -> str:
    """The package name a bare dir implies: its own basename, or its parent's when it is a `Classes`
    dir (a package is laid out `<Pkg>/Classes/*.uc`, so `Classes` is never the package)."""
    src_dir = os.path.abspath(src_dir)
    base = os.path.basename(src_dir)
    return os.path.basename(os.path.dirname(src_dir)) if base.casefold() == "classes" else base


def _search_dirs(deps: list[str]) -> list[str]:
    """Dependency `.u` search dirs, most-authoritative first. `compile_package_dir` reads core.u /
    Engine.u from the FIRST dir, so the UED22 substrate (which has them) leads when present, then the
    user's `--deps`. With no substrate the user's `--deps` are the only source (the first must hold
    core.u / Engine.u); none at all exits 2."""
    from ... import tool_assets

    dirs: list[str] = []
    ued22 = tool_assets.uned_dir() / "UED22"
    if ued22.is_dir() and any(ued22.glob("*.u")):
        dirs.append(str(ued22))
    dirs.extend(deps)
    if not dirs:
        raise CommandError("no dependency packages found: pass --deps DIR (a dir holding core.u and "
                           "Engine.u) — the UED22 substrate is not installed")
    return dirs

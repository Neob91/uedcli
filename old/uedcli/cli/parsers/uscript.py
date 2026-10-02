"""`uscript` command-family parser registrar — compile UnrealScript to a `.u` package, like UCC."""
from __future__ import annotations


def register(sub) -> None:
    uscript = sub.add_parser(
        "uscript",
        help="compile UnrealScript source into a .u code package (offline; a native compiler that "
             "matches UCC's byte output — no editor, no docker)")
    ussub = uscript.add_subparsers(dest="sub", required=True)

    comp = ussub.add_parser(
        "compile",
        help="compile every *.uc in a source dir into one .u package. Prints the written path to "
             "stdout, a human summary to stderr; a compile error exits 2 naming the class/construct.")
    comp.add_argument(
        "src", metavar="SRC-DIR",
        help="dir of *.uc sources: a package's Classes/ dir or a flat dir. All *.uc in it compile "
             "into one package.")
    comp.add_argument(
        "-o", "--out", default=None, metavar="OUT.u",
        help="output package path (relative → cwd). Default: <PkgName>.u in the cwd.")
    comp.add_argument(
        "--package", default=None, metavar="NAME",
        help="package name (heads every class's PackageImports and names the output). Default: the "
             "source dir's name, or its parent's when the dir is named Classes.")
    comp.add_argument(
        "--deps", action="append", default=[], metavar="DIR",
        help="extra .u search dir for resolving supers/types (repeat to add more). The UED22 "
             "substrate is searched by default; when it is unavailable at least one --deps dir "
             "holding core.u and Engine.u is required.")
    comp.add_argument(
        "--json", action="store_true",
        help="emit one JSON object {package, classes, bytes, path} instead of the bare path line")

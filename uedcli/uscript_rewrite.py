"""Reimplemented UnrealScript munger: turn a decompiled `.uc` into a body-free v69 "stub".

Replaces `Tools/unrclsprs/main.py`. The load-bearing invariant is **whitelist / discard the
remainder**: the parser recognizes only a fixed keep-set (class decl, `#exec`s, enums, structs,
variables, `defaultproperties`) and drops everything else — function/state/replication bodies are
never identified-and-deleted, they simply fall outside the whitelist and are never rendered. An
unrecognized future construct vanishes (fails safe), it does not leak into the stub.

Scanning is brace-depth AND string/comment aware (the prototype's `[^}]+`/`[^;]+` regexes break on
nested braces and mis-split quoted values). See
`dev/docs/specs/2026-06-21-uedcli-package-stubbing-design.md`.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path


class UScriptParseError(Exception):
    """A decompiled `.uc` could not be parsed (raised with the offending context)."""


def read_uc(path: Path | str) -> str:
    """Read a decompiled `.uc` as utf-8, falling back to `iso-8859-1` on non-utf-8 bytes (DeusEx
    source carries them). `iso-8859-1` decodes every byte, so this never raises. (The prototype's
    third `iso-8859-2` branch was unreachable dead code — dropped.)"""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("iso-8859-1")


def rename_group_prefixed_pcx(textures_dir: Path | str) -> dict[str, str]:
    """Rename umodel/UCC's group-prefixed PCX (`Skins.GEPAmmoTex1.pcx`) to the bare name
    (`GEPAmmoTex1.pcx`) that `#exec TEXTURE IMPORT FILE=Textures\\<Name>.pcx` expects. Returns the
    {old: new} map. **Fails loud on a true base-name collision** (two files mapping to the same
    bare name) rather than silently picking one. (G-C: net-new — the prototype only rewrote the
    directive, never the file. The collision policy may be relaxed by the live G-C probe.)"""
    d = Path(textures_dir)
    claimed: dict[str, str] = {}
    for f in sorted(d.glob("*.pcx")):
        parts = f.name.split(".")
        bare = f"{parts[-2]}.{parts[-1]}" if len(parts) > 2 else f.name
        if bare in claimed and claimed[bare] != f.name:
            raise UScriptParseError(
                f"PCX base-name collision: {claimed[bare]!r} and {f.name!r} both map to {bare!r}"
            )
        claimed[bare] = f.name
    renames = {src: bare for bare, src in claimed.items() if src != bare}
    for src, bare in renames.items():
        (d / src).rename(d / bare)
    return renames


# --- low-level span scanning (string/comment aware) ---------------------------------------

def _skip_string_or_comment(text: str, i: int) -> int:
    """If a string/name literal or comment begins at `i`, return the index just past it; else `i`.

    Name literals (`Texture'Pkg.Name'`) and double-quoted strings are spanned so a `{`/`}`/`;`
    inside them never moves brace depth.
    """
    n = len(text)
    c = text[i]
    if c == '"':
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == '"':
                return j + 1
            j += 1
        return n
    if c == "'":
        j = i + 1
        while j < n and text[j] != "'":
            j += 1
        return min(j + 1, n)
    if text.startswith("//", i):
        j = text.find("\n", i)
        return n if j < 0 else j
    if text.startswith("/*", i):
        j = text.find("*/", i)
        return n if j < 0 else j + 2
    return i


def _match_brace(text: str, i: int) -> int:
    """`text[i]` is `{`; return the index just past the matching `}` (string/comment aware)."""
    assert text[i] == "{"
    n = len(text)
    depth = 0
    j = i
    while j < n:
        k = _skip_string_or_comment(text, j)
        if k != j:
            j = k
            continue
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    raise UScriptParseError(f"unterminated brace block starting at offset {i}")


def _scan_to_semicolon(text: str, i: int) -> int:
    """Return the index just past the next top-level `;` (braces/strings/comments skipped)."""
    n = len(text)
    depth = 0
    j = i
    while j < n:
        k = _skip_string_or_comment(text, j)
        if k != j:
            j = k
            continue
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ";" and depth == 0:
            return j + 1
        j += 1
    raise UScriptParseError(f"unterminated statement (no `;`) starting at offset {i}")


def _skip_unknown_construct(text: str, i: int) -> int:
    """Discard a non-keep construct: skip its `{...}` body, or to its terminating `;` if none.

    `(`/`)` are tracked so a `;` or `{` inside a signature's default args isn't mistaken for the
    terminator/body. This is how function/state/replication/cpptext/operator bodies leave the stub.
    """
    n = len(text)
    paren = 0
    j = i
    while j < n:
        k = _skip_string_or_comment(text, j)
        if k != j:
            j = k
            continue
        c = text[j]
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        elif paren == 0 and c == "{":
            return _match_brace(text, j)
        elif paren == 0 and c == ";":
            return j + 1
        j += 1
    raise UScriptParseError(f"unterminated construct starting at offset {i} (no `{{`/`;` before EOF)")


def _find_brace(text: str, i: int) -> int:
    brace = text.find("{", i)
    if brace < 0:
        raise UScriptParseError(f"expected `{{` after construct at offset {i}")
    return brace


def _scan_braced_decl(text: str, i: int) -> int:
    """For an `enum`/`struct` at `i`: return the index past the `;` following its `{...}` body."""
    return _scan_to_semicolon(text, _match_brace(text, _find_brace(text, i)))


def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        k = _skip_string_or_comment(text, i)
        if k != i and (text.startswith("//", i) or text.startswith("/*", i)):
            i = k
            continue
        break
    return i


# --- parsed model -------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class Exec:
    command: str            # e.g. "MESH IMPORT" (upper-cased, whitespace-collapsed)
    props: dict[str, str]   # KEY -> value, insertion-ordered; keys upper-cased
    comment: str | None     # trailing `// ...`, verbatim, or None


@dataclass(frozen=True, kw_only=True)
class ParsedClass:
    name: str
    parent: str | None
    execs: tuple[Exec, ...]
    enums: tuple[str, ...]
    structs: tuple[str, ...]
    variables: tuple[str, ...]
    defaults: tuple[tuple[str, str], ...]


def _find_line_comment(s: str) -> int | None:
    """Index of a `//` line comment in `s`, skipping quoted spans; None if none."""
    i, n = 0, len(s)
    while i < n:
        if s[i] in "\"'":
            i = _skip_string_or_comment(s, i)
            continue
        if s.startswith("//", i):
            return i
        i += 1
    return None


_WORD = re.compile(r"\w+")


def _parse_exec(body: str) -> Exec:
    """Parse an `#exec` directive body (text after `#exec`) into command + props + comment.

    Quoted values may contain spaces (the prototype's `\\S+` regex mis-split them). Leading bare
    words are the command; a bare word after props start is a parse error.
    """
    comment = None
    ci = _find_line_comment(body)
    if ci is not None:
        comment = body[ci:].strip()
        body = body[:ci]
    body = body.strip()

    command_words: list[str] = []
    props: dict[str, str] = {}
    seen_prop = False
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        wm = _WORD.match(body, i)
        if not wm:
            raise UScriptParseError(f"unexpected token in #exec: {body[i:]!r}")
        word, i = wm.group(0), wm.end()
        if i < n and body[i] == "=":
            i += 1
            if i < n and body[i] == '"':
                j = i + 1
                while j < n and body[j] != '"':
                    j += 1
                value, i = body[i:min(j + 1, n)], min(j + 1, n)
            else:
                j = i
                while j < n and not body[j].isspace():
                    j += 1
                value, i = body[i:j], j
            key = word.upper()
            if key in props:
                raise UScriptParseError(f"duplicate #exec key {key!r}")
            props[key] = value
            seen_prop = True
        elif seen_prop:
            raise UScriptParseError(f"bare word {word!r} after #exec props")
        else:
            command_words.append(word.upper())
    return Exec(command=" ".join(command_words), props=props, comment=comment)


def _render_exec(e: Exec) -> str:
    props = " ".join(f"{k}={v}" for k, v in e.props.items())
    comment = f" {e.comment}" if e.comment else ""
    head = f"#exec {e.command}"
    return f"{head} {props}{comment}" if props else f"{head}{comment}"


def _exec_with(e: Exec, **updates: str) -> Exec:
    """Return a copy of `e` with `updates` merged into its props (existing keys keep position)."""
    props = dict(e.props)
    props.update(updates)
    return Exec(command=e.command, props=props, comment=e.comment)


def rewrite_imports(cls: ParsedClass) -> ParsedClass:
    """Point `#exec MESH IMPORT` ANIVFILE/DATAFILE at `Models\\<Mesh>_a.3d`/`_d.3d` (keyed off the
    directive's own `MESH=`, which equals umodel's object-named output), and `#exec TEXTURE IMPORT
    FILE` at `Textures\\<Name>.pcx`. The decompiled source-filename forms are discarded."""
    new_execs = []
    for e in cls.execs:
        if e.command == "MESH IMPORT" and "MESH" in e.props:
            mesh = e.props["MESH"]
            e = _exec_with(e, ANIVFILE=f"Models\\{mesh}_a.3d", DATAFILE=f"Models\\{mesh}_d.3d")
        elif e.command == "TEXTURE IMPORT" and "NAME" in e.props:
            e = _exec_with(e, FILE=f"Textures\\{e.props['NAME']}.pcx")
        new_execs.append(e)
    return dataclasses.replace(cls, execs=tuple(new_execs))


# A qualified object literal in `defaultproperties`/exec values: `Type'Package.…'`.
_QUALIFIED_REF_PREFIX = re.compile(r"(\w+)'(\w+)\.")
_QUALIFIED_REF_FULL = re.compile(r"\w+'\w+(?:\.\w+)+'")


def rehome_self_refs(cls: ParsedClass, *, package: str, temp: str) -> ParsedClass:
    """Re-home ONLY `package`'s own self-refs in `defaultproperties` (`Type'<package>.Foo'` →
    `Type'<temp>.Foo'`); leave every other package's refs untouched. (The prototype's
    `update_defaults` rewrote EVERY package's refs — that corrupts a legitimate foreign ref, which
    is why it was disabled.) **Whether re-home is the right behavior at all is provisional on the
    live G-D probe** — this builds the correctly-scoped helper; G-D decides if it's applied."""
    pkg_lower = package.lower()

    def repl(m: re.Match[str]) -> str:
        if m.group(2).lower() == pkg_lower:
            return f"{m.group(1)}'{temp}."
        return m.group(0)

    new_defaults = tuple(
        (key, _QUALIFIED_REF_PREFIX.sub(repl, value)) for key, value in cls.defaults
    )
    return dataclasses.replace(cls, defaults=new_defaults)


@dataclass(frozen=True, kw_only=True)
class CrossPackageRef:
    package: str   # the foreign package the ref points into
    ref: str       # the full literal, e.g. "Sound'AmbientSounds.Wind'"
    where: str     # context, e.g. "defaultproperties:AmbientSound" or "exec:MESHMAP SETTEXTURE"


def flag_cross_package_refs(cls: ParsedClass, *, package: str) -> list[CrossPackageRef]:
    """Detect qualified object refs into ANOTHER package (`Type'OtherPkg.…'`) in
    `defaultproperties` values and `#exec` prop values. These are the only refs that could drag in
    a dependency's dependency; per the user they are FLAGGED (not auto-resolved) and the build
    proceeds. The caller filters always-resident substrate packages."""
    pkg_lower = package.lower()
    flags: list[CrossPackageRef] = []

    def scan(value: str, where: str) -> None:
        for literal in _QUALIFIED_REF_FULL.findall(value):
            foreign = _QUALIFIED_REF_PREFIX.match(literal)
            if foreign and foreign.group(2).lower() != pkg_lower:
                flags.append(CrossPackageRef(package=foreign.group(2), ref=literal, where=where))

    for key, value in cls.defaults:
        scan(value, f"defaultproperties:{key}")
    for e in cls.execs:
        for key, prop_value in e.props.items():
            scan(prop_value, f"exec:{e.command}")
            # `#exec MESHMAP SETTEXTURE … TEXTURE=Pkg.Name` binds a mesh skin to another package's
            # texture as a BARE `Pkg.Name` (not the quoted form). File-path keys carry a `\`, so a
            # bare two-part `TEXTURE=` value is unambiguously a cross-package object ref.
            if key == "TEXTURE":
                # `Pkg.Name` OR `Pkg.Group.Name` — the package is the first dotted segment. File
                # paths (`Models\x.pcx`) carry a `\`, so a backslash-free dotted value is an object
                # ref. (Live: real DeusExItems carries `TEXTURE=Effects.Electricity.Nano_SFX_A`.)
                bare = re.fullmatch(r"(\w+)(?:\.\w+)+", prop_value)
                if bare and bare.group(1).lower() != pkg_lower:
                    flags.append(
                        CrossPackageRef(package=bare.group(1), ref=prop_value, where=f"exec:{e.command}")
                    )
    return flags


def parse_meshmap_scales(text: str) -> dict[str, Exec]:
    """Extract `#exec MESHMAP SCALE` directives from umodel's per-mesh `.uc`, keyed by the
    (lower-cased) `MESHMAP` value. Needs NO `class ... ;` decl, so it dodges G-uc — a umodel `.uc`
    that carries only `#exec` lines parses fine here where the full `parse_class` would not."""
    scales: dict[str, Exec] = {}
    for line in text.splitlines():
        stripped = line.strip()
        directive = re.match(r"#\s*exec\b", stripped, re.IGNORECASE)
        if not directive:
            continue
        rest = stripped[directive.end():]
        # Only parse MESHMAP SCALE lines — umodel's `.uc` carries other directives this tolerant
        # reader must not choke on (e.g. `#exec LODPARAMS …`).
        if not re.match(r"\s*MESHMAP\s+SCALE\b", rest, re.IGNORECASE):
            continue
        e = _parse_exec(rest)
        if "MESHMAP" in e.props:
            scales[e.props["MESHMAP"].lower()] = e
    return scales


def reconcile_meshmap_scale(cls: ParsedClass, scales: dict[str, Exec]) -> ParsedClass:
    """Replace each `#exec MESHMAP SCALE` whose `MESHMAP` umodel exported a scale for; keep the
    decompiled directive on a miss (conditional replace-in-place, never insert)."""
    new_execs = []
    for e in cls.execs:
        if e.command == "MESHMAP SCALE" and "MESHMAP" in e.props:
            replacement = scales.get(e.props["MESHMAP"].lower())
            if replacement is not None:
                e = replacement
        new_execs.append(e)
    return dataclasses.replace(cls, execs=tuple(new_execs))


_CLASS_DECL = re.compile(
    r"\bclass\s+(\w+)(?:\s+(?:extends|expands)\s+(\w+(?:\.\w+)*))?\b[^;]*;",
    re.IGNORECASE | re.DOTALL,
)
# `defaultproperties` is flat `Key=Value` (and `Key(N)=Value`) in UE1/DeusEx-v68 — line-split on
# the first `=`. UE2+ `Begin Object … End Object` subobject blocks are NOT handled (they don't
# occur in v68 input); a stray one would mis-split, so revisit if a v69-authored class is ever fed in.
_DEFAULT_PROP = re.compile(r"^\s*([^=\n]+?)\s*=(.*)$", re.MULTILINE)


def _mask_comments_and_strings(text: str) -> str:
    """Blank every comment/string/name-literal span (same length, so offsets stay aligned) so a
    top-level regex search can't match inside one. Decompiled `.uc` opens with banner comments
    that contain the word `class`."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        k = _skip_string_or_comment(text, i)
        if k != i:
            out.append(" " * (k - i))
            i = k
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def parse_class(text: str) -> ParsedClass:
    """Parse a decompiled `.uc` into its keep-set, discarding bodies (whitelist model)."""
    # Search on a comment/string-masked copy so a banner comment mentioning `class` can't match;
    # offsets are preserved, so the match indices apply to the original text.
    m = _CLASS_DECL.search(_mask_comments_and_strings(text))
    if not m:
        raise UScriptParseError("no `class ... ;` declaration found")
    name, parent = m.group(1), m.group(2)

    execs: list[Exec] = []
    enums: list[str] = []
    structs: list[str] = []
    variables: list[str] = []
    default_block: str | None = None

    n = len(text)
    i = m.end()
    while i < n:
        i = _skip_ws_and_comments(text, i)
        if i >= n:
            break
        if text[i] == "#":
            eol = text.find("\n", i)
            eol = n if eol < 0 else eol
            directive = re.match(r"#\s*exec\b", text[i:eol], re.IGNORECASE)
            if directive:
                execs.append(_parse_exec(text[i + directive.end():eol]))
            i = eol
            continue
        word_match = _WORD.match(text, i)
        keyword = word_match.group(0).lower() if word_match else ""
        if keyword == "var":
            end = _scan_to_semicolon(text, i)
            variables.append(re.sub(r"\s+", " ", text[i:end]).strip())
            i = end
        elif keyword in ("enum", "struct"):
            end = _scan_braced_decl(text, i)
            target = enums if keyword == "enum" else structs
            target.append(re.sub(r"\s+", " ", text[i:end]).strip())
            i = end
        elif keyword == "defaultproperties":
            brace = _find_brace(text, word_match.end())
            end = _match_brace(text, brace)
            default_block = text[brace + 1:end - 1]
            i = end
        else:
            i = _skip_unknown_construct(text, i)

    defaults: list[tuple[str, str]] = []
    if default_block is not None:
        for dm in _DEFAULT_PROP.finditer(default_block):
            defaults.append((dm.group(1).strip(), dm.group(2).strip()))

    return ParsedClass(
        name=name,
        parent=parent,
        execs=tuple(execs),
        enums=tuple(enums),
        structs=tuple(structs),
        variables=tuple(variables),
        defaults=tuple(defaults),
    )


def render_stub(cls: ParsedClass) -> str:
    """Re-emit only the keep-set: class decl + `#exec`s + enums + structs + variables +
    `defaultproperties`. Each group keeps source order (types before vars, so a var of an enum
    type still resolves)."""
    parent = f" extends {cls.parent}" if cls.parent else ""
    defs = "\n".join(
        [_render_exec(e) for e in cls.execs]
        + list(cls.enums)
        + list(cls.structs)
        + list(cls.variables)
    )
    defaults = "\n".join(f"    {key}={value}" for key, value in cls.defaults)
    return (
        f"class {cls.name}{parent};\n\n"
        f"{defs}\n\n"
        f"defaultproperties\n{{\n{defaults}\n}}\n"
    )

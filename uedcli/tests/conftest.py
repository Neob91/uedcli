import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------- gitignored-install pointers
# Test-only pointers into the user-supplied, gitignored Deus Ex install (moved here from the
# deleted production `repo_paths.py` — layout reorg slice 3). NOT a production discovery path
# (production is the composed config search path). `UEDCLI_TEST_INSTALL` overrides; the no-env
# fallback anchors on THIS file's location (the dev-checkout layout), so collection never fails.

def install_root() -> Path:
    env = os.environ.get("UEDCLI_TEST_INSTALL")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "uned" / "DeusExAssets"


def ued22_root() -> Path:
    """`<repo>/uned/UED22` — the one package corpus that is GIT-TRACKED, so an offline test may
    assert exact counts over it. No env pointer: a fresh checkout has it.

    ENUMERATION RULE — state it wherever a count is asserted, or the same tree gives three
    answers. Measured 2026-07-27: `git ls-files uned/UED22` = 214 files. Counting packages as
    RECURSIVE + EXTENSION-EXACT `{.u,.utx,.uax,.umx}` gives **34 packages / 1,998 `Texture`
    exports**, which is what every asserted figure in the suite uses. A loose `*.u*` glob also
    catches the tracked `DeusEx.u.bak` (35 / 2,002); top-level-only misses
    `DoNotPlaceInventorySpots/Engine.u` and `PlaceInventorySpots/Engine.u` (32 / 1,934). All
    three are defensible; only one matches the numbers.
    """
    return Path(__file__).resolve().parents[2] / "uned" / "UED22"


UED22_PACKAGE_SUFFIXES = (".u", ".utx", ".uax", ".umx")


def ued22_packages() -> list[Path]:
    """Every package under `ued22_root()`, under the enumeration rule above. Sorted, so a
    failure names the same package on every machine."""
    return sorted(p for p in ued22_root().rglob("*")
                  if p.is_file() and p.suffix.lower() in UED22_PACKAGE_SUFFIXES)


def install_system_root() -> Path:
    """The install's `System/` (v68 `.u`) — schema/closure integration-test input."""
    return install_root() / "System"


def install_content_dirs() -> list[Path]:
    """The install's content dirs (Textures/Sounds/Music) — integration-test inputs."""
    return [install_root() / d for d in ("Textures", "Sounds", "Music")]


@pytest.fixture(autouse=True)
def _isolate_uedcli_home(tmp_path, monkeypatch):
    """Point `$UEDCLI_HOME` at a per-test tmp dir so NO test can read or write the developer's real
    `~/.uedcli` — neither the config nor the derivable cache (`cache/{stubs,textures}`). A test that
    needs a specific home sets `UEDCLI_HOME` itself; its setenv/delenv runs after this fixture and
    overrides."""
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "uedcli-home"))


@pytest.fixture(autouse=True)
def _schema_cache_off(monkeypatch):
    """The offline suite runs with the persistent package-schema cache OFF by default (`dev/docs/architecture.md`
    "Package schema cache"): a stale dev-written entry must not
    poison unrelated tests while the `uprops`/`upackage` decoder is being refactored by a concurrent
    session. The dedicated cache tests (`test_schema_cache.py`) opt back IN. Also clear the module's
    in-process memo so a bundle cached by one test can never leak into another (each `uedcli` command
    is normally a fresh process, so cross-test memo persistence is a test-harness artefact)."""
    from uedcli import schema_cache
    schema_cache._DISC_MEMO.clear()
    schema_cache._PROP_MEMO.clear()
    schema_cache._SWEPT = False          # per-test reset: the auto-sweep gate is once-per-PROCESS, but
                                         # pytest is one process, so reset it so each test's writes can
                                         # (re-)trigger the automatic footprint sweep as in production.
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "off")


@pytest.fixture(autouse=True)
def _isolate_project_resolution(tmp_path_factory, monkeypatch):
    """Sever every implicit route to the developer's REAL project (a review fix): drop an inherited
    `$UEDCLI_PROJECT`, and chdir into a neutral tmp dir so cwd walk-up can never climb out of tmp
    and find the dx_lum repo's own `uedcli.toml` (a test that forgot its project fixture would
    otherwise silently read — or WRITE — the developer's checkout). The neutral dir comes from
    `tmp_path_factory`, NOT the test's own `tmp_path` — tests assert on their `tmp_path`'s exact
    contents. Tests that need a specific cwd/env set it themselves after this fixture."""
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    # Also drop an inherited $UEDCLI_LEVEL (the ambient level source since 2026-07-20): a developer
    # who runs `bin/test` with a level exported must not have it silently satisfy a verb that a test
    # expects to fail with "no level". A test that needs an ambient level sets UEDCLI_LEVEL itself
    # (via monkeypatch.setenv), after this fixture, so its value wins.
    monkeypatch.delenv("UEDCLI_LEVEL", raising=False)
    monkeypatch.chdir(tmp_path_factory.mktemp("neutral-cwd"))


@pytest.fixture(autouse=True)
def _stub_author_validation(request, monkeypatch):
    """Author-time class/texture ingest validation (`ingest.validate_ingest_actors` /
    `_validate_texture_ref`) resolves the project's games config + scans the game `.u` packages — neither present in the
    offline suite. Stub both to NO-OPs by default so pre-existing ingest/generator tests stay offline
    and green (they predate validation). A test marked `@pytest.mark.real_validation`
    (`test_ingest_validation.py`) opts OUT — it patches `ClassIndex.from_project` /
    `config.composed_search_files` to a fake substrate and exercises the REAL gate. Mirrors the
    `resources.class_schema` mockable-seam pattern."""
    if request.node.get_closest_marker("real_validation"):
        return
    from uedcli.cli import ingest
    from uedcli.cli.commands.brush import poly as brush_poly
    monkeypatch.setattr(ingest, "validate_ingest_actors", lambda actors, args: None)
    monkeypatch.setattr(brush_poly, "_validate_texture_ref", lambda ref, args: None)


@pytest.fixture
def tmp_project(tmp_path, monkeypatch) -> Path:
    """A minimal NEW-layout project rooted at a tmp dir: writes `<root>/uedcli.toml` and points
    `UEDCLI_PROJECT` at the root, so project resolution needs no cwd walk-up — the same seam
    production uses. Returns the root Path (managed dirs default to `<root>/{maps,prefabs,
    texture-catalog}`; state lands in the self-ignoring `<root>/.uedcli/`)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_PROJECT", str(root))
    return root


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="latin1")


# ------------------------------------------------------------------- brush actors, offline
# One copy, shared by `test_preview_native.py` and `test_texframe.py` — the UV-frame pins live in
# the second and the scale-reject pins in the first, and both drive the same fixture shape.

def cube_room(name="Room", size=512.0, height=256.0, texture=None):
    """A subtract cube brush actor — the stand-in room the preview/UV tests frame."""
    from uedcli.builders import cube, make_brush_actor
    return make_brush_actor(name, cube(size, size, height, texture=texture), csg="subtract")


def set_prop(actor, key: str, value: str) -> None:
    """Set one actor property from its T3D text. `MainScale`/`PostScale` are TYPED model fields
    rather than props, so they route to the field: written into `props` they would be read by
    nothing (`rotation.actor_main_scale`/`_post_scale` read the typed field)."""
    if key in ("MainScale", "PostScale"):
        from uedcli.transform import parse_fscale
        setattr(actor, "main_scale" if key == "MainScale" else "post_scale", parse_fscale(value))
        return
    actor.props = [(k, v) for k, v in actor.props if k != key] + [(key, value)]


# ------------------------------------------------------ the mover class resolver, offline
# `movers.is_mover` is SCHEMA-AWARE (dev/docs/direction/conventions.md 2026-07-25 10:18 UTC): it asks a
# `classindex.ClassIndex` whether the actor's class descends from `Engine.Mover`, so every
# mover-aware verb needs the game's `.u` packages — which the offline suite has none of.

MOVER_CLASSES = (
    "Engine.Mover",
    "DeusEx.DeusExMover",
    "DeusEx.ElevatorMover",
    "DeusEx.BreakableGlass",                     # a REAL mover whose name doesn't end in "Mover"
    "CaroneElevatorSet.CaroneElevator",          # ditto (the bug that made the gate schema-aware)
    "CaroneElevatorSet.CEDoor",                  # ditto
)


class _BareMap(dict):
    """`bare_to_fqcn()`'s return: the stub's substrate has an `Engine.<Bare>` class for every bare
    name it isn't told otherwise about, so an ordinary `Class=Brush` resolves instead of tripping
    `is_mover`'s unknown-class error. Only `.get` is overridden — that is all `is_mover` calls."""

    def __init__(self, mapping, unknown):
        super().__init__(mapping)
        self._unknown = unknown

    def get(self, key, default=None):
        if key in self:
            return self[key]
        if key.casefold() in self._unknown:
            return default
        return {f"Engine.{key}"}


class StubClassIndex:
    """Offline stand-in for `classindex.ClassIndex`, covering exactly what the mover gate asks:
    `class_exists`, `ancestry`, and `bare_to_fqcn` (bare `Class=Mover` resolution).

    The modelled substrate: every FQCN exists and roots at `Core.Object`; the ones in
    `mover_classes` sit under `Engine.Mover`; every bare name resolves to `Engine.<Bare>` unless
    it names a mover. The knobs model each way the REAL index fails to answer, all of which
    `is_mover` must turn into a raise rather than a silent `False`:

    - `resolves=False` — no class resolver at all (no games config / no packages on the path).
    - `unknown=(…)` — classes (FQCN or bare) the path does not carry.
    - `truncated=(…)` — classes whose ancestor chain stops short of `Core.Object` because a package
      on the chain is missing (what `ClassIndex.ancestry` does silently).
    - `ambiguous={bare: (fqcnA, fqcnB)}` — a cross-package bare-name collision.
    """

    def __init__(self, mover_classes=MOVER_CLASSES, *, resolves: bool = True,
                 unknown=(), truncated=(), ambiguous=None):
        self._movers = {c.casefold() for c in mover_classes}
        self._resolves = resolves
        self._unknown = {c.casefold() for c in unknown}
        self._truncated = {c.casefold() for c in truncated}
        self._ambiguous = {k.casefold(): set(v) for k, v in (ambiguous or {}).items()}

    @property
    def empty(self) -> bool:
        return not self._resolves

    def class_exists(self, fqcn: str) -> bool:
        if not self._resolves or fqcn.casefold() in self._unknown:
            return False
        return "." in fqcn

    def ancestry(self, fqcn: str) -> list[str]:
        if fqcn.casefold() in self._truncated:
            return [fqcn, "AbsentPackage.MissingBase"]        # stops short of the Core.Object root
        if fqcn.casefold() in self._movers:
            return [fqcn, "Engine.Mover", "Engine.Actor", "Core.Object"]
        return [fqcn, "Core.Object"]

    def bare_to_fqcn(self):
        out: dict[str, set[str]] = {}
        for fqcn in self._movers:
            out.setdefault(fqcn.split(".", 1)[1].casefold(), set()).add(fqcn)
        out.update(self._ambiguous)
        return _BareMap(out, self._unknown)


@pytest.fixture(autouse=True)
def _stub_mover_class_index(request, monkeypatch):
    """Hand every dispatch verb that asks "is this a Mover?" a `StubClassIndex`, so the offline
    suite keeps running without the gitignored game install. Mirrors `_stub_author_validation`:
    it stubs the ONE mockable seam (`resources.mover_index`), so the predicate itself and every
    module under it run for real. A test marked `@pytest.mark.real_mover_index` opts OUT and gets
    the genuine seam (`test_dispatch.py`'s resolver-required tests)."""
    if request.node.get_closest_marker("real_mover_index"):
        return
    from uedcli.cli import resources
    monkeypatch.setattr(resources, "mover_index",
                        lambda args, verb, project=None: StubClassIndex())


# ------------------------------------------------------------------- class info, offline
def stub_field(spec):
    """A `typedprops.Field` from a compact test spelling — the offline stand-in for a property type
    decoded out of the game's `.u`:

        "float" / "int" / "bool" / "byte" / "name" / "string" / "object"
        "enum:A,B,C"                  a ByteProperty with those ordinal-ordered value names
        "struct:X=float,Y=float"      a struct with that member layout (recursive via a Field value)
        Field(...)                    passed through unchanged
    """
    from uedcli import typedprops
    if isinstance(spec, typedprops.Field):
        return spec
    kind, _, tail = spec.partition(":")
    if kind == "enum":
        return typedprops.Field(typedprops.ENUM, enum=tuple(t.strip() for t in tail.split(",")))
    if kind == "struct":
        members = []
        for part in [t for t in tail.split(",") if t.strip()]:
            name, _, mspec = part.partition("=")
            members.append((name.strip().casefold(), stub_field(mspec.strip())))
        return typedprops.Field(typedprops.STRUCT, members=tuple(members))
    return typedprops.Field(kind)


class StubDefaults:
    """An offline stand-in for `classdefaults.ClassDefaults` — the compare path's class-info source
    (`normalize.compare_view`, `verify.verify_dx_matches`).

    The real one decodes the game's own `.u` packages, which the offline suite has no access to, and
    there is deliberately **no zero fallback** (assuming "the default is zero" is precisely the bug
    the typed compare exists to remove), so every offline compare must be handed one explicitly.

    Construct with `{fqcn: {(prop_casefold, index): default_text}}` for the DEFAULTS, and
    `schema={fqcn: {"PropName": <stub_field spec>}}` for the declared TYPES. A class not in a table
    contributes nothing: no defaults, and properties with no declared type, which the compare then
    treats as untyped text rather than inventing a zero for them. Mirroring the real
    `uprops.resolve_class_defaults`, an UNQUALIFIED class name raises `SchemaError` rather than
    silently resolving to nothing."""

    def __init__(self, table: dict[str, dict[tuple[str, int], str]] | None = None, *,
                 schema: dict[str, dict[str, object]] | None = None):
        self._table = {k.casefold(): v for k, v in (table or {}).items()}
        self._schema = {k.casefold(): {n.casefold(): stub_field(s) for n, s in v.items()}
                        for k, v in (schema or {}).items()}
        self._memo: dict[str, object] = {}
        self.resolutions = 0

    def for_class(self, fqcn: str):
        from uedcli.classdefaults import ClassInfo
        from uedcli.uprops import SchemaError
        if "." not in (fqcn or ""):
            raise SchemaError(f"class must be fully qualified (Package.Class): {fqcn!r}")
        key = fqcn.casefold()
        hit = self._memo.get(key)
        if hit is None:
            hit = self._memo[key] = ClassInfo(fqcn, dict(self._schema.get(key, {})),
                                              dict(self._table.get(key, {})))
            self.resolutions += 1
        return hit

"""Recover the package qualifier MAP EXPORT/UCC batchexport always strips from `Texture=`
(spikes/2026-06-19-t3d-package-qualification.md) by reading `OBJ DEPENDENCIES PACKAGE=MyLevel`
off a live editor that has the matching level loaded
(spikes/2026-06-19-read-surface-texture-package.md). `qualify_live_level` is the reusable seam:
it reads the qualifier off an editor that already has the matching level loaded (the caller drives
the load). `model.Polygon.texture` already stores whatever string is given (no new field) —
`parse_texture_ref`/`emit.py` (surface-flags-texturing spec) already treat a qualified ref as just
a longer string."""
from __future__ import annotations

import re
import time

from .model import Level

_LINE = re.compile(r"(?:Log:\s*)?\s*(Class|Texture)\s+(\S+)")


def parse_obj_dependencies(dump: str) -> list[list[str]]:
    """One ordered texture-ref list per `Class Engine.Polys` block (one block per brush,
    poly-order within a block — spikes/2026-06-19-read-surface-texture-package.md). Lines
    outside a block, and `Class` lines for any other type, are ignored."""
    blocks: list[list[str]] = []
    in_polys_block = False
    for line in dump.splitlines():
        m = _LINE.match(line)
        if m is None:
            continue
        kind, token = m.groups()
        if kind == "Class":
            in_polys_block = (token == "Engine.Polys")
            if in_polys_block:
                blocks.append([])
            continue
        if in_polys_block:        # kind == "Texture"
            blocks[-1].append(token)
    return blocks


_CLASS_LINE = re.compile(r"(?:Log:\s*)?\s*Class\s+(\S+\.\S+)(?:\s|$)")


def parse_loaded_classes(dump: str) -> dict[str, set[str]]:
    """Group an `OBJ LIST CLASS=Class` dump's qualified class names by their bare (post-`.`)
    name. A bare actor `Class=` with exactly one entry under its name in the returned map is
    unambiguous; 2+ is a genuine package-name collision (see `qualify_level_classes`)."""
    result: dict[str, set[str]] = {}
    for line in dump.splitlines():
        m = _CLASS_LINE.match(line)
        if m is None:
            continue
        qualified = m.group(1)
        bare = qualified.rsplit(".", 1)[-1]
        result.setdefault(bare, set()).add(qualified)
    return result


def _strip_group(ref: str) -> str:
    """Collapse `Package.Group.Name` (or deeper) to `Package.Name`. The group is NEVER required
    to resolve an object — confirmed live (unrealed/quirks.md "T3D format" / unrealed/t3d.md): a 2-part ref binds
    the same object as the 3-part form, even when the object genuinely has a group. uedctl
    convention: NEVER store a group in a qualified texture name, including refs read back from
    the editor's own `OBJ DEPENDENCIES` output."""
    parts = ref.split(".")
    return ref if len(parts) <= 2 else f"{parts[0]}.{parts[-1]}"


def _bare(ref: str) -> str:
    """The object's own name — the segment after the last `.` — of a texture ref, dropping any
    package/group qualifier (`LUM_CoreTex.Tile.grey_stone_tile` → `grey_stone_tile`; a bare
    `grey_stone_tile` → itself). This is the ONE part of a ref that is invariant between an
    authored `Texture=` (which may be bare, `Package.Name`, or `Package.Group.Name`) and the
    editor's fully-qualified `OBJ DEPENDENCIES` echo — so it is what a brush's authored polys and
    its dump block are correlated by."""
    return ref.split(".")[-1]


def qualify_level_textures(level: Level, blocks: list[list[str]]) -> None:
    """Patch each textured brush's polys with the package-qualified ref OBJ DEPENDENCIES reports
    (group stripped — `_strip_group`), by matching each brush to its OWN dump block ON CONTENT.

    Why content, not position: the dump's `Engine.Polys` walk isn't limited to OUR authored
    brushes — the level's own world BSP `Model` emits one too, an AGGREGATE of every brush's
    surviving surfaces (non-empty once ANY brush is textured; an older 2026-06-20 build saw it
    empty). That aggregate block's position among the non-empty blocks is NOT stable: live-probed
    2026-07-14 (`spikes/2026-07-13-semisolid-save/probe_tree.py`, `probe_aggregate.py`) it landed
    LAST for a 2-brush level (`[6,0,6,0,12,0,0]`), FIRST for the 95-brush castle (a 853-texture
    block zipped onto the first brush → a loud 6-vs-853 raise), and in the MIDDLE for a
    World-shell + cubes level (`[6,6,18,6]`, the 18 at index 2). So neither "drop the first
    block" nor "drop the last" is safe. A brush is instead bound to the FIRST not-yet-claimed
    non-empty block whose ordered per-poly object-names (`_bare`) exactly equal the brush's own
    textured polys' object-names; the world aggregate (and any other non-brush block) is simply
    left unclaimed and dropped. Content matching makes the correlation robust to the aggregate
    floating anywhere in the walk — the bug this rewrite fixed.

    LOAD-BEARING LIMIT — content matching disambiguates by object-NAME, not package, so it CANNOT
    tell apart two brushes (or two polys of one brush) that carry the SAME object-name from
    DIFFERENT packages (`PkgA.Wall` vs `PkgB.Wall` — a real UE1 collision; the tests use
    `Area51Wall_A`, which lives in both `CoreTexMetal` and `Area51Textures`). Both blocks satisfy
    `block_bares[i] == want`, and the tie is then broken by BLOCK ORDER (first-not-yet-claimed).
    That is correct ONLY because the dump's block order equals the authored/`MAP EXPORT` brush
    order and each block's poly order equals the authored poly order
    (`spikes/2026-06-19-read-surface-texture-package.md`) — the empty-block filter and
    aggregate-drop both preserve relative order, so first-unclaimed reproduces the authored
    pairing. If two real brush blocks (or two same-name polys) ever reordered relative to each
    other, same-name/different-package refs would swap SILENTLY: this is a package-name swap only,
    the object-names still match, so the loud `hit is None` raise below does NOT fire, and the
    materialize H3 post-verify re-qualifies BOTH sides with this same function and so cannot catch
    a deterministic mis-bind either. This has never been observed (block order is stable per the
    2026-06-19 spike), but it is the one place correctness rests on order, not content — do not
    "optimize" the empty/aggregate filtering in a way that reorders surviving brush blocks.

    A poly with a null `Texture` is not a graph reference, so OBJ DEPENDENCIES never lines it
    (dev/docs/spikes/2026-06-20-obj-dependencies-untextured-poly-correlation.md, D-Q2) — only a
    brush's non-None polys are matched, in their declared order. Raises LOUDLY if any brush finds
    no matching block (a DETECTABLE drift: a changed object-name, missing/misnamed texture, or a
    poly-count change) — worth surfacing rather than papering over. Mutates `level` in place."""
    brush_names = [n for n in level.order
                   if level.actors[n].brush is not None
                   and any(p.texture is not None for p in level.actors[n].brush.polys)]
    non_empty_blocks = [b for b in blocks if b]
    block_bares = [[_bare(r) for r in b] for b in non_empty_blocks]
    claimed: set[int] = set()
    for name in brush_names:
        polys = [p for p in level.actors[name].brush.polys if p.texture is not None]
        want = [_bare(p.texture) for p in polys]
        hit = next((i for i in range(len(non_empty_blocks))
                    if i not in claimed and block_bares[i] == want), None)
        if hit is None:
            raise ValueError(
                f"qualify_level_textures: no OBJ DEPENDENCIES Engine.Polys block matches brush "
                f"{name!r}'s {len(want)} textured polys {want} — "
                f"{len(non_empty_blocks) - len(claimed)} of {len(non_empty_blocks)} non-empty "
                f"blocks still unclaimed (dump poly-order drift or a missing/misnamed texture?)")
        claimed.add(hit)
        for poly, ref in zip(polys, non_empty_blocks[hit]):
            poly.texture = _strip_group(ref)


def qualify_level_classes(level: Level, loaded_classes: dict[str, set[str]]) -> None:
    """Patch every still-bare `Actor.cls` in `level.order` to its fully-qualified
    `Package.ClassName` form using `loaded_classes` (the parsed `OBJ LIST CLASS=Class` dump).
    Exactly one loaded candidate for a bare name is unambiguous and gets qualified; zero or 2+
    candidates raise rather than guess (dev/docs/spikes/
    2026-06-21-class-qualification-discovery-and-roundtrip.md Test 2: there is no reliable
    read-back that attributes a SPECIFIC actor instance to which colliding package's class it
    bound to, so a genuine collision cannot be safely auto-qualified). An already-qualified
    `cls` (contains '.') is left untouched — covers a second qualify pass and any future
    creation-time-qualified actor."""
    for name in level.order:
        actor = level.actors[name]
        if "." in actor.cls:
            continue
        candidates = loaded_classes.get(actor.cls, set())
        if len(candidates) == 0:
            raise ValueError(f"qualify_level_classes: actor {name!r}'s class {actor.cls!r} "
                              f"is not loaded under any package")
        if len(candidates) > 1:
            raise ValueError(f"qualify_level_classes: actor {name!r}'s class {actor.cls!r} "
                              f"collides across loaded packages: {sorted(candidates)}")
        actor.cls = next(iter(candidates))


def requalify_classes_to_loaded(level: Level, loaded_classes: dict[str, set[str]]) -> None:
    """Canonicalize EVERY actor's class to the LIVE loaded-set FQCN for its bare name — INCLUDING an
    already-qualified class (unlike `qualify_level_classes`, which skips a class that already contains
    a `.`). This keeps H3 post-verify LIVE-vs-LIVE now that offline ingest qualification stores an
    FQCN in the trunk: both `got` (live-qualified off the editor re-export) and `expected` (re-
    qualified here) end up on the LIVE pick, so an OFFLINE pick that differs from the live editor's
    pick can't cause a false post-verify mismatch. A bare name with 0 or 2+ loaded candidates is left
    unchanged (nothing reliable to pick — the same conservatism as `qualify_level_classes`; a 2+
    collision would already have made `qualify_live_level(got)` raise, so the compare is never
    reached). Mutates in place."""
    for name in level.order:
        actor = level.actors[name]
        bare = actor.cls.rsplit(".", 1)[-1]
        candidates = loaded_classes.get(bare, set())
        if len(candidates) == 1:
            actor.cls = next(iter(candidates))


_COMPLETE_RE = re.compile(r"\d+ Deleted Objects")
# A query verb GUARANTEED to log a large amount of text (every loaded class, always non-empty)
# so it reliably forces Editor.log's 4KB stdio buffer past its next flush boundary — unlike the
# original recipe's `OBJ LIST CLASS=Mesh NAME=zzz`, which is a silent no-op (zero log output)
# whenever nothing matches, so it could never force a flush on its own. Side effect (handled
# below, NOT cosmetic): this filler's own listing includes a class literally named
# `Engine.Polys`, which would be mistaken for a brush's PolyList block if not isolated.
_FLUSH_FILLER_CMD = "OBJ LIST CLASS=Class"


def _segment_since_header(text: str, package: str) -> str | None:
    """`text` from the LAST `Dependencies of <package>:` header onward, or None if that header
    hasn't appeared yet. `Editor.log`'s 4KB buffering means a read can surface stale content
    from BEFORE this call even started (a write can sit buffered since well before `offset` was
    taken, only flushing afterward) — `rfind` always anchors on the most recent walk, never an
    earlier one whose own completion marker would otherwise cause a false-positive (confirmed
    live 2026-06-20)."""
    idx = text.rfind(f"Dependencies of {package}:")
    return None if idx == -1 else text[idx:]


def _blocks_only(segment: str) -> str:
    """`segment` (from `_segment_since_header`) truncated at the walk's own `Objects:` summary
    line, so a LATER command's output sharing this read window — e.g. `_FLUSH_FILLER_CMD`'s own
    `Class Engine.Polys` listing entry — can never be mistaken for one of the walk's brush
    blocks (confirmed live 2026-06-20: `qualify_live_level` saw 3 `Engine.Polys` blocks for a
    1-brush level until this truncation was added)."""
    end = segment.find("\nLog: Objects:")
    return segment if end == -1 else segment[:end]


def dump_obj_dependencies(driver, *, package: str = "MyLevel",
                          max_attempts: int = 20, poll_interval: float = 1.0) -> str:
    """Settle-and-read recipe (revised 2026-06-20 —
    dev/docs/spikes/2026-06-20-obj-dependencies-untextured-poly-correlation.md). Two
    independent issues made the original single-attempt recipe unreliable, both fixed by
    retrying: (1) `Editor.log` is a 4KB stdio-buffered stream — genuinely-complete output can
    sit invisible to an external reader until something pushes total bytes written past the
    next flush boundary; (2) a "Cleaning up..." GC-progress dialog (window titled literally
    `xmessage`) can appear during the GC pass `OBJ DEPENDENCIES` (like most commands) triggers,
    and never auto-closes headless — it blocks every later command from reaching the Command
    box until dismissed. Each attempt dismisses any stuck dialog, drives the guaranteed-verbose
    `_FLUSH_FILLER_CMD` to force a flush, and checks for THIS walk's own completion marker ("N
    Deleted Objects" occurring after the most recent `Dependencies of <package>:` header — NOT
    just anywhere in the read text, which could match a stale earlier walk's terminator that
    happened to flush in the same burst) — live-confirmed reliable (5/5 rounds, 2026-06-20).
    Returns only the isolated blocks segment (`_blocks_only`), never the raw read. Raises
    `TimeoutError` rather than ever returning a possibly-partial dump."""
    offset = driver.log_size()
    driver.obj_dependencies(package)
    for _ in range(max_attempts):
        driver.dismiss_blocking_dialog()
        driver.exec(_FLUSH_FILLER_CMD)
        time.sleep(poll_interval)
        segment = _segment_since_header(driver.read_log_since(offset), package)
        if segment is not None and _COMPLETE_RE.search(segment):
            return _blocks_only(segment)
    raise TimeoutError(f"OBJ DEPENDENCIES PACKAGE={package} did not complete within "
                       f"{max_attempts} attempts ({max_attempts * poll_interval:.0f}s)")


def _read_loaded_classes(driver, *, max_attempts: int = 45, poll_interval: float = 2.0,
                         ) -> dict[str, set[str]]:
    """Settle-and-read `OBJ LIST CLASS=Class` for `qualify_level_classes`. Unlike `OBJ
    DEPENDENCIES` this command has no "N Deleted Objects"-style completion marker to wait for
    (it's a flat enumeration, not a walk with its own terminator) — so completion is detected by
    polling until TWO CONSECUTIVE reads parse to the same non-empty map, rather than trusting a
    single post-exec read. A single immediate read raced `Editor.log`'s 4KB stdio buffering and
    returned a near-empty partial class list in practice (caught live 2026-06-21 debugging a
    `qualify_level_classes` false "not loaded" on `LevelInfo`, which IS always loaded). Raises
    `TimeoutError` rather than ever returning a possibly-partial map.

    The dialog-dismiss and flush-filler are re-driven EACH iteration (mirroring the sibling
    `dump_obj_dependencies`), not once before the loop: a materialize that cold-loads a large game
    package (`DeusEx.u`) can raise the "Cleaning up..." GC dialog partway through the load, which
    headless never auto-closes and which wedges every later command — so a once-before dismiss lets
    the class set never settle and the poll times out deterministically. Re-flushing each round also
    keeps pushing the 4KB stdio buffer past its boundary while the load is still emitting classes.
    The ceiling is 90s (45×2s): a cold `DeusEx.u` class enumeration runs well past the former 10s
    (confirmed live 2026-07-25 — `preview --game` of a `DeusExMover` level timed out at 10s on every
    attempt, succeeded once given the longer window)."""
    offset = driver.log_size()
    previous: dict[str, set[str]] | None = None
    for _ in range(max_attempts):
        driver.dismiss_blocking_dialog()
        driver.exec(_FLUSH_FILLER_CMD)
        time.sleep(poll_interval)
        current = parse_loaded_classes(driver.read_log_since(offset))
        if previous is not None and current and current == previous:
            return current
        previous = current
    raise TimeoutError(f"OBJ LIST CLASS=Class did not stabilize within "
                       f"{max_attempts} attempts ({max_attempts * poll_interval:.0f}s)")


def qualify_live_level(level: Level, driver) -> None:
    """Qualify `level`'s textured polys AND bare actor classes from the editor's CURRENTLY
    LOADED level/package set. Caller must have already loaded the matching content into
    `driver` (MAP LOAD / a fresh re-import) — this function only reads."""
    qualify_level_textures(level, parse_obj_dependencies(dump_obj_dependencies(driver)))
    qualify_level_classes(level, _read_loaded_classes(driver))



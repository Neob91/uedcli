"""`texture` — the offline texture catalog (sync / list / search / tags / classify)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ... import config, container_assets
from .. import resources
from ..errors import CommandError, ProjectError


def run(args) -> int:
    """The offline texture catalog. STATELESS — no level, no live editor read/edit. `sync`
    mints a per-command ephemeral container for UCC batchexport only; every other verb is pure
    manifest I/O.

    Project-scoped: the catalog dir defaults to the resolved project's `catalog` dir
    (`config.project_catalog_dir`, default `<root>/texture-catalog/`) and `sync` discovers
    packages from the composed config search path (project overlay shadows game base), NOT the
    retired hardcoded `substrate_code_dirs`/`texture_catalog_root` (Andrzej's directive, dev/docs/direction/containers.md
    2026-07-14 — texture sync onto the composed project+game path). The project is resolved LAZILY:
    `sync` always needs it (for discovery); every OTHER verb — reads AND `classify set` — needs it
    only to default the catalog dir, so an explicit `--catalog-dir` runs OUTSIDE a project (the
    per-package flock is catalog-adjacent, `<catalog>/.locks/`, not project-derived — decision
    2026-07-18)."""
    from ... import texture, texture_catalog as tc

    _project = {}
    def project() -> config.Project:                     # resolve once, only when actually needed
        if "p" not in _project:
            _project["p"] = resources.resolve_project(args)       # no project ⇒ ProjectError → exit 2
        return _project["p"]

    catalog_dir = args.catalog_dir or config.project_catalog_dir(project())

    def lock_dir() -> str:
        """`<catalog>/.locks/` — the per-package flock home, derived from the CATALOG DIR it
        guards, not the project (decision 2026-07-18): every writer to one catalog shares one lock
        domain even across projects/checkouts pointing at the same shared catalog, and an explicit
        `--catalog-dir` needs no project for ANY texture verb (restores spec §6's override
        contract for `classify set`). Self-ignoring like `.uedcli/` — lock litter can never be
        committed from a tracked catalog dir."""
        return str(config.self_ignoring_dir(Path(catalog_dir) / ".locks", create=True,
                                            what="catalog lock dir"))

    def _load_all() -> list[tc.Manifest]:
        d = Path(catalog_dir)
        out = []
        for jf in sorted(d.glob("*.json")) if d.is_dir() else []:
            try:
                if (m := tc.load_manifest(jf)) is not None:
                    out.append(m)
            except (ValueError, OSError) as e:
                print(f"skipping unreadable manifest {jf}: {e}", file=sys.stderr)
        return out

    if args.sub == "sync":
        # Discovery is config-driven (Andrzej's directive, dev/docs/direction/containers.md 2026-07-14): EVERY package on
        # the composed project+game search path (project overlay shadows game base, stem-deduped by
        # `composed_search_files`) — including `.u` code packages, because a `.u` is the same Unreal
        # package format and can hold textures too (DeusEx skins live in `DeusExItems.u`). A package
        # with no textures just batchexports nothing and is skipped. The build container mounts the
        # WHOLE composed dir set at `/resources/<n>` (one uniform scheme) so every discovered package
        # is reachable by bare name via its crafted `[Core.System] Paths`.
        user_config = config.load_user_config()
        if user_config is None:                          # hard error — decision 2026-07-06 05:12
            raise ProjectError(
                "no per-user games config (~/.uedcli/config.toml): texture sync needs the game's "
                "base package paths; create it with a [games.<name>] paths dir list")
        # (bare_name, host_file) for EVERY package on the composed path, stem-deduped
        # project-shadows-base by composed_search_files.
        all_pkgs = [(config.pkg_stem(p), p)
                    for p, _prov in config.composed_search_files(project(), user_config)]
        search_dirs = config.composed_search_dirs(project(), user_config)
        mounts = container_assets.resource_mounts(search_dirs)   # one uniform set: all reachable
        if args.package:
            want = args.package.casefold()
            pkgs = [(n, p) for n, p in all_pkgs if n and n.casefold() == want]
            if not pkgs:
                raise CommandError(
                    f"package not found on the composed search path: {args.package}")
        else:
            pkgs = [(n, p) for n, p in all_pkgs if n]
        images_root = str(config.texture_images_root())
        if not pkgs:
            print("no packages found on the composed search path", file=sys.stderr)
            return 2
        # batchexport runs offline UCC in a container. Editors are per-command ephemeral (no
        # standing container, no `--container` flag), so mint ONE no-GUI container for the whole
        # sweep and tear it down after.
        from ...stub import ephemeral_build_container, StubBuildError
        built = 0
        try:
            with ephemeral_build_container(mounts=mounts,
                                           state_dir=config.state_dir(project().root, create=True)
                                           ) as container:
                for name, file_path in pkgs:
                    try:
                        m = tc.sync_package(package=name, package_file=file_path, container=container,
                                            catalog_dir=catalog_dir, images_root=images_root,
                                            force=args.force, batchexport=texture.batchexport_textures,
                                            lock_dir=lock_dir())
                    except (subprocess.CalledProcessError, OSError, ValueError) as e:
                        print(f"{name}: skipped ({e})", file=sys.stderr)   # one bad package never aborts
                        continue
                    if m is not None:
                        built += 1
                        print(f"{name}: {len(m.textures)} textures")
        except StubBuildError as e:                    # container couldn't start (docker down / image)
            print(f"texture sync: could not start build container: {e}", file=sys.stderr)
            return 2
        if built == 0:
            # Discovery + batchexport ran; nothing produced textures (none on the container Paths,
            # per the v1 limit) — a NORMAL outcome, not a misconfiguration. rc 0.
            print(f"discovered {len(pkgs)} packages; none produced textures "
                  f"(none on the container Paths)", file=sys.stderr)
        return 0

    if args.sub == "list":
        state = next((s for s in ("unclassified", "classified", "stale", "removed")
                      if getattr(args, s)), None)
        for m in _load_all():
            if args.package and m.package.lower() != args.package.lower():
                continue
            for e in m.textures.values():
                if state and tc.bucket(e) != state:
                    continue
                print(f"{e.ref}\t{e.width}x{e.height}\t{tc.bucket(e)}\t{','.join(e.tags)}")
        return 0

    if args.sub == "search":
        if not args.query and not args.tag and not args.color:
            raise CommandError("search needs a query or --tag/--color")
        try:
            tc.validate_colors([c.lower() for c in args.color])
        except ValueError as e:
            raise CommandError(str(e))
        refs = tc.search(_load_all(), args.query, tags=args.tag, colors=args.color,
                         package=args.package)
        if not refs:
            # No match is a NORMAL outcome (rc 0): stdout stays empty so a pipe into
            # `poly set` is clean; the "no matches" note goes to stderr.
            print("no matches", file=sys.stderr)
            return 0
        for r in refs:
            print(r)
        return 0

    if args.sub == "tags":
        for tag, n in tc.all_tags(_load_all(), package=args.package):
            print(f"{tag}\t{n}")
        return 0

    if args.sub == "classify" and args.csub == "status":
        manifests = [m for m in _load_all()                  # load ONCE (atomic snapshot + cheaper)
                     if not args.package or m.package.lower() == args.package.lower()]
        counts = tc.status_counts(manifests)
        for pkg, c in sorted(counts["per_package"].items()):
            print(f"{pkg}\ttotal {c['total']}\tclassified {c['classified']}\t"
                  f"unclassified {c['unclassified']}\tstale {c['stale']}\tremoved {c['removed']}")
        g = counts["total"]
        print(f"TOTAL\t{g['total']} / {g['classified']} classified")
        if args.full:
            for m in manifests:
                for e in m.textures.values():
                    if tc.bucket(e) in ("unclassified", "stale"):
                        print(e.ref)
        return 0

    if args.sub == "classify" and args.csub == "set":
        pkg = args.ref.split(".", 1)[0]
        mpath = tc.manifest_path(catalog_dir, pkg)
        with tc._package_lock(lock_dir(), pkg):
            try:
                m = tc.load_manifest(mpath)               # corrupt catalog JSON → ValueError, caught below
                if m is None:
                    raise CommandError(
                        f"no catalog for package: {pkg} — run 'texture sync --package {pkg}'")
                out = tc.classify_set(m, args.ref, tags=args.tags, description=args.description,
                                      colors=args.colors)
                tc.save_manifest(mpath, out)
            except (ValueError, OSError) as e:
                raise CommandError(f"{args.ref}: {e}")
        print(args.ref)
        return 0

    raise CommandError(f"unimplemented texture sub-verb: {args.sub}")

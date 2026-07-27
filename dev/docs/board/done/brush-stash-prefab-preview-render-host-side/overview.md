+++
priority = "p?"
kind = "unknown"
summary = "`brush`/`stash`/`prefab preview` render host-side — no container"
+++

# `brush`/`stash`/`prefab preview` render host-side — no container

— 2026-07-12
(branch `uedcli-impl`, commit `d9d7e98af`). These three preview verbs were the ONLY container
users that drove neither the editor nor UCC; they used the standing `dx-lum-uned` container purely
as an ImageMagick + `/work` file-staging utility. Now `_render_actors_to_out` (`dispatch.py`)
writes the PPM straight to the host `--out`, and `--png` decodes PPM→PNG with Pillow (already the
sole third-party dep) — zero docker, no editor. The `container` param was dropped from the helper
and all three call sites. Fixed a latent path bug along the way (the `--png` extension swap used
`rsplit(".",1)` on the whole path, mangling `--out` when the filename had no extension but a parent
dir contained a dot → now `os.path.splitext`), and wrapped the write/convert so Pillow/OS errors
surface as a clean `_SelectionExit` exit-2 message instead of a traceback (per the no-exception
rule). Tests added: `--png` Pillow path, the no-extension/dotted-parent regression, the clean-error
path (`tests/test_stash_dispatch.py`). Docs reconciled: `architecture.md` "Preview internals" +
the image-deps note (ImageMagick now scoped to the `level preview` editor-screenshot path only —
`wine_ctl.py`'s `import`/`convert`), `preview.py` docstring, `cli.py --png` help. Full offline
suite green (997 passed). Reviewed by two cold subagents; both findings resolved.
**Remnant (low pri):** the older two preview tests still monkeypatch a `no_docker` guard onto
`dispatch.subprocess.run`, which is now inert (the path makes no subprocess call) — harmless, could
be dropped on a future pass. The `from PIL import Image` sits lazily in the `--png` branch, aligning
with the open lazy-import item in `board/inbox/`.

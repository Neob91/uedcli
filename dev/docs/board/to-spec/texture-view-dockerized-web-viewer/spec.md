# Spec — `texture view` + dockerized web viewer

## Goal

Let a human browse the texture catalog visually: a `texture view` verb that serves a small web UI with
image thumbnails and a search box, reading the tracked catalog plus the gitignored per-user image
cache. Deferred from the 2026-06-22 texture tool (`decisions.md` 2026-06-22 explicitly parked "a
dockerized web viewer + `texture view`" to a follow-on spec "reading the same catalog; `view` is the
viewer's entry point and ships with it").

## Two blocking concerns before design

### 1. Which catalog does it read?

The 2026-06-22 note says it reads "the tracked `texture-catalog/` + gitignored `.uedcli/textures/`" —
the legacy name-keyed manifest + PNG cache. But `direction/asset-catalog.md` deletes that store and
replaces it with hash-keyed classify shards + a **content-addressed per-user preview cache** shared
across projects, and reframes the whole surface: `texture` is one of four kinds (`texture`/`class`/
`sound`/`music`), discovery is `search`, images come from `preview`. A viewer built on the legacy
layout is throwaway. See `questions/target-catalog-and-scope.md`.

### 2. Is a web server in uedcli's scope at all?

Nothing in the direction docs authorizes uedcli to run a **web server**, and it cuts against the
grain of several rulings:
- `direction/containers.md`: the only containers uedcli drives are wine ones (editor / UCC build /
  game). "uedcli itself never runs in one." A viewer container is a new, non-wine kind.
- `direction/asset-catalog.md`: the audience is "an LLM agent". A human web UI serves a different user;
  the direction's own answer to "see an asset" is `preview` (produce the image file) + `search` (rank
  refs), which an agent consumes as files/lines.
- `conventions.md` "Verbs compose": producer verbs print to stdout; a long-lived HTTP server is a
  different modality from the CLI's stateless one-shot verbs.

This does not kill the item — a human-facing browse tool is a reasonable thing to want — but whether
it belongs *inside* uedcli (a `texture view` verb spinning a server/container) versus being served by
already-produced `preview` artifacts through any static file server is a real scope call for the owner.

The rest of this spec sketches the design **conditional on** a yes to building it, targeting the
redesign's store (the recommended target if it ships at all).

## Current state

- No `view` verb exists (`cli/parsers/texture.py`, `cli/commands/texture.py` —
  `sync|list|search|tags|classify`).
- Legacy image cache: `config.texture_images_root()` → per-user PNGs written by `sync`'s
  `_decode_exported` (`texture_catalog.py:372`), keyed by package/stem.
- Search already exists offline: `texture_catalog.search` (ranked, text/tag/color) and, under the
  redesign, `texture search --similar`/`--color`. The viewer's search box should call the **same**
  ranking, never a second implementation.
- Decode/preview is offline and native (`utexture.DecodedTexture`, `direction/packages.md`), so image
  artifacts can be produced with no editor/container.

## Design (conditional; targets the redesign store)

Surface:

```
texture view [--port N] [--catalog-dir DIR] [--no-browser]
    help: "serve a local web page to browse the texture catalog (thumbnails + search); Ctrl-C to stop"
    --port      help: "port to bind on localhost (default: an ephemeral free port)"
    --no-browser help: "don't try to open a browser; just print the URL"
```

Behavior:
- Bind **localhost only** (a catalog browser is a personal tool, not a network service).
- Serve a single static page + a small JSON endpoint that returns search results by calling the
  existing catalog `search` (no new ranking). Thumbnails come from the content-addressed preview cache;
  a cache miss triggers the same native `preview` decode the CLI uses (never a wrong pixel — an
  undecodable texture shows a named-error tile, per `asset-catalog.md`).
- Print the URL to stderr; open a browser unless `--no-browser`.

**Container vs in-process:** the item title says "dockerized", but native offline decode + a stdlib
`http.server` need no container at all — which is strictly better against the "uedcli drives only wine
containers" ruling. Recommend **in-process, no Docker**. If a container is wanted (dependency
isolation, a richer JS stack), it is a new non-wine container type and needs an explicit owner yes —
folded into the scope question.

**Verb-composition note:** `view` is a long-lived server, unlike every other `texture` verb. That is
inherent to a browser UI and acceptable if the item is approved, but it is why `view` is its own verb
and never a flag on `list`/`search`.

## Edge cases & errors

| Case | Behavior | Exit |
|------------------------------|-----------------------------------------------------|---
| Empty catalog | serve the page; it shows "no textures — run `texture sync`" | 0 |
| Port in use (explicit `--port`) | exit 2 naming the port | 2 |
| Undecodable texture | named-error tile in the grid, page keeps working (`asset-catalog.md` enumeration rule) | 0 |
| No project + no `--catalog-dir` | existing `ProjectError` exit 2 | 2 |
| Ctrl-C | clean shutdown, exit 0 | 0 |

## Tests

- The JSON search endpoint returns the same refs as `texture search` for the same query (one ranking,
  pinned).
- Thumbnail endpoint serves a cached image; a cache miss decodes then serves; an undecodable ref
  returns the error tile, not a 500.
- Port-in-use → exit 2 naming the port.
- Server binds localhost only (not 0.0.0.0).
- Offline-testable: drive the handler functions directly, no real socket/browser needed for the logic.

## Open questions

- **Scope + target store** — is a web viewer in uedcli's remit, in-process vs dockerized, and against
  the legacy store or the asset-catalog redesign? `questions/target-catalog-and-scope.md`. Both sub-
  questions gate whether this is built at all and on what, so they are one owner decision.

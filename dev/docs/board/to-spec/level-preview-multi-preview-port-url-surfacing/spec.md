# `level preview` multi-preview port/URL surfacing — DRAFT spec

## Goal

Decide whether, and how, `level preview` should surface the noVNC port/URL when more than one
preview could run at once — the concern the overview raised for "2+ simultaneous previews".

## Current state (the overview predates the architecture pivot)

The item was written against the OLD editor-screenshot preview (an interactive noVNC editor,
`-p 0:6080` + `docker port`, "one previewable editor per host"). That backend is **deleted**
(`rendering.md:8`, `trunk-and-editor.md:88`). The current `--game` preview is different in every
way that matters here:

- **Batched snapshots, not an interactive session.** `level preview` boots/reuses a container,
  renders the requested still shots, returns. It is not a live editor you watch (VNC is dev-debug
  only — `trunk-and-editor.md:135`).
- **One WARM container per Unix user**, `uedcli-game-preview-<uid>` (`preview_game.py:391`),
  serialized by a per-user flock (`:395`, `:682`). Within a user, previews **run one at a time**;
  concurrency across users is by construction (distinct uid → distinct container name).
- **Host port is already ephemeral and correctly resolved.** The container publishes
  `-p 127.0.0.1::6080` (a kernel-assigned host port — `preview_game.py:349`), read back per container
  via `docker port` in `_novnc` (`:303`). Two containers therefore never collide on a host port, and
  each reports its own — the v1 "one per host" limitation is already gone.
- **The URL is surfaced only with `--keep-alive`**: `http://localhost:<port>/vnc.html`
  (`preview_game.py:704`), which pins the warm container for live inspection. A normal batch prints
  no URL because there is nothing to watch.

**So the literal ask — surface the port/URL for concurrent previews — is largely already satisfied:**
ports are ephemeral and per-container, the one URL that exists (`--keep-alive`) reports the right
one, and the design deliberately runs one warm preview per user.

## The one real gap

Within a single user you cannot hold TWO different live previews at once. A second `--keep-alive`
with a different size/config mismatches the warm container's fingerprint; if the first is pinned, the
second **errors** rather than starting a second container (`preview_game.py:504-507`). This is by
design (one warm container per user), not an oversight.

## Design options (Q1 — is anything more wanted?)

- (a) **Close/downscope** (recommend). The pivot resolved the port collision; ephemeral ports +
  per-container `docker port` already give a correct URL per container, and `--keep-alive` prints it.
  Deliverable: confirm no code change, refresh the overview to the post-pivot reality, done. Optional
  tiny polish: also print the noVNC URL/port on a normal `--game` batch (not just `--keep-alive`) so
  it is discoverable — but a non-pinned container self-terminates, so the URL is short-lived and may
  mislead; recommend NOT doing this.
- (b) **Support N concurrent pinned live previews per user.** Real work against the current design: a
  new container-identity scheme (name per preview, not per user), a lifecycle/teardown story
  (`level preview` owns no `stop` verb — deliberately, `trunk-and-editor.md:135`), and a URL list
  output. This is re-opening the persistent-editor model the direction docs rejected.

Recommend (a): the concern is an artifact of the retired backend; the current model is intentionally
one warm preview per user, and the port/URL it surfaces is already correct.

## Edge cases & errors (only if (b) is chosen)

- Two pinned previews, same config → could share one container or error; needs a rule.
- Port/URL list output when N containers run → a `--json` list of `{container, url}`.
- Teardown identity: which `docker rm -f` releases which — the reason the one-per-user model exists.

## Tests

- Under (a): a regression asserting `_novnc` returns the container's own ephemeral port (already
  effectively covered by `test_preview_game.py`); no new behavior. Refresh the overview text.
- Under (b): concurrent-container identity, port-list output, teardown — a substantial suite.

## Open questions

- Q1 — close/downscope as resolved-by-pivot, or invest in N concurrent per-user previews
  (`questions/scope-after-pivot.md`).

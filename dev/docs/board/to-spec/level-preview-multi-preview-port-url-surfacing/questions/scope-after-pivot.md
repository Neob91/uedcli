# Multi-preview port/URL — close as resolved by the architecture pivot, or build N-per-user?

## Context

The item was written for the retired editor-screenshot preview ("one previewable editor per host").
The current `--game` preview is a batched-snapshot flow over ONE warm container per Unix user,
flock-serialized, with an ephemeral host port resolved per-container via `docker port`. Ports no
longer collide, and the only URL that exists (`--keep-alive`, `preview_game.py:704`) already reports
the right one. Cross-user concurrency works by construction; within a user, previews run one at a
time by design.

Options:
- (a) **Close/downscope** (recommend): confirm no code change, refresh the overview to the post-pivot
  reality. The port/URL concern is an artifact of the deleted backend.
- (b) Build N concurrent pinned live previews per user: a per-preview container identity, a
  teardown/`stop` story (which `level preview` deliberately lacks), and URL-list output — effectively
  re-opening the persistent-editor model the direction docs rejected
  (`trunk-and-editor.md` Rejected, VNC-handoff bullet).

## Answer

<!-- Empty = open. -->

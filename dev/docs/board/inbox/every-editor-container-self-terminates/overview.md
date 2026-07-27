+++
priority = "p2"
kind = "owner-question"
summary = "EVERY editor container self-terminates when idle, not just the warm one"
+++

# EVERY editor container self-terminates when idle, not just the warm one

`direction/containers.md` currently promises idle self-death only for the warm containers. That is
where the container leak lives: teardown exists solely in a host-side `finally`, and SIGTERM (which
is what `timeout … bin/uedcli level materialize` sends) kills Python without running it — so a
killed or wedged ephemeral build strands a running editor and its ~0.5 GB wineprefix volume,
permanently. Measured on this host 2026-07-26: 8 stranded containers over ~4 hours and 9 orphan
volumes ≈ 5.5 GB. No host-side handler can fix it (SIGKILL), so the container has to be able to
reap itself. Proposed addition, verbatim, to `direction/containers.md` § "Per-command ephemeral is
the concurrency story":

> **Every editor container self-terminates when idle — ephemeral ones included.** Teardown by the
> invocation that started it is the fast path, not the guarantee: a killed uedcli process runs no
> cleanup at all, and an editor that outlives its parent would otherwise hold its memory and its
> disk forever. The container's own idle timer is what makes "ephemeral" true rather than merely
> intended. Because a container cannot remove its own volume, the volume is reclaimed by a sweep of
> unattached volumes on the next acquire — keyed on having no container attached, never on age,
> since a legitimate build can outlive any threshold.

Folded into `specs/2026-07-18-warm-editor-materialize.md` decision 8 + §4.5. *(Rejected: host-side
signal handlers as the mechanism — they cannot cover SIGKILL; an age-based sweep as the primary
mechanism — two legitimate multi-minute builds were in flight among the 8 stranded containers
observed, and an age threshold would have killed them.)*

+++
priority = "p3"
kind = "owner-question"
summary = "Should the editor readiness-retry also recover wineprefix corruption?"
+++

# Should the editor readiness-retry also recover wineprefix corruption?

p3` **Should the editor readiness-retry also recover wineprefix corruption?** The
bounded `ensure_editor` retry (landed 2026-07-19) reaps only the *container* and re-mounts the same
per-id `uned-wp-<id>` wineprefix volume each re-spin — so it recovers transient container/X-display
startup races but NOT a corrupt/half-initialized wineprefix. Wiping the volume (`docker volume rm`)
between attempts would cover that too, at ~0.5 GB wine re-init per retry. Deliberately deferred; your
call whether the retry should escalate to a volume wipe on a later attempt.

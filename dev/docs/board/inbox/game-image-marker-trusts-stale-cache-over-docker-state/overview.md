+++
priority = "p2"
kind = "debug"
summary = "ensure_image()'s game-image.sha256 marker skips the rebuild without checking the image actually still exists in Docker"
+++

# game-image marker trusts a stale cache over live Docker state

`uedcli/preview_game.py`'s `ensure_image()` (~line 238-264) fast-paths past `build-image.sh` when
a host-side marker file (`$UEDCLI_HOME/cache/game-image.sha256`) matches the current source hash —
on the assumption that a matching hash means the `uedcli-game:latest` image is already built. It
explicitly skips a `docker image inspect` check to save ~0.3s per warm preview, per its own comment:

> "an externally-deleted image surfaces at boot as a named `docker run` error, which is rare"

Hit this for real: Docker's image cache got evicted externally (lost both `ued-x86-runtime` and
`uedcli-game`, apparently an automatic eviction under disk pressure — unrelated to uedcli). The
marker file was untouched, so every subsequent `level photo --game` kept skipping the rebuild and
failing with `pull access denied for uedcli-game` — the same class of error as the
`dx-lum-uned`/`ued-x86-runtime` tag-mismatch bug fixed earlier, but with a different root cause
(stale cache marker, not a naming bug) and no way to recognize the failure without knowing to
delete the marker file (`rm $UEDCLI_HOME/cache/game-image.sha256`) and retry.

Not urgent to fix outright (the tradeoff is deliberate and documented), but worth either: rebuilding
on that specific docker error and retrying once automatically, or naming the fix (delete the marker)
directly in the error message so a user/agent doesn't have to read the source to recover.

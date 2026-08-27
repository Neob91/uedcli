+++
priority = "p2"
kind = "debug"
summary = "`packages.write_paths_and_reload` repairs a missing `[Core.System] Paths` line with `docker exec sed -i` on `/opt/UED22/unrealtournament.ini` — but `ensure_editor` bind-mounts that path as a single FILE, and `sed -i` renames its temp over the target, which cannot work on a bind mount. When the branch fires the build dies with `sed` exit 4 and nothing written. Seen once on a UNATCO materialize; the retry passed."
+++

# `write_paths_and_reload`'s `sed -i` can never work on the bind-mounted engine ini

`level materialize` on the 1437-actor UNATCO trunk failed with:

    materialize failed (nothing written): Command '['docker', 'exec', '<c>', 'sed', '-i',
    '/^\[Core.System\]/a\...7 Paths lines...', '/opt/UED22/unrealtournament.ini']'
    returned non-zero exit status 4

An immediate retry of the identical command succeeded, so the FIRING is intermittent — but the branch
itself is dead code that can only ever fail. `editor.engine_ini_mount` bind-mounts a host file over
`/opt/UED22/unrealtournament.ini`; `sed -i` writes a temp beside the target and `rename()`s it into
place, which is not possible across a single-file bind mount (GNU sed reports exit 4, an I/O error).
`editor.py`'s own comment at line 316 already records this for the entrypoint's removed `sed -i`.

Why it fired is not established. The pre-launch crafted ini demonstrably contains all seven
`Paths=` lines (checked by crafting it in-process), and a live container sampled every 15 s for
2.5 min never lost them — so the `cat`-and-substring check that decides whether to `sed` saw
something else in that one run. Whatever the trigger, `write_paths_and_reload` is documented as
"idempotent belt-and-suspenders" over what `ensure_editor` already wrote pre-launch, so the honest
fix is to drop the live repair (or make it rewrite the HOST ini file, which the process can write
directly, instead of `sed`ing the container-side mount point) rather than leave a repair path that
turns a transient read into a failed build.

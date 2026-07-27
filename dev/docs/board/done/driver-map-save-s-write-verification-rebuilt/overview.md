+++
priority = "p1"
kind = "debug"
summary = "`driver.map_save`'s write verification rebuilt — `inbox.md` CLOSED 2026-07-25"
+++

# `driver.map_save`'s write verification rebuilt — `inbox.md` CLOSED 2026-07-25

The old rule ("two equal non-zero sizes ⇒ finished"; "`stat` exit 1 ⇒ no file, anything else ⇒
docker failed") could not tell *finished* from *stalled* (a truncated map's size is just as stable
as a finished one's) nor *file-missing* from *container-dead* (a stopped container, a missing
container and a permission error ALL exit 1 — re-verified live), and its `subprocess.run` had no
`timeout=`. Replaced by four stacked signals: a pre-`MAP SAVE` stat the file must differ from; N
equal readings across a settle window; a structural check of the written package's header
(`driver.package_header_problem`); and liveness from a probe SENTINEL, not an exit code, with each
`docker exec` bounded. `container_file_size` is deleted in favour of `container_stat` /
`container_file_head` / `package_problem` over one `_container_probe`. The two tests that could not
fail (both passed `timeout=0.0`) and the docker-failure test that mocked an impossible
`returncode=126` pairing were rebuilt on a fake clock that exercises the real 600 s/1 s/3 s
defaults. `decisions.md` 2026-07-25 11:31 UTC; `architecture.md` "Editor driver";
`unrealed/commands.md`. **Remnant → `inbox.md`:** driver's other `docker exec` calls (8 across 6
methods, plus `xfer.remove`) are still unbounded.

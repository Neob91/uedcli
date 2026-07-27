+++
priority = "p2"
kind = "unknown"
summary = "SPEC REVIEW ROUND 1 (2026-07-26) — the warm-editor spec DID NOT PASS the gate"
+++

# SPEC REVIEW ROUND 1 (2026-07-26) — the warm-editor spec DID NOT PASS the gate

Three cold Opus reviewers over `specs/2026-07-18-warm-editor-materialize.md`; ~50 findings, heavy
independent convergence. **The premise survived** — all three agree a one-shot commandlet
structurally satisfies `commands.md`'s "fresh editor, exactly one level loaded" precondition that
warm reuse cannot meet. **The mechanisms did not.** The spec is PARKED, not merged; per CLAUDE.md
"Review gates" it re-enters at round 1 after re-design. Findings, grouped, all actionable:

**A. The verify container cannot work as specified (all 3 reviewers).**
1. `store_export.export_dx_t3d` is three `docker exec`s into a RUNNING container; §5.1 specifies a
   `docker run --rm` whose command exits by itself. You cannot exec into an exited container. §6's
   "simply handed the one-shot container" and §5.1 are mutually exclusive — and detaching to fix it
   reinstates exactly the leak shape the spec exists to remove.
2. The image `ENTRYPOINT` is `tini -- bash /opt/uned/entrypoint.sh`, which ignores its args and
   gates the editor on `${LAUNCH_UED:-1}`. `LAUNCH_UED=0` lives in `docker-compose.yml` and in
   `stub.ephemeral_build_container`'s explicit `-e`, neither of which reaches a plain `docker run`.
   So the specced verify container boots Xvfb + fluxbox + x11vnc + `unrealed.exe`, waits for a
   window, THEN runs UCC — a full GUI stack, not a ~3 s one-shot. Needs `--entrypoint` + explicit
   `-e LAUNCH_UED=0`, and the timing claim is unestablished until measured.
3. **`/stubs` is silently lost.** It is a compose volume, not part of `resource_mounts`, and the
   crafted ini puts it FIRST on `[Core.System] Paths` (the whole v69-shadowing scheme). A plain
   `docker run` has no `/stubs`, so any level using a stubbed class → the class never loads →
   `qualify_level_classes` raises → **exit 2 on a correct build, deterministically, for every
   stub-using project**. SP-F.2 only catches it if its fixture happens to use a stub.
4. **stdout contamination.** `OBJ LIST CLASS=Class` emits a line for the class literally named
   `Engine.Polys`, which `parse_obj_dependencies` opens as a brush block. That is why
   `qualify._blocks_only` exists — its docstring records the live failure (3 blocks for a 1-brush
   level). §5.1's script runs both dumps into ONE undelimited stream, re-creating it; §3's "parsers
   reused verbatim" omits `_segment_since_header`/`_blocks_only` from both the kept and deleted
   lists. Also unknown whether `_blocks_only`'s `\nLog: Objects:` marker even appears in commandlet
   stdout, whose format differs. Fix direction: a delimiter line between dumps, or two separate
   invocations; either way the segmentation must survive.

**B. The foundation is unevidenced.** Neither committed harness in `spikes/headless-materialize/`
contains `OBJ DEPENDENCIES`, `OBJ LOAD` or `OBJ LIST` — zero hits. The findings write-up asserts
the verb works headless and lands on stdout, but nothing reproducible backs it, and
`rules/spikes.md` calls that the state a finding rots in. Nor was it observed after a `MAP LOAD` of
an existing `.dx` (the spike ran it, if at all, after an in-memory build). Decision 6 rests on it.

**C. The idle watchdog can kill live builds — and decision 8 puts it on the DEFAULT path.**
§4.5's premise "every host-side `Driver` exec routes through `wine_ctl`" is false; `driver.py`'s
own docstring enumerates the exceptions. `map_save` types through `wine_ctl` once, then polls up to
**`timeout=600.0`** via `docker exec sh -c`, touching no marker — and the proposed `UED_IDLE_S` is
**600**. The bounds are equal, and `levelbuild-friction` §3 records a real production `MAP SAVE
never produced a finished file (after 600s)`. Because decision 8 also puts the watchdog on the
ephemeral boot, the regression lands on the default path plus `stash intersect/deintersect`,
`native/csg_golden.py` and `tests/editor_oracle.py`. Fix: refresh the marker from the probe loop,
and make the deadline strictly greater than the longest bounded editor wait. SP-F.7 tests only the
true-positive direction; nothing tests that a slow healthy build survives.

**D. A killed build leaves a BUSY warm editor, and nothing detects it.** The health probe is
`alive` + `window=<digits>`; it cannot see "still executing the previous invocation's `MAP
REBUILD`". A SIGTERMed materialize (the spec's own §1(c) example) leaves the container up by
design; the next acquire passes the probe and types into a busy editor with fire-and-forget input —
which is the exact class `quirks.md` blames for the SP-E blocker. So the ~50 % failure can return
through a door decision 6 does not close, and decision 5 turns it into a hard exit 2. Needs a
busy/generation detector (e.g. a drive-start/end marker), not just a liveness probe.

**E. The warm path is LESS resilient than today.** §4.3 caps warm boot at ONE reboot; `ensure_editor`
retries readiness **3** times and its docstring calls startup death "the single most frequent
interruption in the build→preview loop". The justification ("a second failure predicts the ephemeral
would fail too") has no evidence and is undercut by the warm reboot minting a fresh wineprefix each
time. And the ephemeral fallback — kept for mere lock contention — is not used for the one case
where it is known-good recovery.

**F. Two more direction conflicts, unparked** (the §4.3 teardown one WAS parked correctly).
(i) §5.2/§5.3's read-write host `/work` staging bind mount contradicts `direction/containers.md`:
*"Mutable exchange — ONE container-local `/work` dir … crossed only by `docker cp` … so nothing it
holds can leak into the tree"*, plus its rejected "bind-mounting arbitrary host roots". Candidate
resolution WITHIN the ruling: read-only input mount (a `.dx` is an asset to the verify) + T3D out
over stdout. Needs the owner's confirmation that this reading is right. (ii) §4.1 puts the warm
flock and crafted-ini temp in `~/.uedcli/`, while `direction/projects-and-config.md` inventories
the per-user home as config + `cache/{textures,stubs,schema}` only and assigns flocks/staging temps
to the in-repo `.uedcli/`. `preview_game` already does the former, so code precedes spec here.

**G. The spike's acceptance criterion is both unreachable and insufficient.**
- Unreachable: two known pre-existing post-verify FALSE POSITIVES will fail warm builds for
  unrelated reasons — `levelbuild-friction` §1 (engine-stamped `Base` missing from
  `normalize.COMPUTED_PROPS`; "the single most costly defect of the run. Deterministic, not flaky")
  and `headless-materialize` §11 (a `basement` GEOMETRY line-shift). SP-F.5 would report a design
  failure that is actually one of these. **The second of the two is FIXED (2026-07-26)** — it was
  not a false positive but a real emit defect: uedcli wrote `Pan U=0 V=0`, which the editor never
  writes back, so the two brush texts differed. `emit_polygon` no longer writes a zero pan
  (`rationale/emit.md`, `unrealed/t3d.md` "A poly sub-field has NO class default"). Only the
  `levelbuild-friction` §1 `Base` blocker remains against this criterion.
- Insufficient: a **runt/unlit** map is not a "failure" by a 0/N pass-rate criterion. `friction`
  §1b documents a `--no-verify` build writing 23,126 bytes instead of 191,332 and printing success,
  and the H3 compare **structurally cannot** catch it because lighting is regenerable build output
  the compare ignores by direction. SP-E left a ready-made oracle (`warm_editor_canoncmp.py`) and
  nominated exactly this as pinnable; SP-F uses neither it nor a size/lightmap check.
- N=8 at 0 failures has weak power: a residual 10 % rate still passes ~43 % of the time. State what
  confidence N buys.

**H. Leak mechanics — the fix under-fixes, over-reaches and races.** (i) The watchdog *stops* a
container; it never `docker rm`s it, and ephemeral names are fresh uuid7s so nothing re-takes the
name — the RAM leak is fixed, the exited-container/COW-layer leak is not, and §1(c)'s "2
never-started" containers can never self-reap (they ran no entrypoint). (ii) The `uned-wp-*` glob
also matches `uned-wp-stub-*` from `stub.ephemeral_build_container`, and volumes are daemon-global
while the ephemeral half carries no uid. (iii) "No attached container" is NOT race-free: compose
creates the named volume before the container references it, so a sweep in that window removes a
booting editor's prefix — and the ephemeral path is deliberately lock-free, so there is nothing to
serialise against. (iv) The sweep runs only on the warm acquire path, i.e. never under the
contention that produces the leaks. (v) The verify container's own crafted ini is never unlinked —
one leaked temp per materialize, in a spec whose purpose is fixing leaks.

**I. Fail-closed assertion checks the wrong property.** §4.5 asserts the watchdog by checking the
env var made it in — but the named failure mode is a STALE IMAGE whose baked entrypoint has no
watchdog code, which accepts `-e UED_IDLE_S` and ignores it. Must observe the effect (the
entrypoint's own log line, as `game-entrypoint.sh` prints, or `/work/.last_use` existing). §8 pins
the same wrong property.

**J. Factual/citation defects.** (i) Today's verify runs **three** poll loops, not two —
`qualify_live_level` calls `dump_obj_dependencies` AND `_read_loaded_classes`, then
`verify_dx_matches` calls `_read_loaded_classes` again; two 90 s-ceiling class reads is also a far
more plausible home for the derived ~42 s. (ii) The crafted ini is NOT "a pure function of the
mounts" — `paths_ini_lines` host-scans each dir for present extensions, and the host pre-bake
`uned/UED22/unrealtournament.ini` is covered by no fingerprint component. (iii) `preview_game`
does not have the shape §6 says it factors: `acquire_warm_container` contains no flock (docstring:
"Caller MUST hold the flock") and no reboot retry; `_acquire_lock` is **bounded blocking**
(`WARM_LOCK_TIMEOUT_S`, raises) not nonblocking, and `REBOOT_BUDGET=3` is consumed in the render
loops. (iv) `Commandlet batchexport not found` is in `commands.md`, not `quirks.md`. (v) §10 lists
`Save.tmp`'s location as UNPINNED although the spec's own headline spike answered it 🔬 ("in the
destination's own directory … two concurrent saves into one directory would therefore collide") —
which is live for conflict F(i). (vi) §1(c)'s host numbers (8 containers / 9 volumes / ~5.5 GB) are
my own session's census and appear nowhere committed; `friction` §2 reports a different count over
a different window. (vii) "never purge" strengthens the cited spike's "does NOT **immediately**
purge". (viii) §1's table violates CLAUDE.md's table-alignment rule.

**K. Unaccounted memory doubling.** Every materialize now holds an editor container AND a verify
container running the full editor engine (worse with A2's GUI stack). `parallel-editors.md`:
~0.5 GB each, concurrency is memory-bound, unbounded fan-out OOMs a small box — and §1(c)'s own
incident was RAM+swap exhaustion on a 4-core/7.7 GB box. Neither §4.6 nor §10 mentions it.

**L. Smaller, still real.** Fingerprint thrash when two projects alternate on one per-user warm
container (every acquire mismatches → reboot + teardown + 0.5 GB resident for 10 min; not on the
watch-list). `UED_IDLE_S`/lock keyed on `$UEDCLI_HOME` but the container name on `uid`, so two
sessions with different `UEDCLI_HOME` share one container with different locks. No "container
vanished mid-acquire" outcome in the gate §4.2 calls complete (should reboot, not exit 2). The
`pinned` branch is unreachable in v1 yet specified and tested. `--keep-build` mechanism must change
under §5.3's reorder (staging file already on host; `cp_out` source may be released) and nobody
unlinks staging on the verify-failure path → one stranded `.dx` per failed verify. `qualify_live_level`
becomes broken-not-dead if its two callees are deleted; `_FLUSH_FILLER_CMD`, `_COMPLETE_RE`,
`Driver.obj_dependencies/log_size/read_log_since` all lose their last caller. No docs items
anywhere: `docs/usage.md:12` ("no persistent session") is falsified for a USER-FACING doc,
`architecture.md` still describes the verify in the same ephemeral container, `commands.md` has no
`Editor.ExecCommandlet` entry, and the new stderr mode line is observable output. No `rationale/`
landing named for the many implementation choices.

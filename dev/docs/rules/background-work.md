# Background / long-running work

Anything started in the background and then waited on — integration
tests, an ephemeral editor spin-up, a `MAP REBUILD`, an `apply` — must
never be left on a single open-ended wait. The editor is crash-prone and
wedges *silently* (see `../unrealed/quirks.md` "Stability"), so a job that
should take ~100s can hang forever — and with no timeout you hang with it.

Wait *cheaply*, though — re-invoking the model to check costs a full
context read each time (full price once past the prompt cache's ~5-min
TTL), so do NOT poll on short model wake-ups:

- Run it as a tracked background job and let the harness re-invoke you the
  moment it exits — completion wakes you for free, so don't poll for it.
- Pair that with a LONG fallback timer (~20 min) that only fires if the
  job hangs and never reports. It's a hang-detector, not a progress check;
  a short timer just burns context reads waiting for an event that already
  wakes you. When it fires, investigate (liveness, logs) — don't extend.
- For live editor driving that isn't a tracked job, block inside ONE tool
  call with an until-loop that sleeps internally (internal sleeps are
  free) and returns on completion or at the timeout.

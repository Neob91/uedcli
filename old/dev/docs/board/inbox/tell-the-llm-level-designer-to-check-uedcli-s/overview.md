+++
priority = "p2"
kind = "chore"
summary = "Tell the LLM level-designer to CHECK UEDCLI'S EXIT CODE — a failed operation is easy to miss"
+++

# Tell the LLM level-designer to CHECK UEDCLI'S EXIT CODE — a failed operation is easy to miss

Raised by Andrzej 2026-07-26 after the three-level agent build run
(evidence: `dev/docs/spikes/levelbuild-friction/`). Agents repeatedly carried on after an
operation had failed, because they read the *output* rather than the *status*. Concretely
observed in that run:
- `substrate stub Endemia` fails with `Exiting due to error` and **exit 2** — correct
  signalling — but the actionable cause (`Can't find Function in file 'Function
  DeusEx.DeusExDecoration.BeginPlay'`) is separated from the terminal line by blank lines and an
  out-of-order `stubbing Endemia…` progress line, so eyeballing the tail suggests "it printed
  something, probably fine".
- The orchestrating session **itself misread a shell pipeline's exit status as uedcli's** and
  briefly reported a non-existent "exits 0 on failure" defect. `cmd | grep | tail` reports the
  LAST stage's status — `PIPESTATUS[0]`/`set -o pipefail` is needed, and every `2>&1 | tail`
  idiom in the docs' own examples is exposed to this.
- Agents habitually pipe uedcli through `| tail -N`, which is exactly the idiom that discards
  both the status and the earlier lines carrying the cause.
Where it belongs: `docs/usage.md` (a short "check the exit status, and how not to lose it
through a pipe" note) and the level-design guides that show piped invocations.
**Caveat that must be stated in the same note, or it teaches false confidence:** exit 0 is
NOT sufficient. In the same run `level materialize --no-verify` exited 0, printed
`materialized <path>`, and wrote a 23,126-byte runt with no light bake (correct build:
191,332 bytes) — see friction §1b. So the guidance is "a non-zero status always means it
failed; a zero status does not always mean it worked — check the artifact too."

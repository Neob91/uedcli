+++
priority = "p3"
kind = "owner-question"
summary = "`brush build --name` was a HARD rename to `--base-name` — no back-compat alias"
+++

# `brush build --name` was a HARD rename to `--base-name` — no back-compat alias

p3. Done 2026-07-12 per your rename directive. A cold reviewer flagged that this is a hard
break on an LLM-facing surface: any existing prompt/example using `brush build --name` now fails
with argparse "unrecognized arguments". Deliberately NOT aliased (you chose the clean break to push
the correct spelling into prompts). If LLM-prompt breakage bites, a hidden alias is ~1 line:
`add_argument("--name", dest="base_name", help=argparse.SUPPRESS)`. Decide keep-broken vs alias.

+++
priority = "p2"
kind = "unknown"
summary = "`config.toml paths` as a TOML list"
+++

# `config.toml paths` as a TOML list

(Andrzej-requested 2026-07-19). Accept
`paths` as a TOML array alongside today's colon-separated string, on both `~/.uedcli/config.toml`
`[games.*].paths` and project `uedcli.toml`. Reviewed spec:
`spec.md`. **Awaiting your call on the sub-choices** (all
recommended in the spec): accept-both-forms (not list-only); apply to both loaders; leave
`catalog`/`prefabs`/`maps` as single strings; headline benefit is a colon-containing POSIX dir
(Windows drive letters do NOT work on the Linux host — corrected in review). On confirmation this
goes to `board/to-build/` and the durable choice gets a `decisions.md` entry.

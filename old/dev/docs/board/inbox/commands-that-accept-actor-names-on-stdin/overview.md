+++
priority = "p2"
kind = "unknown"
summary = "Commands that accept actor names on STDIN (`-`) should ALSO accept them as positional args (2026-07-24)"
+++

# Commands that accept actor names on STDIN (`-`) should ALSO accept them as positional args (2026-07-24)

Every consuming/mutating verb that reads its target set from stdin via `-` should equally
take the same names directly on the command line, so `actor prop set Foo Bar Texture=…` works without a
`printf 'Foo\nBar' | ... -` dance. Revisits the current CLI convention that `-` is the SOLE names source,
mutually exclusive with CLI args (uedcli `CLAUDE.md`): positional names and `-` stay mutually exclusive
per-call, but a verb must offer BOTH intake modes, not stdin-only. Audit which consuming verbs are
currently stdin-only and add positional intake where missing. Andrzej flagged.

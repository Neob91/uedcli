+++
priority = "p3"
kind = "debug"
summary = "usability-nit leftover: upstream pipe errors flow downstream as data` — when an upstream verb in a `|` pipe fails and emits something to stdout (e.g"
+++

# usability-nit leftover: upstream pipe errors flow downstream as data` — when an upstream verb in a `|` pipe fails and emits something to stdout (e.g

usability-nit leftover: upstream pipe errors flow downstream as data` — when an upstream
verb in a `|` pipe fails and emits something to stdout (e.g. argparse usage), a downstream `- ` consumer
reads it as a name (`unknown brush 'usage'`). Our verbs send errors to stderr (so a clean pipe is
fine), so this bites mainly on argparse-usage-to-stdout or a partial producer. A robust
detect/annotate is fuzzy (heuristically recognizing "this stdin line is an error, not a name"). Needs
design — deferred from the 2026-07-19 nits batch. (Related: the scoped-error item above would reduce
the argparse-usage case.)

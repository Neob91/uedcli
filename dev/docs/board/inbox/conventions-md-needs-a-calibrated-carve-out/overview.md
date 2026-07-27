+++
priority = "p1"
kind = "owner-question"
summary = "`conventions.md` needs a calibrated carve-out for the THIRD stdin convention"
+++

# `conventions.md` needs a calibrated carve-out for the THIRD stdin convention

Ruled 2026-07-26 ("it's fine") and written into the catalog spec's decision 8, but
`direction/conventions.md` still says "Exactly TWO stdin conventions … never add a third", with a
third listed under Rejected — so two protected docs contradict each other until this lands. Proposed
addition (verbatim, awaiting a yes):

> **Calibrated exception — `classify set -` reads JSONL.** The asset catalog's `classify set` accepts a
> JSONL row set on stdin (`{ref, tags, description[, colors]}`), a THIRD `-` convention beside the
> name list and the T3D snippet. It is approved because a classification write carries per-item
> *fields*, which a bare name list cannot express, and because a per-ref process start (~0.3 s) would
> make classifying a corpus turn-bound. The two-convention rule's actual requirement — that `-` means
> exactly one thing *per verb* — still holds: within the catalog nouns `-` is a name list for
> `show`/`preview`/`classify unset` and JSONL for `classify set`. No further convention is added
> without the same explicit approval.

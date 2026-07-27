+++
priority = "p1"
kind = "implement"
summary = "Owner decision 2.9 is unbuilt: specs and plans never moved into item directories, so 22 item links still break on every stage change."
+++

# Finish the board migration — move specs and plans into item directories

**Owner decision 2.9 shipped as zero work.** It is the ruling that resolved the spec's *structural*
review finding, and the migration declared itself done without it.

```
$ ls dev/docs/specs | wc -l ; ls dev/docs/plans | wc -l
71
27
$ find dev/docs/board -name spec.md -o -name plan.md | wc -l
0
```

**Why it matters, concretely.** Items now write exactly the citations 2.9 exists to abolish — 16
`](../../../specs/…)` and 6 `](../../../plans/…)` links across item bodies. Every one breaks the
moment its item changes stage, which is the failure the slug rule was ruled to prevent.

**Two things must land in the SAME change**, or the second is silently lost:

1. The move itself, plus reshaping `_EPHEMERAL` in `uedcli/tests/test_doc_links.py` to
   `board/*/*/spec.md` and `plan.md`, exempt except under `to-build/`.
2. **Narrowing `CLAUDE.md`'s round-2 trigger.** It currently excludes all of `dev/docs/board/*`
   from "the artifact". The moment a spec lives under the board, editing it to resolve a round-1
   finding stops counting — and **every spec and plan review in the repo silently loses its round
   2**. Narrow it to `board/*/*/overview.md` and `board/*/*/questions/`.

Also outstanding here: `dev/docs/decisions.md` is FROZEN and carries two markdown links into
`dev/docs/specs/`, which removing that tree will redden. It cannot be edited, so those two links
need exempting in the link test instead.

Deferred deliberately after the item migration landed; not attempted.

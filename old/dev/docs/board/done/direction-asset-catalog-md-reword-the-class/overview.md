+++
priority = "p1"
kind = "owner-question"
summary = "direction/asset-catalog.md: reword the class-curation override clause to match the no-override ruling"
+++

# direction/asset-catalog.md: reword the class-curation clause

You ruled (§8.4, 2026-08-01): the class shard is `{kind, ref, tags, description}` — **no general
override field**; a wrong decoded fact is not correctable via an override. C3 is being built to that.

But `direction/asset-catalog.md` line 34 still says the opposite, and it's a `direction/` doc I can't
edit without your explicit yes on the exact text. Proposed one-line change:

**BEFORE (line 34):**

> Curation collapses to **a description, plus an override where the file fact is wrong.**

**AFTER:**

> Curation collapses to **tags plus a description**; the decoded file facts stand as read — there is
> no general override of a class's file fact. *(The texture-colours pre-fill below is the one
> exception, and it is texture-only.)*

This only aligns the doc with your ruling; it changes no behavior. The commit would carry a
`Confirmed: asset-catalog` trailer. Approve the wording, or edit it.

## Answer

<!-- owner: yes / edited wording -->

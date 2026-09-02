+++
priority = "p2"
kind = "chore"
summary = "The bulk conversion was a first pass: 481 of 492 summaries are the title verbatim, and several structural markers were dropped."
+++

# Board migration remnants

The mechanism is built and the items are all converted, but the *content* pass was mechanical.
Found by three cold reviewers over the finished migration.

**1. Summaries are not summaries.** 481 of 492 are the H1 copied verbatim; 94 exceed 110
characters and the longest is 418. The spec called authoring ~490 one-line summaries "the largest
hand-labour item here, **and the thing `bin/board ls` depends on**", and warned that titles
average 79 characters so a copy "will often not be enough to triage on". `bin/board ls` therefore
delivers none of the promised triage improvement — this is the change's stated payoff, unbuilt.

**2. Slugs were machine-truncated at 48 characters**, which spec §3.3 rejects by name. 285 of 492
are ≥40 chars. The worst (`inbox/done`, `inbox/authoring`, `to-spec/zones`,
`someday/all-parked-here`, `inbox/decision-needed`, `inbox/front-facing`) were repaired by hand;
the rest stand, and renaming is barred once referenced. Also `inbox/composable-actor-find-2`
collides with `to-plan/composable-actor-find` — the same work, given a `-2` suffix §3.3 forbids.

**3. Markers and structure dropped.** The 25 `[x]` and 13 `[~]` completion markers in the old
`board/done/` are gone, so "finished with remnants" is unrecoverable for all 95 done items. The 14 HTML
provenance banners were never converted to the specified one-line `**Provenance:**`; 12 survive raw,
glued to the *preceding* item, so a banner describing what follows it now sits inside something
unrelated. 25 items kept their two-space list-continuation indent.

**4. Three priorities were invented** from body prose, against migration rule 3 ("copied, never
invented"): `done/level-is-the-ambient-uedcli-level-target-tree`,
`done/the-second-name-suffix-mover-predicate…`, `inbox/de-containerization-follow-on-spec-items`.

**5. Three kind mis-mappings.** `[chore/flag]` and `[process/flag]` are on the spec's **chore** row,
but the classifier tests the owner word-set first and `flag` is in it, so they became
`owner-question`: `inbox/92-stage-0-done`, `inbox/build-2-feature-was-split-across-sessions`,
`inbox/build-4-cli-py-dispatch-py-hunks-were-again`.

**6. A title lost a code identifier.** The tag-stripping regex ate a bracketed symbol:
`to-spec/low-materialize-log-noise` reads `XGetWindowProperty failed (code=1)`; the original was
`XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)`.

**7. The inventory was never written.** The plan required one committed `inventory.tsv` per batch,
reviewed before any directory was created; the classification stayed implicit in the script. That
is the step that would have caught the text loss found afterwards.

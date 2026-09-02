# Zones v1 — what scope, and how much of the build-dependent half?

## Context

The authoring primitives for zones already exist: the `portal` surface flag (`brush build sheet
--flag portal` / `brush poly set --add-flag portal`), `ZoneInfo` placement via generic `actor build
DeusEx.ZoneInfo` + `actor add`, and zone properties via `actor prop set`. What is genuinely missing
is the build-dependent half — "which zone is this in?", the 64-zone cap, "is this region sealed?" —
which needs the built BSP zone tree. Native zone resolution is a known open bug (several
`board/inbox` items); the editor path is slow and crash-prone.

Options (detail in `spec.md`):

- **A — thin (recommended).** No new zone verbs. A `docs/leveldesign/` recipe + the offline-decidable
  `level doctor` checks (option C). Smallest surface; nothing blocked on the broken native path.
- **B — a `zone` verb family** (`zone list/place/show`). Sugar over existing verbs unless it reports
  built-zone membership, which is blocked on a working zone backend. Low value sugar-only.
- **C — doctor zone checks** (pairs with A): portal/region sanity offline; the 64-zone cap surfaced
  by the build step (it needs the count), not the offline doctor.

Sub-decisions if we go past A:
- Is a built-zone MEMBERSHIP query ("which zone is actor X in") in scope for v1, given it needs a
  working (editor or native) build? Recommend NO for v1 — gate it on native zone resolution landing.
- Where does the 64-zone-cap warning live — the build step (recommended, has the count) or a spike
  to make it offline-decidable?

## Answer

<!-- Empty = open. -->

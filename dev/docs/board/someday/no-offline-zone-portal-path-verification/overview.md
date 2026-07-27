+++
priority = "p3"
kind = "implement"
summary = "No offline ZONE / PORTAL / PATH verification — builds are \"author-complete but verify-blind\""
+++

# No offline ZONE / PORTAL / PATH verification — builds are "author-complete but verify-blind"

`doctor` has zero zone awareness: it can't confirm a portal actually seals two
regions into separate zones, that the portal covers the opening, that a leak didn't fuse the rooms
into zone 0, or that PathNodes are reachable. All resolve at build time only. An offline
zone/portal/reachability pass would close the biggest confidence gap for multi-room work. (Agent B.)

+++
priority = "p3"
kind = "chore"
summary = "FLAG: `to-build.md` and `inbox.md` both own the `xfer` timeout work, and one item schedules a function for deletion that another schedules for repair"
+++

# FLAG: `to-build.md` and `inbox.md` both own the `xfer` timeout work, and one item schedules a function for deletion that another schedules for repair

Not my change.
`to-build.md` says the inbox chore covers "only `driver.py`'s 8 calls + `xfer.remove`" and claims
`cp_in`/`cp_out` for itself, while the inbox entry (widened by the round-3 review) already covers
all three `xfer` subprocesses — `board/README.md` says one home per item. Separately `to-build.md`
lists `xfer.cp_in` among zero-caller dead code to DELETE while also scheduling it for a timeout
bound; whichever builder runs first invalidates the other. Also two `to-build.md` links point at
specs that are untracked (`2026-07-25-trunk-write-safety.md`,
`2026-07-25-decimal-map-coordinates.md`). (2026-07-25, round-4 cold reviews.)

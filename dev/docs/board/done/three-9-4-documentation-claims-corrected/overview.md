+++
priority = "p3"
kind = "chore"
summary = "Three #9.4 documentation claims corrected — `inbox.md` CLOSED 2026-07-25"
+++

# Three #9.4 documentation claims corrected — `inbox.md` CLOSED 2026-07-25

(a) `architecture.md` said a bare class name resolves as an OR ("a mover if ANY candidate
descends"); the code requires the candidates to AGREE and raises `ClassRefError` on a split.
(b) `docs/usage.md` listed `level materialize` and `level preview` among the verbs that ask the
mover question — neither does (only `level preview --native` reaches `_mover_index`); they need
the same config for an unrelated reason, now stated as such. (c) `decisions.md` 2026-07-25 10:18
UTC's "12 classes / four rejected" enumeration was re-measured against the real composed path
(**9** case-sensitive `*Mover` names, 12 only case-insensitively; **17** `Engine.Mover`
descendants; **8** real movers rejected by the old guess; **0** false positives) and corrected in
place with a dated note — the decision itself stands.

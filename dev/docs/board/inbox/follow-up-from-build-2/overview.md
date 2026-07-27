+++
priority = "p3"
kind = "owner-question"
summary = "follow-up from build #2 (--rotate vs --prop Rotation=)` — on `actor build`, passing BOTH `--rotate P,Y,R` and `--prop Rotation=…` silently resolves to the `--ro"
+++

# follow-up from build #2 (--rotate vs --prop Rotation=)` — on `actor build`, passing BOTH `--rotate P,Y,R` and `--prop Rotation=…` silently resolves to the `--ro

follow-up from build #2 (--rotate vs --prop Rotation=)` — on `actor build`, passing
BOTH `--rotate P,Y,R` and `--prop Rotation=…` silently resolves to the `--rotate` value (documented
as shorthand for the same field). Left permissive; say if you'd prefer a conflict error.

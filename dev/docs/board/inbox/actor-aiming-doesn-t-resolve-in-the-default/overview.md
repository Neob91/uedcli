+++
priority = "p2"
kind = "implement"
summary = "`@actor` aiming doesn't resolve in the DEFAULT `--native` preview"
+++

# `@actor` aiming doesn't resolve in the DEFAULT `--native` preview

`level preview
--native "look:@Room"` (and `at:@Room`) → `actor not found`; `@refs` resolve only in `--game --map`.
So the fast offline loop can't aim at your own geometry by name — raw coords only, made worse by the
suffix item above. Native should resolve `@refs` host-side against the trunk (thought `actor_aim_point`
did — live it did not; verify + fix). (My probe.)

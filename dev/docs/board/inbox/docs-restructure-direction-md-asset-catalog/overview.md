+++
priority = "p2"
kind = "chore"
summary = "Docs restructure: `direction.md` \"asset catalog\" content must NOT go to `to-spec.md`"
+++

# Docs restructure: `direction.md` "asset catalog" content must NOT go to `to-spec.md`

It is spec'd + planned + reviewed and sits on `to-build.md:48-52`; routing it
back would walk a reviewed item backwards, violating "an item lives in exactly ONE queue".
Re-verify every board destination against the board's real state.

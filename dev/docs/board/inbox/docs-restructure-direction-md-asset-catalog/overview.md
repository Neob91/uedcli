+++
priority = "p2"
kind = "chore"
summary = "Docs restructure: `direction.md` \"asset catalog\" content must NOT go to `board/to-spec/`"
+++

# Docs restructure: `direction.md` "asset catalog" content must NOT go to `board/to-spec/`

It is spec'd + planned + reviewed and sits in `board/to-build/`; routing it
back would walk a reviewed item backwards, violating "an item lives in exactly ONE queue".
Re-verify every board destination against the board's real state.

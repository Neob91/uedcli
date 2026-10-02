+++
priority = "p3"
kind = "chore"
summary = "`<repo>/Textures/` is only partly git-tracked, and that keeps biting the test design"
+++

# `<repo>/Textures/` is only partly git-tracked, and that keeps biting the test design

`git ls-files Textures/` lists four packages (`France.utx`, `LUM_CharacterTex.utx`,
`LUM_CoreTex.utx`, `LUM_InfoPortraits.utx` — 384 `Texture` exports); `CoreTexSky.utx` (1.7 MB) and
`CoreTexWater.utx` (172 KB) sit beside them **untracked** (34 more exports). Two drafts of the
native-texture-formats plan wrote "6 packages / 418 exports" into *offline* test expectations,
which would fail on a fresh checkout and drift here. Fixed in that plan with a count-stability rule
(exact counts only over `uned/UED22` + fixtures + the single tracked `LUM_CoreTex.utx`), but the
underlying question is yours: **should those two packages be committed, gitignored, or moved?** A
content directory that is half-tracked and live is a permanent trap for any corpus test.
*(A copy of `CoreTexWater.utx` is already committed as a test fixture under
`Tools/uedcli/uedcli/tests/fixtures/`, so at least that one is duplicated content.)*

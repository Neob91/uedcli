+++
priority = "p1"
kind = "debug"
summary = "bin/test is red on current master, before any new change: ~28 of 35 failures are test_board.py/test_doc_links.py fallout from f605547's board consolidation — items now live one level deeper (to-build/native-materialize/<slug>/) than the board schema tests expect (<stage>/<slug>/overview.md), so item-shape/frontmatter/slug-reference/dependency tests all fail. Either the tests learn the grouped layout or the layout changes; owner's consolidation ruling implies the former."
+++

# bin/test red on master: board schema tests broken by to-build/native-materialize consolidation

Hit 2026-09-02 running the full suite for the p_base round-15 change (whose own diff touches none of
these): `35 failed, 13086 passed`. The board-schema class (test_board.py `test_item_shape`,
`test_frontmatter`, `test_dependencies_resolve`, `test_slug_references_resolve`,
`test_no_dependency_cycles`; test_doc_links.py link checks) all trace to
`dev/docs/board/to-build/native-materialize/` holding ITEMS one directory deeper than the
`<stage>/<slug>/overview.md` shape the tests enforce. Reproduce: `bin/test -k "board or doc_links"`.
The remaining ~7 failures are a separate item (`test-csg-native-differential-passes-a-4-field`).

+++
priority = "p3"
kind = "chore"
summary = "`map_save` has no INTEGRATION test — the new accept rule has never run against a real editor"
+++

# `map_save` has no INTEGRATION test — the new accept rule has never run against a real editor

`test_driver.py` drives it against a fake container and a fake clock (thorough: every
branch is mutation-checked), and `test_real_packages_pass_the_completeness_check` feeds real `.u`/
`.dx` headers to the validator offline. What is unpinned is the round trip: that a live `MAP SAVE`
into the `dx-lum-uned` container is ACCEPTED by the four-signal rule, in the wall-clock the editor
really takes. It also newly depends on `stat -c '%s %.9Y'` and `od -An -v -tu1` existing in that
image (verified by hand 2026-07-25 — GNU coreutils 9.1 — but nothing re-checks it after an image
rebuild). `test_driver_integration.py` covers only `map_export`/`exec`; add an
`@pytest.mark.integration` save round-trip there. (2026-07-25, cold review of the `map_save`
change.)

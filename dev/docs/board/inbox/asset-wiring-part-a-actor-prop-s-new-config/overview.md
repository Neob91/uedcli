+++
priority = "p2"
kind = "owner-question"
summary = "Asset-wiring Part A: `actor prop`'s new config-error path has no regression test, and `_class_schema` still isn't project-threaded (Part B).** "
+++

# Asset-wiring Part A: `actor prop`'s new config-error path has no regression test, and `_class_schema` still isn't project-threaded (Part B).** 

Asset-wiring Part A: `actor prop`'s new config-error path has no
regression test, and `_class_schema` still isn't project-threaded (Part B).** p2. `dispatch._class_schema`
now resolves the project from cwd/env + loads the games config, so a present-but-broken config
(malformed TOML / ambiguous project / game named by the project but absent from the games config)
raises `config.ConfigError` mid-`actor prop` → caught by `dispatch()` → exit 2 (verified clean, no
traceback). But: (a) no offline test exercises it (the tests monkeypatch `_class_schema` as a
seam), which the tool's "cover each no-traceback path with a regression test" rule wants; and (b)
the invocation's `--project` flag is NOT threaded into schema resolution (it re-resolves from
cwd/env, keeping the 1-arg seam), so a `--project` override can't reach the schema path. Part B:
thread the resolved project down from the `actor prop` handler and add the regression test. Marked
in code with `# TODO(asset-wiring Part B)` (dispatch.py `_class_schema`).

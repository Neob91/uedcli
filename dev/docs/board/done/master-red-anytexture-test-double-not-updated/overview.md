+++
priority = "p2"
kind = "debug"
summary = "Done — `_AnyTexture` accepts the `class_index` kwarg `f89334b` started passing."
+++

# master red: `_AnyTexture` test double not updated for the `class_index` kwarg

Done. `f89334b` threaded the class index into `cli.ingest`'s `TextureResolver(...)` call but updated
only one of the two stubs; `test_import_verb.py`'s now takes the kwarg too. No other stub of
`TextureResolver` had the same gap.

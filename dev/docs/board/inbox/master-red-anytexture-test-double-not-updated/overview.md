+++
priority = "p2"
kind = "debug"
summary = "master red: test_import_verb's _AnyTexture stub takes one arg, but f89334b made the caller pass class_index=."
+++

# master red: `_AnyTexture` test double not updated for the `class_index` kwarg

`f89334b` (2026-08-05, the last code commit before the break) threaded the class index into ingest
texture validation:

```python
resolver = utexture.TextureResolver(files, class_index=class_index)   # uedcli/cli/ingest.py
```

`test_import_verb.py`'s `_AnyTexture` stub still declares `def __init__(self, _files)`, so both
`real_validation` tests fail with `TypeError: _AnyTexture.__init__() got an unexpected keyword
argument 'class_index'`. The commit updated `test_ingest_validation.py` but not this second stub.

Test-double drift only — the production path is correct and its own regression test passes. Fix is
one line (accept and ignore the kwarg), but confirm first that no other stub of `TextureResolver` has
the same gap.

Found 2026-08-22 running the full suite. Not fixed in that session: out of the approved scope.

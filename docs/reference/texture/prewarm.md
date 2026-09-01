# texture prewarm

`texture prewarm` decodes every texture on the path ahead of an offline session, so a later
list/show/search/classify starts with the ref→identity map warm. Progress goes to stderr.

```bash
uedcli texture prewarm [--package P]
```

- `--package P` warms only that package (bare stem).
- `--force` re-decodes even a texture already warmed this run (reserved; decode is per-invocation
  today).

See also: [`texture list`](list.md).

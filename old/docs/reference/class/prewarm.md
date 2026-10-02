# class prewarm

Building the class index and resolving property schemas decodes every `.u` on the path the first
time. `class prewarm` does that decode ahead of time and persists it, so a later **offline**
`class list` / `search` / `show` starts warm instead of cold.

```bash
uedcli class prewarm                    # warm every package on the path
uedcli class prewarm --package DeusEx    # just one package
uedcli class prewarm --force             # re-decode even entries that are already warm
```

- It warms the **package schema cache** (class discovery + property schemas). It does **not** render
  previews or resolve mesh facts — those have no persistent cache yet, so a cold `class preview` or
  `class show`'s extents still pay their own cost.
- Prints each warmed package stem to stdout, one per line, with a count on stderr. `--package P`
  warms only `P` (an unknown package **exits 2** naming it); `--force` re-decodes and rewrites each
  entry even when a valid one exists (the default fills only misses). With no composed package path
  it **exits 2** (`no package search path`).

See also: [`class list`](list.md).

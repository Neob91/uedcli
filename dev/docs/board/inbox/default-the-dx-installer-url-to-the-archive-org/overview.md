+++
priority = "p2"
kind = "implement"
summary = "Give dev/scripts/install-deusex-assets.sh a default --url pointing at the archive.org GOTY installer."
+++

# Default the DX installer `--url` to the archive.org GOTY setup

`dev/scripts/install-deusex-assets.sh` should default its `--url` to:

```
https://archive.org/download/deus_ex_goty_16231/setup_deus_ex_goty_1.112fm%28revision_1.3.0.1%29_%2816231%29.exe
```

**This reverses an explicit decision in the script's own header**, so whoever builds it must revise
that text rather than leave it contradicting the code:

> NO SOURCE IS BUILT IN. `--url` fetches whatever URL YOU pass and nothing else; there is no default,
> no bundled list, and no lookup. Deus Ex is a commercial game still sold today, so YOU are
> responsible for having the right to the copy you point this at […]

Two things to settle while building:

- **Does the default fire on bare `--url`, or when neither `<SOURCE>` nor `--url` is given?** Today
  those are mutually exclusive and exactly one is required; a default changes what "no arguments"
  means, which is the branch that currently prints the usage error.
- **Pin a `--sha256` alongside it.** The script already supports positional `--sha256` per URL and
  reports an unverified download as such. A built-in URL with no built-in checksum is the one
  combination that gets worse rather than better — it makes an unverified third-party download the
  path of least resistance.

`dev/docs/deusex-assets-setup.md` ("Where to get Deus Ex") also lists the options and needs the same
update.

+++
priority = "p2"
kind = "implement"
summary = "Give dev/scripts/install-deusex-assets.sh a default --url pointing at the archive.org GOTY installer."
+++

# Default the DX installer `--url` to the archive.org GOTY setup

Done. With neither `<SOURCE>` nor `--url`, the script uses `DEFAULT_URL` (the archive.org GOTY
installer) verified against the pinned `DEFAULT_SHA256`; the header records that it is an unofficial
redistribution and that the right to the copy is the operator's. Both open questions were settled:
the default fires on no-args (not on bare `--url`), and the checksum IS pinned.

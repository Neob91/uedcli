"""`docs list|show|search` — uedcli's own USER-facing documentation, served from the tool.

Read-only and fully offline: no project, no ambient level, no games config, no editor. Owns the
`UserDocsError` → `CommandError` translation (the service raises its own error rather than reaching
into the CLI boundary).
"""
from __future__ import annotations

import sys

from .. import targets as target_names
from ..errors import CommandError


def _doc_bytes(doc) -> bytes:
    """A served doc's raw bytes, or a clean exit-2 error naming the topic that could not be read.

    Raw bytes, deliberately: the docs contain UTF-8 typography (`°`, `×`, `≡`, `…`) and printing
    them through Python's text layer would re-encode them in whatever the terminal locale claims,
    corrupting the page under a non-UTF-8 locale. `sys.stdout.buffer` is a byte-for-byte copy.
    """
    try:
        return doc.path.read_bytes()
    except OSError as e:
        raise CommandError(f"cannot read doc {doc.key}: {e.strerror or e}") from None


def run(args) -> int:
    """`docs list|show|search` — uedcli's own USER-facing documentation, served from the tool.

    Read-only and fully offline: no project, no ambient level, no games config, no editor. It has
    to run in a bare checkout and in a bare install, so it must never trip the config/ingest gates
    the content verbs sit behind.

    The served tree is `docs/` (the CLI reference plus the level-design guides); the DEVELOPER
    tree (`dev/docs/**`) is never served — see `userdocs.py`, which owns the enumeration, the
    resolver order and the topic-key rules. All three sub-verbs share that ONE enumeration, so
    `show` resolves a topic by looking it up in the same served set `list` prints, never by
    joining user text onto a filesystem path.

    Output follows the house pipe conventions: data (topic keys, or a page's markdown) on stdout,
    the human count on stderr, `--json` where a caller wants structure. So
    `uedcli docs search lighting | uedcli docs show -` composes.
    """
    from ... import userdocs
    try:
        docs = userdocs.load_docs()
    except userdocs.UserDocsError as e:
        # This family owns the translation of the service's own error into the clean-exit-2
        # `CommandError` the central guard prints (completing the slice-2 reverse-import removal:
        # `userdocs` no longer reaches into the CLI boundary).
        raise CommandError(str(e)) from None

    if args.sub == "list":
        if getattr(args, "json", False):
            import json
            print(json.dumps([{"path": d.key, "title": d.title} for d in docs], indent=2))
        else:
            for d in docs:
                print(d.key)
        print(f"{len(docs)} topic(s)", file=sys.stderr)
        return 0

    if args.sub == "show":
        if args.topic == "-":
            # ATOMIC over the whole stdin set: resolve every key AND read every page before a
            # single byte reaches stdout. A partial dump plus a warning on stderr would be taken
            # for the complete answer once the warning scrolls away ("no silent half-answers").
            #
            # Reuses `targets.resolve_target_names`, the CLI's one newline-list-from-stdin reader, rather
            # than re-splitting here — it already drops blank lines and strips a leading UTF-8 BOM,
            # which `str.strip` does not (a BOM is not whitespace). Without it, a first line
            # written by a BOM-emitting producer failed to resolve and, because this form is
            # atomic, took the whole invocation down with it.
            wanted = target_names.resolve_target_names(["-"])
            if not wanted:
                return 0                      # empty stdin is a clean no-op, never an error
            resolved, missing = [], []
            for raw in wanted:
                if (doc := userdocs.find_doc(docs, raw)) is not None:
                    resolved.append(doc)
                else:
                    missing.append(userdocs.normalize_key(raw) or raw)
            if missing:
                raise CommandError("Docs not found: " + ", ".join(missing))
            chunks: list[bytes] = []
            for doc in resolved:
                # One marker line per page, BEFORE the page it names, so a consumer reading the
                # concatenated stream always knows which topic the following markdown belongs to.
                # It is a markdown comment, so the stream stays valid markdown.
                chunks.append(f"<!-- topic: {doc.key} -->\n".encode())
                body = _doc_bytes(doc)         # a read failure here must still print NOTHING …
                chunks.append(body)
                if body and not body.endswith(b"\n"):
                    chunks.append(b"\n")      # keep the next marker on a line of its own
            out = sys.stdout.buffer            # … so writing starts only once every page is in hand
            for chunk in chunks:
                out.write(chunk)
            out.flush()
            return 0
        if (doc := userdocs.find_doc(docs, args.topic)) is None:
            raise CommandError(userdocs.not_found_message(docs, args.topic))
        sys.stdout.buffer.write(_doc_bytes(doc))
        sys.stdout.buffer.flush()
        return 0

    if args.sub == "search":
        if not args.query.strip():
            # A blank substring is inside every line of every page, so it would "match" the whole
            # corpus in score order — a meaningless answer, not an empty one. Refuse it by name.
            raise CommandError("docs search: the query must not be empty")
        hits = userdocs.search(docs, args.query)
        if getattr(args, "json", False):
            import json
            print(json.dumps([{"path": h.doc.key, "title": h.doc.title, "snippet": h.snippet}
                              for h in hits], indent=2))
        else:
            for h in hits:
                print(h.doc.key)
        # Zero matches is a NORMAL outcome (rc 0) — stdout stays empty so a pipe into
        # `docs show -` is a clean no-op, and the count goes to stderr like every other query verb.
        print(f"{len(hits)} match(es)", file=sys.stderr)
        return 0

    raise CommandError(f"unimplemented docs sub-verb: {args.sub}")

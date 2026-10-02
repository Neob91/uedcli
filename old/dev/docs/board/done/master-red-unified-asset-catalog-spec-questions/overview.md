+++
priority = "p2"
kind = "debug"
summary = "Done — the deleted-doc check no longer false-positives on the item that reports it."
+++

# master red: unified-asset-catalog trips the deleted-doc check

Done. Both halves are resolved: the `test_markdown_links_resolve` dangling link was fixed with the
texture-arm edits, and the surviving `test_no_citation_of_a_deleted_doc` offender was this item
itself — it has to name the retired doc to describe the bug. It is now in `_MAY_NAME_DELETED`, the
same exemption `test_doc_links.py` already uses for itself.

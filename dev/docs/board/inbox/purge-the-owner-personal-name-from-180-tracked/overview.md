+++
priority = "p3"
kind = "chore"
summary = "The owner asked that their personal name not appear in any document; ~180 tracked files still carry it."
+++

# Purge the owner personal name from ~180 tracked files

**Owner instruction, 2026-07-27:** their personal first name is not to appear in any document. Use
"the owner" (and they/them) instead.

Done already in that session's change: `CLAUDE.md`, the root `README.md`, and the two owner-only
docs, which were renamed to `dev/docs/owner-notes.md` and
`dev/docs/2026-06-20-open-questions-for-owner.md` (content untouched — only the filenames changed,
and the six files citing the old paths were repointed).

**Still carrying the name — roughly 180 files.** Find them with
`grep -ril '<name>' --exclude-dir=.git .`. They fall into four groups, and the last two need a ruling
before anything is edited:

1. **Code comments** — `uedcli/dispatch.py` (3), `uedcli/native/materialize.py` (1),
   `uedcli/game/uscript/dxdriver/Classes/UedPreviewDeusExDriver.uc` (1). Mechanical; reword to "the
   owner". This is a code change, so it takes a **build** review row, not docs-only.
2. **`dev/docs/architecture.md`** and other live developer docs — mechanical reword.
3. **`dev/docs/decisions.md`** — the **frozen** retired ledger ("never append"). Rewriting names
   inside a frozen historical record may not be wanted. **Ask.**
4. **~170 board items** under `dev/docs/board/`, mostly `inbox/`. Two have the name **in their
   slug** (`andrzej-the-older-gate-contradiction-item-above`,
   `andrzej-the-two-claude-md-files-now-give`), and a slug is documented as permanent and never
   renamed (`dev/docs/board/README.md`) — `test_board.py` checks that every slug citation resolves,
   so renaming means finding and updating every reference. Several other items quote historical tag
   spellings such as `[FLAG-FOR-<name>]`, where the name **is** the quoted data. **Ask** whether
   historical board capture is in scope at all.

Sequence it as: groups 1 and 2 first (one batch, build review), then a ruling on 3 and 4.

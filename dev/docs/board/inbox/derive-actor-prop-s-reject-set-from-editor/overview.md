+++
priority = "p2"
kind = "unknown"
summary = "Derive `actor prop`'s reject set from editor-editability, not a hard-coded list"
+++

# Derive `actor prop`'s reject set from editor-editability, not a hard-coded list

Today `propedit.HARD_REJECT` is a hand-maintained deny-list (`name`, `brush`, `keypos`, `keyrot`,
`keynum`). Instead, block a prop when UnrealEd itself would not expose it as editable — the
principled source of truth. The schema decode already carries the signal: `Prop.property_flags`
(the `CPF_*` bits; the editor-edit flag is `0x1`) and `Prop.category` (`None` for a non-editable
plain `var`, set for an editable `var(Category)`). **Reconcile the two axes at spec time:**
editor-editability ≠ uedcli policy. Some editor-editable props are still uedcli-owned-elsewhere and
must stay blocked (`keynum` is editable but we canonicalize it to 0; check whether `name` carries
the edit flag), and `keypos`/`keyrot` are authored via `mover key` (verify they're non-editable so
the gate blocks them for free). So the likely shape is "not editor-editable → block" PLUS a small
explicit policy set for editable-but-uedcli-managed props. Consistent with the 2026-07-20 16:18
decision that `NumKeys` (editor-editable) is settable. Ref: `propedit.HARD_REJECT`, `uprops.Prop`.

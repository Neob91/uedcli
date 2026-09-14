+++
priority = "p2"
kind = "implement"
summary = "uscript: cross-package struct type not resolved (var IpAddr X) - FIXED"
+++

# uscript: cross-package struct type not resolved (var IpAddr X) - FIXED

Fixed: `compile._resolve_var_type` (member-var declarations) was the one type-resolution site missing
the cross-package-struct branch `_func_prop_type`/`_resolve_array_type` already had (`_member_graph(b)
.is_struct_name(base)` + `_add_struct_import`) - added, mirroring those two exactly. Regression:
`UscIpAddrProbe` (`uedcli/tests/fixtures/uscript/ut99/UscIpAddrProbe/`, `test_uscript_ut99.py`), a
member var AND a function param both typed to `IpDrv.InternetLink.IpAddr`, verified `perm_gate`
byte-exact against a fresh live UT99 UCC build.

Real `IpServer` is still NOT a corpus win: past this gap it hits two further, NEW, NOT-small gaps
(`uscript-cross-package-import-identity-collides/`, `uscript-struct-member-access-confuses-a-local/`),
scoped out per this session's one-small-follow-on-fix cap.

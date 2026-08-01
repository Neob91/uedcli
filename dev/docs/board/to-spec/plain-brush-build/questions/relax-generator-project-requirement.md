# Should a plain `brush build` (fixed `Engine.Brush`, no texture/prop/mover-class) run with no games config?

## Context

`direction/generators.md` deliberately makes every generator project-dependent: "'Stateless' means no
level and no session — not 'no project' … it needs a resolvable project and package path and exits 2
without one", and explicitly rejects validating only at the write boundaries, "accepting that this
makes them project-dependent."

The finding: for a *plain* `brush build` (class is the hardcoded `Engine.Brush`, no `--texture`, no
`--prop`, no `--mover-class`) the ingest gate resolves nothing substrate-specific — `Engine.Brush`
always exists and the texture loop is skipped — so the gate can only ever pass, yet it still exits 2
when `~/.uedcli/config.toml` is absent. A user who just wants `brush build cube >shape.t3d` is blocked
on config that buys no validation.

Stakes: a small friction win on the most basic generator vs a carve-out in a rule the owner set on
purpose (uniform "generators are checked, hence project-dependent"). The relaxation is narrow — the
moment any of `--texture`/`--prop`/`--mover-class` appears, there is a real class/texture/schema to
resolve and the config requirement stands.

Options:

- **A — Keep the rule as written.** Plain `brush build` still requires a project/config, for one
  uniform generator contract and no special case. Costs the friction above.
- **B — Relax for the zero-validation case only.** Skip the gate when the class is the fixed
  `Engine.Brush` and there is no `--texture`/`--prop`/`--mover-class`; requires editing
  `direction/generators.md` to carve this out.

If B, the exact `direction/generators.md` wording change is needed too (this question is also the
place to approve that text).

Recommendation: **B** — the gate provably cannot fail in this case, so requiring config is friction
with no validation value; the carve-out is precisely bounded by "nothing substrate-specific named".
But it is your rule to change.

## Answer

<!-- Empty = open. -->

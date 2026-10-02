"""Parser registrars: one module per top-level command family, plus the
private `_arguments` module of shared argument types, converters and flags.
Only `cli.main` imports this tier; a registrar imports within `cli.parsers`
and lower services, never another `cli` module."""

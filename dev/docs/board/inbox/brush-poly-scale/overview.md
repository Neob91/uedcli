+++
priority = "p2"
kind = "unknown"
summary = "`brush poly scale` — the fourth canonical surface op, still missing"
+++

# `brush poly scale` — the fourth canonical surface op, still missing

Pan, rotate
and align are specced (board item `the-per-surface-verb-split`); scale is deliberately NOT, because
it interacts with how `align --run` derives texel density from the seed frame (by projection onto
the run tangent/across directions), and speccing it blind would duplicate or contradict that. Needs
its own spec once `--run` lands. (Supersedes the "fold in `texture scale`/`texture rotate`" clause on
`board/to-spec/`'s texture-alignment item — rotate is now specced under its real name, `brush poly
rotate`; only scale remains.)

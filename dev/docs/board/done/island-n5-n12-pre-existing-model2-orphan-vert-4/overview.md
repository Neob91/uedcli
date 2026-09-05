+++
priority = "p3"
kind = "debug"
summary = "CORRECTION: my 2026-09-05 'false alarm, Island N1-16 byte-exact' disproof was itself invalid -- built on the same corrupted/truncated cached trunk as the original report. See corrupt-trunk-cache-silently-passes-the-ladder for the real root cause."
+++

# Both the original finding AND my "false alarm" disproof were built on a corrupted trunk

An isolated-worktree agent originally reported Island (`01_nyc_unatcoisland`) N5-N12 failing with a +4
world-`Model2` orphan-vert overcount. I (the coordinator) "disproved" this the same day by rebuilding a
fresh editor ref for Island N8 in the main worktree and getting `PARITY: YES`, and declared "Island
N1-16 are byte-exact."

**That disproof was wrong.** Found 2026-09-05 (later the same day, by a different isolated agent doing
forward-ladder work): the cached Island trunk in multiple worktrees -- including the one I used for my
"fresh" rebuild -- was silently TRUNCATED to 102 actors starting at `PathNode838`, missing `LevelInfo`
and every brush. A correct extraction gives 3653 actors starting `LevelInfo0, Brush296, ...` (confirmed
by two independent extractions). Every N-actor subset built from the bad trunk was pathnodes/weapons
over an EMPTY WORLD, so of course native and a "fresh" editor ref agreed -- there was no real geometry
for either side to diverge on. My rebuild reused the same corrupted cached extraction (`actor_parity.py`
only re-extracts when its completeness check fails, and a truncated-but-well-formed trunk passes that
check), so it proved nothing.

**Both the original +4 orphan-vert report and my disproof are therefore VOID** -- neither was measuring
real Island geometry. The root cause (a corrupted trunk extraction cache that silently passes the ladder
instead of erroring) is tracked separately: `corrupt-trunk-cache-silently-passes-the-ladder`. With the
CORRECT 3653-actor trunk, Island's real parity ceiling as of 2026-09-05 is N=1..4 byte-exact, bailing at
N=5 on a real (ULP-class) residual -- see that board item and `NATIVE-MATERIALIZE.md` for current state.

Lesson (sharper than the one this item originally recorded): a "fresh rebuild disproves it" check is
only as good as the trunk it rebuilds from. Verify the TRUNK's actor count/content against the level's
known scale (thousands of actors, not ~100) before trusting either a failing OR a passing gate result.

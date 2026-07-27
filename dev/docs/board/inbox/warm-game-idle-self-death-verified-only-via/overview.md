+++
priority = "p3"
kind = "debug"
summary = "Warm `--game`: idle self-death verified only via a backdated marker, not a real 10-min wall-clock idle"
+++

# Warm `--game`: idle self-death verified only via a backdated marker, not a real 10-min wall-clock idle

The watchdog loop + kill path are confirmed (backdate `/work/.last_use`
700s → self-terminates in ≤60s), but a true unattended 10-min idle wasn't timed. Low risk (the
mtime math is trivial); flag only if a container is ever seen lingering.

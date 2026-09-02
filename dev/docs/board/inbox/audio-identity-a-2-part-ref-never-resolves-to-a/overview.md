+++
priority = "p3"
kind = "unknown"
summary = "Audio identity: a 2-part ref never resolves to a 3-part identity (plan A3 wording)"
+++

# Audio identity: a 2-part ref never resolves to a 3-part identity (plan A3 wording)

Filed during the audio-arm build (`sound-corpus-remeasure`). Not a code bug — an impossible test
bullet in the plan, resolved by the coherent interpretation. No action needed unless the reviewer
disagrees.

Plan A3 (and the spec) set the collision rule: identity = `Package.Name` when the bare name is
**unique** within its package, else the full dotted `Package.Group.Name`. Plan A3's test list then
says: *"a supplied 2-part ref resolves (mocked audio_index) to a stored 3-part identity and back"*.

Under the collision rule a 2-part ref can never UNAMBIGUOUSLY resolve to a 3-part identity: a 3-part
identity exists only because the bare name collides across groups, and a collided bare name is
exactly the case where the 2-part `Package.Name` is ambiguous. So the two directions that are
coherent and implemented/tested are:

- **3-part dotted ref → 2-part identity** (a unique bare name that happens to sit in a group): the
  ref printed by `list` is `Package.Group.Name`, its shard key is `Package.Name`.
- **2-part ref → 2-part identity** (the unique case), and **3-part dotted ref → 3-part identity**
  (the collided case).
- A **2-part ref whose bare name collided → exit 2 (ambiguous)**, naming it and listing the
  candidates; the full dotted ref is required.

`audioindex.AudioIndex.resolve` implements exactly this (`test_audioindex.py` pins all four). The
"2-part → 3-part" bullet is dropped as impossible; nothing else in the plan depends on it.

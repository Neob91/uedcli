# Does `--faces world` reuse `level preview --native`, or does `level preview` grow an actor-set input?

## Context

`level preview --native` already does native CSG solve → textured surface render over a level. The
world mode needs the same over an ad-hoc actor set (including `--from-t3d` snippets). Two shapes:
(a) `actor preview --faces world` calls the shared native render path, re-targeted at the actor set;
(b) instead extend `level preview` to accept an actor-set/stdin input and treat `actor preview
--faces world` as sugar over it. (a) keeps the two verbs' current split; (b) unifies the world
renderer under one verb. Overlaps board items `level-preview-native-*`. Recommend (a) unless the
duplication is large once measured.

## Answer

<!-- Empty = open. -->

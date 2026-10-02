"""Runtime-dumped tie-break order for `ordering.order_package`.

`SavePackage` sorts the name/import tables `msvc_qsort`-descending by reference count; count-TIED
entries fall to the gather order = the engine's global FName / GObjObjects registration index (see
`ordering.py`). That index is a UED22 boot+load artifact, not derivable from the source under
compilation. It is DUMPED from a booted `UCC.exe` and shipped as per-substrate data:

  data/gobjnames_ued22.json    — GObjNames strings in ascending global index (name tie-break gather)
  data/gobjobjects_ued22.json  — GObjObjects [name, class, outer] in ascending index (import gather)

Dump method (recorded in each file's `_doc` and reproducible via the board harness `dump_gobj.py`):
winedbg plants an INT3 at SavePackage (core.dll fixed base 0x10000000, no ASLR) during `UCC make` of
a trivial class, then walks GObjNames (@0x10139d50) / GObjObjects (@0x1013a260) by index. Feeding
these through the real `order_package` reproduces the name AND import tables of every fixture
byte-exact (UscVars name + UscBB import — the former residuals — included).

Both maps give RELATIVE order only (lower index = earlier), casefolded (FName is case-insensitive).
A name/object absent sorts after all present — correct for a package's own new symbols, which
register last, after everything in the dumped pool.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from .ordering import GlobalIndex

_DATA = Path(__file__).resolve().parent / "data"


@cache
def _dumped() -> GlobalIndex:
    names = json.loads((_DATA / "gobjnames_ued22.json").read_text())["names"]
    objects = json.loads((_DATA / "gobjobjects_ued22.json").read_text())["objects"]
    name_idx: dict[str, int] = {}
    for i, n in enumerate(names):
        name_idx.setdefault(n.casefold(), i)
    obj_idx: dict[str, int] = {}
    for i, (nm, _cls, _outer) in enumerate(objects):
        if nm is not None:
            obj_idx.setdefault(nm.casefold(), i)
    return GlobalIndex(names=name_idx, objects=obj_idx)


def default_global_index() -> GlobalIndex:
    """The runtime-dumped `GlobalIndex` for `order_package`'s name/import tie-break (casefolded)."""
    return _dumped()


@cache
def _pool_case() -> dict[str, str]:
    names = json.loads((_DATA / "gobjnames_ued22.json").read_text())["names"]
    out: dict[str, str] = {}
    for n in names:
        out.setdefault(n.casefold(), n)
    return out


def pool_case(name: str) -> str:
    """The canonical FName spelling for `name` from the dumped global name pool (UE1 FName is
    case-insensitive but case-preserving, and the editor spells a pooled name from its boot pool, not
    the source — e.g. a member `a` becomes `A`). A name not in the pool keeps its source spelling."""
    return _pool_case().get(name.casefold(), name)


# ── engine boot global name pool (RF_Native FNames) ───────────────────────────────────────────────
# A name-table entry carries flag 0x04000000 (RF_Native) iff its FName was registered as a native
# name during engine boot — NOT merely because it appears in some package. That pool is:
#
#   (a) the hardcoded C++ name table (`RegisterNames()` / AUTO_REGISTER_NAME), extracted from
#       `core.dll`'s wide-string block right after `FName::StaticInit` (starts at `ByteProperty`,
#       runs through the gameplay probe names) — 268 names incl. operator/Inventory names like `Add`
#       and `Tag` that appear in NO stock `.u` name table; PLUS
#   (b) every name flagged RF_Native in any stock `uned/UED22/*.u` name table — the engine/editor/game
#       intrinsics registered by Engine.dll/Editor.dll etc. that (a) misses (e.g. `TakeDamage`,
#       `PostBeginPlay`), captured wherever a stock package references them.
#
# The naive "union of all stock name STRINGS" is WRONG: it over-includes package-created names such as
# `ScriptText` and `ReturnValue` (present in Core.u but NOT RF_Native → unflagged in the goldens).
# Union of (a)+(b) reproduces the name-table flags of every committed golden byte-exact (verified in
# test_uscript_permgate). Regenerate by re-running the two extractions above over the substrate.
ENGINE_NAME_POOL: frozenset[str] = frozenset({
    'abstract', 'accept', 'acceptinventory', 'actorentered', 'actorleaving', 'add', 'advanced',
    'all', 'alterdestination', 'always', 'animend', 'array', 'arraycount', 'arrayproperty',
    'assert', 'attach', 'auto', 'basechange', 'begin', 'beginevent', 'beginplay', 'beginstate',
    'bkillvelocity', 'black', 'blue', 'bool', 'boolproperty', 'botdesireability', 'break',
    'broadcastlocalizedmessage', 'broadcastmessage', 'build', 'bump', 'byte', 'byteproperty',
    'camera', 'case', 'checkclienterror', 'class', 'classproperty', 'clienthearsound',
    'clientmessage', 'clienttravel', 'cmd', 'coerce', 'color', 'colors', 'compatibility',
    'config', 'connectfailure', 'console', 'const', 'continue', 'coords', 'core', 'critical',
    'cyan', 'default', 'defaultcolor', 'demoplaysound', 'dependson', 'destroyed', 'detach',
    'detailchange', 'dev', 'devaudio', 'devbind', 'devcompile', 'devgarbage', 'devgraphics',
    'devkill', 'devload', 'devmd5', 'devmusic', 'devnet', 'devnettraffic', 'devpath',
    'devphysics', 'devreplace', 'devsave', 'devsound', 'die', 'display', 'do', 'drivers',
    'editconst', 'editor', 'else', 'encroachedby', 'encroachingon', 'endedrotation', 'endevent',
    'endstate', 'enemynotvisible', 'engine', 'enum', 'enumcount', 'error', 'event', 'exec',
    'execwarning', 'exit', 'expands', 'expired', 'export', 'exporter', 'extends', 'factory',
    'falling', 'felloutofworld', 'field', 'final', 'find', 'firetexture', 'fixedarrayproperty',
    'float', 'floatproperty', 'footzonechange', 'for', 'forcegenerate', 'foreach',
    'friendlyerror', 'from', 'function', 'gainedchild', 'gameending', 'generate',
    'getbeacontext', 'global', 'globalconfig', 'goto', 'green', 'grid', 'guid', 'heading',
    'headzonechange', 'hearnoise', 'hitwall', 'icetexture', 'if', 'ignores', 'import', 'init',
    'initgame', 'initialstate', 'input', 'insert', 'int', 'interpolateend', 'intproperty',
    'intrinsic', 'invariant', 'iterator', 'keyevent', 'keytype', 'kickedclasses', 'kicker',
    'kickvelocity', 'killcredit', 'killedby', 'landed', 'latent', 'length', 'linker',
    'linkerload', 'linkersave', 'local', 'localization', 'localized', 'log', 'loggamespecial',
    'loggamespecial2', 'login', 'longfall', 'lostchild', 'magenta', 'main', 'map',
    'mapproperty', 'mayfall', 'md5utils', 'message', 'name', 'nameproperty', 'native',
    'nativereplication', 'netcomego', 'new', 'noexport', 'none', 'notifylevelchange',
    'nousercreate', 'object', 'objectproperty', 'operator', 'optional', 'options', 'out',
    'outer', 'package', 'paintimer', 'parent', 'perobjectconfig', 'plane', 'play',
    'playercalcview', 'playercalcviewex', 'playerinput', 'playertick', 'playertimeout',
    'pointer', 'possess', 'postbeginplay', 'postlogin', 'postnetbeginplay', 'postoperator',
    'postrender', 'postteleport', 'posttouch', 'prebeginplay', 'preclienttravel', 'prelogin',
    'preoperator', 'prerender', 'preteleport', 'private', 'probe34', 'probe39', 'probe4',
    'probe48', 'probe49', 'probe5', 'probe50', 'probe51', 'probe52', 'probe53', 'probe54',
    'probe55', 'probe56', 'probe57', 'probe58', 'probe59', 'probe60', 'probe61', 'probe62',
    'property', 'receivelocalizedmessage', 'red', 'reliable', 'remoterole', 'remove',
    'renderoverlays', 'rendertexture', 'replication', 'return', 'role', 'rot', 'rotationgrid',
    'rotator', 'rotatorproperty', 'safereplace', 'scriptlog', 'scriptwarning', 'sdldrv',
    'seefriend', 'seemonster', 'seeplayer', 'self', 'sendbinary', 'sendtext', 'servertravel',
    'setinitialstate', 'settings', 'showupgrademenu', 'simulated', 'singular', 'skip', 'sound',
    'spawn', 'spawned', 'spawnnotification', 'specialcost', 'specialhandling', 'speechtimer',
    'stacknode', 'state', 'static', 'stop', 'string', 'stringproperty', 'strproperty', 'struct',
    'structproperty', 'subheading', 'subsystem', 'super', 'switch', 'system', 'tag',
    'takedamage', 'teammessage', 'textbuffer', 'textbufferfactory', 'texture', 'tick', 'timer',
    'title', 'touch', 'travel', 'travelpostaccept', 'travelpreaccept', 'trigger', 'unpossess',
    'unrealshare', 'unreliable', 'until', 'untouch', 'untrigger', 'update', 'updateeyeheight',
    'updatetactics', 'user', 'userprompt', 'utrace', 'var', 'vect', 'vector', 'vectorproperty',
    'videochange', 'walktexture', 'warning', 'watertexture', 'wavetexture', 'wettexture',
    'while', 'white', 'windrv', 'within', 'write', 'yellow', 'zonechange',
})


def engine_name_pool() -> frozenset[str]:
    """Casefolded names in the engine boot global name pool (RF_Native FNames). A compiled name-table
    entry gets the 0x04000000 flag iff its casefolded name is in here. See `ENGINE_NAME_POOL`."""
    return ENGINE_NAME_POOL


# ── RF_HighlightName (0x400) pool ─────────────────────────────────────────────────────────────────
# A name-table entry carries flag 0x400 (RF_HighlightName — the editor highlights it) iff its FName is
# a reserved keyword or an intrinsic type/struct name. Derived as the union of every name flagged
# 0x400 across the stock `uned/UED22/*.u` name tables (30 names — the UnrealScript keyword + built-in
# type set). Data-driven so Struct/Enum/Const/State/type-names all get it correctly.
HIGHLIGHT_NAME_POOL: frozenset[str] = frozenset({
    "auto", "class", "color", "const", "coords", "enum", "event", "from", "function", "global",
    "guid", "input", "iterator", "name", "none", "out", "outer", "package", "plane", "rot",
    "rotator", "spawn", "state", "static", "stop", "string", "struct", "switch", "vect", "vector",
})


def highlight_name_pool() -> frozenset[str]:
    """Casefolded names carrying the 0x400 (RF_HighlightName) name-table flag — keywords + intrinsic
    type/struct names. See `HIGHLIGHT_NAME_POOL`."""
    return HIGHLIGHT_NAME_POOL

"""`#exec CONVERSATION IMPORT FILE="X.Con"` — the byte-exact emitter for Deus Ex conversations.

The directive does NOT add objects to the class package `P.u`. The original Ion Storm Editor.dll
handler auto-creates SIBLING packages next to it (reverse-engineered against the DX UCC golden,
`reference_dxorig`):

  - `<P>Text.u`      — the conversation object graph (Conversation / ConEvent* / ConSpeech /
                        ConChoice / ConFlagRef + the mission scaffolding), instances of `ConSys`
                        classes stored as tagged-property objects.
  - `<P>Audio<A>.u`  — a single empty `ConAudioList` stub, where `<A>` is the `.con`'s
                        audioPackageName.

`parse_con` decodes the `.con` binary (format per the ConEdit `ConFile.Reader.pas`/`.Writer.pas`);
`build_conversation_packages` builds the two sibling `CompiledPackage`s. The object property SCHEMAS
(field order + type) are read from `ConSys.u` on the search path, so tags match the class layout.

Parity oracle: `gate.perm_gate` (identity/permutation), byte-exact modulo the documented exclusions
(package GUID, table order, FName case). Verified against fresh DX-UCC builds for the Minimal golden
and a comprehensive `.con` (every writable event type).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from ..native.actor_write import (PT_BOOL, PT_BYTE, PT_INT, PT_NAME, PT_OBJECT, PT_STR, Prop,
                                   write_props)
from ..upackage import Package, read_compact_index as _rci
from ..uprops.base import PROPERTY_TYPES
from ..uprops.ufield import _decode_property, _field_next
from .env import InstallEnv
from .global_index import engine_name_pool, highlight_name_pool
from .model import CompiledPackage, Export, Import, Name, ObjectBody
from .natives import prop_type_label

_CON_HEADER = b"Deus Ex Conversation File\x1a"   # 26 bytes

# ObjectFlags (RE'd vs DX UCC golden): most objects RF_Public|LoadFor* = 0x70004; the container
# "list" objects add RF_Standalone (0x80000).
_RF_OBJECT = 0x00070004
_RF_STANDALONE = 0x000F0004

# ── .con event type ordinal → ConSys ConEvent subclass (EEventType, verified identical) ────────────
_EVENT_CLASS = {
    0: "ConEventSpeech", 1: "ConEventChoice", 2: "ConEventSetFlag", 3: "ConEventCheckFlag",
    4: "ConEventCheckObject", 5: "ConEventTransferObject", 6: "ConEventMoveCamera",
    7: "ConEventAnimation", 8: "ConEventTrade", 9: "ConEventJump", 10: "ConEventRandomLabel",
    11: "ConEventTrigger", 12: "ConEventAddGoal", 13: "ConEventAddNote", 14: "ConEventAddSkillPoints",
    15: "ConEventAddCredits", 16: "ConEventCheckPersona", 17: "ConEventComment", 18: "ConEventEnd",
}


# ══ parsed .con model ═════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True, kw_only=True)
class ConFlagEntry:
    name: str
    value: bool          # the .con stores -1 (true) / 0 (false) as a 4-byte LongBool


@dataclass(frozen=True, kw_only=True)
class ConChoiceEntry:
    text: str
    label: str
    display_as_speech: bool
    mp3: str
    skill: int           # -1 = no skill required
    skill_name: str
    skill_level: int
    flags: tuple[ConFlagEntry, ...]


@dataclass(frozen=True, kw_only=True)
class ConEvent:
    kind: str            # ConSys class name (from _EVENT_CLASS)
    label: str
    payload: dict        # type-specific fields, keyed as documented in `_parse_event`


@dataclass(frozen=True, kw_only=True)
class ConConversation:
    id: int
    con_name: str
    description: str
    owner_name: str
    b_data_link: bool
    notes: str
    bools: dict          # display_once/first_person/... -> bool (Conversation bool fields)
    invoke_radius: int
    flag_refs: tuple[ConFlagEntry, ...]
    events: tuple[ConEvent, ...]


@dataclass(frozen=True, kw_only=True)
class ConFile:
    version: int
    audio_package: str
    notes: str
    missions: tuple[int, ...]
    conversations: tuple[ConConversation, ...]


# ── the .con binary reader (little-endian; ConFile.Reader.pas) ────────────────────────────────────
class _Reader:
    def __init__(self, data: bytes) -> None:
        self.b = data
        self.p = 0

    def _need(self, n: int) -> None:
        if self.p + n > len(self.b):
            raise ValueError(f".con truncated: need {n} bytes at offset {self.p} "
                             f"(size {len(self.b)})")

    def i(self) -> int:
        self._need(4)
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def d(self) -> float:
        self._need(8)
        self.p += 8                                  # a double date — read and discarded
        return 0.0

    def s(self) -> str:
        n = self.i()
        if n == 0:
            return ""
        if n < 0:
            raise ValueError(f".con bad string length {n} at offset {self.p}")
        self._need(n)
        v = self.b[self.p:self.p + n].decode("latin-1")
        self.p += n
        return v

    def lb(self) -> bool:
        return self.i() != 0


_CONV_BOOLS = ("display_once", "first_person", "non_interact", "random_camera", "can_interrupt",
               "cannot_interrupt", "invoke_bump", "invoke_frob", "invoke_sight", "invoke_radius")


def parse_con(data: bytes) -> ConFile:
    """Decode a `.con` file to a `ConFile`. Raises `ValueError` on a bad header/overrun."""
    if data[:26] != _CON_HEADER:
        raise ValueError(f"not a Deus Ex .con file (bad 26-byte header: {data[:26]!r})")
    r = _Reader(data)
    r.p = 26
    version = r.i()
    r.d(); r.s(); r.d(); r.s()                        # created/modified dates + names (discarded)
    audio_package = r.s()
    notes = r.s()
    missions = tuple(r.i() for _ in range(r.i()))
    _tables_size = r.i()
    for _ in range(4):                               # Actors / Flags / Skills / Objects tables
        for _ in range(r.i()):
            r.i(); r.s()
    r.i()                                            # unknown4 (== numConversations)
    conversations = tuple(_parse_conversation(r) for _ in range(r.i()))
    return ConFile(version=version, audio_package=audio_package, notes=notes, missions=missions,
                   conversations=conversations)


def _parse_conversation(r: _Reader) -> ConConversation:
    r.i()                                            # unknown0 (== event count)
    cid = r.i()
    con_name = r.s()
    description = r.s()
    r.d(); r.s(); r.d(); r.s()                        # created/modified
    r.i()                                            # ownerIndex
    owner_name = r.s()
    b_data_link = r.lb()
    notes = r.s()
    bools = {name: r.lb() for name in _CONV_BOOLS}
    invoke_radius = r.i()
    flag_refs = tuple(_parse_flagref(r) for _ in range(r.i()))
    events = tuple(_parse_event(r) for _ in range(r.i()))
    return ConConversation(id=cid, con_name=con_name, description=description, owner_name=owner_name,
                           b_data_link=b_data_link, notes=notes, bools=bools,
                           invoke_radius=invoke_radius, flag_refs=flag_refs, events=events)


def _parse_flagref(r: _Reader) -> ConFlagEntry:
    r.i()                                            # flagIndex (recomputed by name at load)
    name = r.s()
    value = r.lb()
    r.i()                                            # expiration (unused)
    return ConFlagEntry(name=name, value=value)


def _parse_event(r: _Reader) -> ConEvent:
    r.i()                                            # eventIdx
    r.i()                                            # unknown1
    etype = r.i()
    label = r.s()
    kind = _EVENT_CLASS.get(etype)
    if kind is None:
        raise ValueError(f"unknown .con event type {etype}")
    payload: dict = {}
    match etype:
        case 0:                                      # Speech
            r.i(); payload["speaker"] = r.s()
            r.i(); payload["speaking_to"] = r.s()
            payload["text"] = r.s()
            payload["mp3"] = r.s()
            payload["continued"] = r.lb()
            payload["bold"] = r.lb()
            payload["font"] = r.i()
        case 1:                                      # Choice
            payload["unk0"] = r.i()
            payload["clear_screen"] = r.lb()
            payload["choices"] = tuple(_parse_choice(r) for _ in range(r.i()))
        case 2:                                      # SetFlag
            payload["flags"] = tuple(_parse_flagref(r) for _ in range(r.i()))
        case 3:                                      # CheckFlag
            payload["flags"] = tuple(_parse_flagref(r) for _ in range(r.i()))
            payload["goto_label"] = r.s()
        case 4:                                      # CheckObject
            r.i(); payload["object"] = r.s()
            payload["fail_label"] = r.s()
        case 5:                                      # TransferObject
            r.i(); payload["object"] = r.s()
            payload["count"] = r.i()
            r.i(); payload["from_name"] = r.s()
            r.i(); payload["to_name"] = r.s()
            payload["fail_label"] = r.s()
        case 6:                                      # MoveCamera
            payload["camera_type"] = r.i()
            payload["camera_position"] = r.i()
            payload["camera_transition"] = r.i()     # editor writes -1 (byte 255)
        case 7:                                      # Animation
            r.i(); payload["owner"] = r.s()
            payload["sequence"] = r.s()
            payload["play_mode"] = r.i()             # 0 loop / 1 once (dropped by the object)
            payload["seconds"] = r.i()               # dropped
            payload["finish"] = r.lb()
        case 8:                                      # Trade (editor writes no payload)
            pass
        case 9:                                      # Jump
            payload["jump_label"] = r.s()
            payload["con_id"] = r.i()
        case 10:                                     # Random
            payload["labels"] = tuple(r.s() for _ in range(r.i()))
            payload["cycle"] = r.lb()
            payload["cycle_once"] = r.lb()
            payload["cycle_random"] = r.lb()
        case 11:                                     # Trigger
            payload["tag"] = r.s()
        case 12:                                     # AddGoal
            payload["goal_name"] = r.s()
            payload["complete"] = r.lb()
            if not payload["complete"]:
                payload["goal_text"] = r.s()
                payload["primary"] = r.lb()
        case 13:                                     # AddNote
            payload["text"] = r.s()
        case 14:                                     # AddSkillPoints
            payload["points"] = r.i()
            payload["award"] = r.s()
        case 15:                                     # AddCredits
            payload["credits"] = r.i()
        case 16:                                     # CheckPersona
            payload["persona"] = r.i()
            payload["condition"] = r.i()
            payload["value"] = r.i()
            payload["jump_label"] = r.s()
        case 17:                                     # Comment
            payload["text"] = r.s()
        case 18:                                     # End
            pass
    return ConEvent(kind=kind, label=label, payload=payload)


def _parse_choice(r: _Reader) -> ConChoiceEntry:
    r.i()                                            # choice index (unk0)
    text = r.s()
    display_as_speech = r.lb()
    skill = r.i()
    skill_name = ""
    skill_level = 0
    if skill >= 0:
        skill_name = r.s()
        skill_level = r.i()
    label = r.s()
    mp3 = r.s()
    flags = tuple(_parse_flagref(r) for _ in range(r.i()))
    return ConChoiceEntry(text=text, label=label, display_as_speech=display_as_speech, mp3=mp3,
                          skill=skill, skill_name=skill_name, skill_level=skill_level, flags=flags)


# ══ ConSys property schemas (field-iteration order + type, read from ConSys.u) ═════════════════════
_LABEL_PTYPE = {"name": PT_NAME, "string": PT_STR, "bool": PT_BOOL, "byte": PT_BYTE,
                "int": PT_INT, "float": 4}   # PT_FLOAT unused by conversations


def _schema(env: InstallEnv) -> dict[str, list[tuple[str, int]]]:
    """`{class_cf: [(field_name, ptype), …]}` for every ConSys class, in UE field-iteration order
    (own properties first in Children order, then up the super chain, within ConSys)."""
    pkg = env._load("ConSys")
    cls_idx = {pkg.names[e["nm"]].casefold(): i + 1
               for i, e in enumerate(pkg.exports) if e["cls"] == 0}

    def own(idx1: int) -> list[tuple[str, int]]:
        e = pkg.exports[idx1 - 1]
        buf, pos = pkg.buf, e["soff"]
        for _ in range(3):                            # Super, Next, ScriptText
            _, pos = _rci(buf, pos)
        cur, _ = _rci(buf, pos)
        out: list[tuple[str, int]] = []
        for _ in range(4096):
            if cur <= 0:
                break
            ee = pkg.exports[cur - 1]
            if pkg.name_of_ref(ee["cls"]) in PROPERTY_TYPES:
                label = prop_type_label(_decode_property(pkg, cur, ""))
                if label.startswith(("object:", "class")):
                    pt = PT_OBJECT
                elif label.startswith("struct:"):
                    pt = 10
                else:
                    pt = _LABEL_PTYPE.get(label, PT_INT)
                out.append((pkg.names[ee["nm"]], pt))
            cur = _field_next(pkg, cur)
        return out

    schema: dict[str, list[tuple[str, int]]] = {}
    for cf, idx1 in cls_idx.items():
        fields: list[tuple[str, int]] = []
        seen: set[str] = set()
        name: str | None = pkg.names[pkg.exports[idx1 - 1]["nm"]]
        for _ in range(32):
            if name is None or name.casefold() not in cls_idx:
                break
            cur_idx = cls_idx[name.casefold()]
            for fname, pt in own(cur_idx):
                if fname.casefold() not in seen:
                    seen.add(fname.casefold())
                    fields.append((fname, pt))
            sup = pkg.exports[cur_idx - 1]["sup"]
            name = pkg.name_of_ref(sup) if sup != 0 else None
        schema[cf] = fields
    return schema


# ══ the emitted object graph ══════════════════════════════════════════════════════════════════════
@dataclass(kw_only=True)
class _Obj:
    key: str
    name: str
    class_name: str                      # ConSys class
    object_flags: int
    values: dict                         # field_cf -> literal value or ("ref", key) for objects
    trailer: bytes = b""


@dataclass(kw_only=True)
class _Builder:
    schema: dict[str, list[tuple[str, int]]]
    objs: list[_Obj] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)

    def _name(self, class_name: str) -> str:
        n = self.counters.get(class_name, 0)
        self.counters[class_name] = n + 1
        return f"{class_name}{n}"

    def add(self, class_name: str, values: dict, *, name: str | None = None,
            standalone: bool = False, trailer: bytes = b"") -> str:
        key = f"obj{len(self.objs)}"
        self.objs.append(_Obj(key=key, name=name or self._name(class_name), class_name=class_name,
                              object_flags=_RF_STANDALONE if standalone else _RF_OBJECT,
                              values={k.casefold(): v for k, v in values.items()}, trailer=trailer))
        return key

    def obj(self, key: str) -> _Obj:
        return self.objs[int(key.removeprefix("obj"))]


def _flagref_chain(b: _Builder, flags: tuple[ConFlagEntry, ...]) -> str | None:
    """Build a ConFlagRef linked list (nextFlagRef), return the first's key (or None if empty)."""
    keys = []
    for fr in flags:
        vals: dict = {"FlagName": fr.name}
        if fr.value:
            vals["Value"] = True
        keys.append(b.add("ConFlagRef", vals))
    for i, k in enumerate(keys[:-1]):
        b.obj(k).values["nextflagref"] = ("ref", keys[i + 1])
    return keys[0] if keys else None


def _build_event(b: _Builder, ev: ConEvent, conv_key: str, conv_by_id: dict[int, str]) -> str:
    """Create the ConEvent* object (plus its ConSpeech / ConChoice / ConFlagRef sub-objects) and
    return its key. `nextEvent`/`Conversation` are filled by the caller / here."""
    p = ev.payload
    v: dict = {}
    match ev.kind:
        case "ConEventSpeech":
            if p["speaker"]:
                v["speakerName"] = p["speaker"]
            if p["speaking_to"]:
                v["speakingToName"] = p["speaking_to"]
            speech_vals = {"Speech": p["text"]} if p["text"] else {}
            v["ConSpeech"] = ("ref", b.add("ConSpeech", speech_vals))
            if p["continued"]:
                v["bContinued"] = True
            if p["bold"]:
                v["bBold"] = True
            if p["font"]:
                v["speechFont"] = p["font"]
        case "ConEventChoice":
            if p["clear_screen"]:
                v["bClearScreen"] = True
            first = _build_choice_chain(b, p["choices"])
            if first is not None:
                v["ChoiceList"] = ("ref", first)
        case "ConEventSetFlag":
            first = _flagref_chain(b, p["flags"])
            if first is not None:
                v["flagRef"] = ("ref", first)
        case "ConEventCheckFlag":
            first = _flagref_chain(b, p["flags"])
            if first is not None:
                v["flagRef"] = ("ref", first)
            if p["goto_label"]:
                v["setLabel"] = p["goto_label"]
        case "ConEventCheckObject":
            if p["object"]:
                v["ObjectName"] = p["object"]
            if p["fail_label"]:
                v["failLabel"] = p["fail_label"]
        case "ConEventTransferObject":
            if p["object"]:
                v["ObjectName"] = p["object"]
            if p["count"]:
                v["transferCount"] = p["count"]
            if p["from_name"]:
                v["fromName"] = p["from_name"]
            if p["to_name"]:
                v["toName"] = p["to_name"]
            if p["fail_label"]:
                v["failLabel"] = p["fail_label"]
        case "ConEventMoveCamera":
            if p["camera_type"]:
                v["cameraType"] = p["camera_type"]
            if p["camera_position"]:
                v["cameraPosition"] = p["camera_position"]
            if p["camera_transition"] & 0xFF:
                v["cameraTransition"] = p["camera_transition"] & 0xFF
        case "ConEventAnimation":
            if p["owner"]:
                v["eventOwnerName"] = p["owner"]
            if p["sequence"]:
                v["Sequence"] = p["sequence"]
            if p["finish"]:
                v["bFinishAnim"] = True
        case "ConEventJump":
            if p["jump_label"]:
                v["jumpLabel"] = p["jump_label"]
            target = conv_by_id.get(p["con_id"])
            if target is not None:
                v["jumpCon"] = ("ref", target)
            if p["con_id"]:
                v["conID"] = p["con_id"]
        case "ConEventRandomLabel":
            pass                                     # residual: RandomLabel field mapping unverified
        case "ConEventTrigger":
            if p["tag"]:
                v["triggerTag"] = p["tag"]
        case "ConEventAddGoal":
            if p["goal_name"]:
                v["goalName"] = p["goal_name"]
            if p["complete"]:
                v["bGoalCompleted"] = True
            else:
                if p.get("goal_text"):
                    v["goalText"] = p["goal_text"]
                if p.get("primary"):
                    v["bPrimaryGoal"] = True
        case "ConEventAddNote":
            if p["text"]:
                v["noteText"] = p["text"]
        case "ConEventAddSkillPoints":
            if p["points"]:
                v["pointsToAdd"] = p["points"]
            if p["award"]:
                v["awardMessage"] = p["award"]
        case "ConEventAddCredits":
            if p["credits"]:
                v["creditsToAdd"] = p["credits"]
        case "ConEventCheckPersona":
            if p["persona"]:
                v["personaType"] = p["persona"]
            if p["condition"]:
                v["condition"] = p["condition"]
            if p["value"]:
                v["Value"] = p["value"]
            if p["jump_label"]:
                v["jumpLabel"] = p["jump_label"]
        case "ConEventComment":
            if p["text"]:
                v["commentText"] = p["text"]
        case "ConEventTrade" | "ConEventEnd":
            pass
    etype = next(k for k, cls in _EVENT_CLASS.items() if cls == ev.kind)
    if etype:                                        # eventType byte (default 0 = Speech omitted)
        v["eventType"] = etype
    if ev.label:
        v["Label"] = ev.label
    v["Conversation"] = ("ref", conv_key)
    return b.add(ev.kind, v)


def _build_choice_chain(b: _Builder, choices: tuple[ConChoiceEntry, ...]) -> str | None:
    keys = []
    for ch in choices:
        vals: dict = {}
        if ch.text:
            vals["choiceText"] = ch.text
        if ch.label:
            vals["choiceLabel"] = ch.label
        if ch.display_as_speech:
            vals["bDisplayAsSpeech"] = True          # residual: no speech-synthesis expansion
        if ch.skill_level:
            vals["skillLevelNeeded"] = ch.skill_level
        first_flag = _flagref_chain(b, ch.flags)
        if first_flag is not None:
            vals["flagRef"] = ("ref", first_flag)
        keys.append(b.add("ConChoice", vals))
    for i, k in enumerate(keys[:-1]):
        b.obj(k).values["nextchoice"] = ("ref", keys[i + 1])
    return keys[0] if keys else None


def _build_conversation(b: _Builder, conv: ConConversation, audio_package: str,
                        conv_by_id: dict[int, str]) -> str:
    conv_key = b.add("Conversation", {})            # per-class counter → Conversation0, …
    conv_by_id[conv.id] = conv_key
    obj = b.obj(conv_key)
    v = obj.values
    if conv.con_name:
        v["conname"] = conv.con_name
    if conv.description:
        v["description"] = conv.description
    if conv.owner_name:
        v["conownername"] = conv.owner_name
    if conv.b_data_link:
        v["bdatalinkcon"] = True
    _CONV_BOOL_FIELD = {
        "display_once": "bDisplayOnce", "first_person": "bFirstPerson",
        "non_interact": "bNonInteractive", "random_camera": "bRandomCamera",
        "can_interrupt": "bCanBeInterrupted", "cannot_interrupt": "bCannotBeInterrupted",
        "invoke_bump": "bInvokeBump", "invoke_frob": "bInvokeFrob",
        "invoke_sight": "bInvokeSight", "invoke_radius": "bInvokeRadius"}
    for src, fld in _CONV_BOOL_FIELD.items():
        if conv.bools.get(src):
            v[fld.casefold()] = True
    if conv.invoke_radius:
        v["radiusdistance"] = conv.invoke_radius
    flag_first = _flagref_chain(b, conv.flag_refs)
    # events: create each, then link nextEvent in order
    event_keys = [_build_event(b, ev, conv_key, conv_by_id) for ev in conv.events]
    for i, k in enumerate(event_keys[:-1]):
        b.obj(k).values["nextevent"] = ("ref", event_keys[i + 1])
    if event_keys:
        v["eventlist"] = ("ref", event_keys[0])
    if flag_first is not None:
        v["flagreflist"] = ("ref", flag_first)
    if conv.id:
        v["conversationid"] = conv.id
    if audio_package:
        v["audiopackagename"] = audio_package
    return conv_key


def _build_scaffolding(b: _Builder, con: ConFile, conv_keys: list[str]) -> None:
    """The mission scaffolding: ConversationMissionList → ConItem → ConversationList → ConItem →
    Conversation. Single-mission is verified byte-exact; multi-mission is a faithful generalisation."""
    mission_items: list[str] = []
    for mission in (con.missions or (0,)):
        mkey = b.add("ConItem", {})                  # the mission's ConItem is created FIRST
        conv_items = [b.add("ConItem", {"ConObject": ("ref", ck)}) for ck in conv_keys]
        for i, k in enumerate(conv_items[:-1]):
            b.obj(k).values["next"] = ("ref", conv_items[i + 1])
        list_vals: dict = {}
        if conv_items:
            list_vals["conversations"] = ("ref", conv_items[0])
        list_vals["missionDescription"] = f"Mission {mission}"
        clist = b.add("ConversationList", list_vals, name=f"ConList_Mission{mission:02d}",
                      standalone=True)
        b.obj(mkey).values["conobject"] = ("ref", clist)
        mission_items.append(mkey)
    for i, k in enumerate(mission_items[:-1]):
        b.obj(k).values["next"] = ("ref", mission_items[i + 1])
    mvals: dict = {}
    if mission_items:
        mvals["missions"] = ("ref", mission_items[0])
    b.add("ConversationMissionList", mvals, name="ConMissionList", standalone=True)


# ══ package assembly ══════════════════════════════════════════════════════════════════════════════
def _name_flags(name: str) -> int:
    flags = 0x00070010
    cf = name.casefold()
    if cf in highlight_name_pool():
        flags |= 0x00000400
    if cf in engine_name_pool():
        flags |= 0x04000000
    return flags


def _assemble(objs: list[_Obj], package_name: str, schema: dict[str, list[tuple[str, int]]]
              ) -> CompiledPackage:
    """Turn a built object list into a `CompiledPackage`: export table (creation order), ConSys import
    table, name table, and each object's tagged-property body (fields emitted in class field order)."""
    key_to_ref = {o.key: i + 1 for i, o in enumerate(objs)}

    # imports: ConSys package + each referenced ConSys class.
    class_names: list[str] = []
    for o in objs:
        if o.class_name not in class_names:
            class_names.append(o.class_name)
    import_specs = [("Core", "Package", None, "ConSys")]
    imp_ref = {"ConSys": -1}
    for cn in class_names:
        imp_ref[cn] = -(len(import_specs) + 1)
        import_specs.append(("Core", "Class", "ConSys", cn))

    # names: collect the exact set (order excluded by the gate).
    names_order: list[str] = []
    seen: set[str] = set()

    def add_name(n: str) -> None:
        if n not in seen:
            seen.add(n)
            names_order.append(n)

    for n in ("None", package_name, "Core", "Class", "Package", "ConSys"):
        add_name(n)
    for cn in class_names:
        add_name(cn)
    # tags (property names + name-valued values), in field order per object.
    tag_lists: dict[str, list[Prop]] = {}
    for o in objs:
        add_name(o.name)
        props: list[Prop] = []
        for fname, pt in schema.get(o.class_name.casefold(), []):
            if fname.casefold() not in o.values:
                continue
            raw = o.values[fname.casefold()]
            add_name(fname)
            if pt == PT_OBJECT:
                props.append(Prop(fname, PT_OBJECT, key_to_ref[raw[1]]))
            elif pt == PT_NAME:
                add_name(raw)
                props.append(Prop(fname, PT_NAME, raw))
            elif pt == PT_BOOL:
                props.append(Prop(fname, PT_BOOL, bool(raw)))
            elif pt == PT_BYTE:
                props.append(Prop(fname, PT_BYTE, int(raw)))
            elif pt == PT_INT:
                props.append(Prop(fname, PT_INT, int(raw)))
            elif pt == PT_STR:
                props.append(Prop(fname, PT_STR, raw))
            else:
                raise NotImplementedError(f"conimport: field {o.class_name}.{fname} ptype {pt}")
        tag_lists[o.key] = props

    name_index = {n: i for i, n in enumerate(names_order)}
    names = tuple(Name(text=n, flags=_name_flags(n)) for n in names_order)
    imports = tuple(Import(class_package=name_index[cp], class_name=name_index[cn],
                           package_index=0 if outer is None else imp_ref[outer],
                           object_name=name_index[on]) for cp, cn, outer, on in import_specs)

    exports = []
    for o in objs:
        props = write_props(lambda s: name_index[s], tag_lists[o.key])
        exports.append(Export(cls=imp_ref[o.class_name], super_ref=0, outer=0,
                              name=name_index[o.name], flags=o.object_flags,
                              body=ObjectBody(props=props, trailer=o.trailer)))
    return CompiledPackage(version=68, licensee=0, package_flags=1, names=names,
                           imports=imports, exports=tuple(exports))


def build_conversation_packages(con: ConFile, base_pkg_name: str, env: InstallEnv
                                ) -> dict[str, CompiledPackage]:
    """Build the sibling packages a `#exec CONVERSATION IMPORT` of `con` emits, keyed by package name
    (`<base>Text`, `<base>Audio<audioPackage>`). The class package itself is unchanged."""
    schema = _schema(env)
    b = _Builder(schema=schema)
    conv_by_id: dict[int, str] = {}
    conv_keys = [_build_conversation(b, c, con.audio_package, conv_by_id) for c in con.conversations]
    _build_scaffolding(b, con, conv_keys)

    text_name = f"{base_pkg_name}Text"
    out = {text_name: _assemble(b.objs, text_name, schema)}
    if con.audio_package:
        audio_name = f"{base_pkg_name}Audio{con.audio_package}"
        audio_obj = _Obj(key="a0", name=f"ConAudioList_{con.audio_package}",
                         class_name="ConAudioList", object_flags=_RF_STANDALONE, values={},
                         trailer=b"\x00")
        out[audio_name] = _assemble([audio_obj], audio_name, schema)
    return out

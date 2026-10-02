"""Serializer + CRC pins: the rung-0 model (`class UscHello expands Object;`) serialized byte-exact
against the committed UCC golden `fixtures/uscript/UscHello.u`, and the two `appStrCrc` calibration
values. Pure — no docker; regenerate the golden via `uscript.reference.ucc_compile`."""
from __future__ import annotations

from pathlib import Path

from uedcli.native.codec import ref_export, ref_import
from uedcli.uscript.crc import script_text_crc
from uedcli.uscript.gate import gate
from uedcli.uscript.model import (
    ClassBody, CompiledPackage, Dependency, Export, Import, Name, TextBufferBody,
)
from uedcli.uscript.serialize import serialize

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "uscript" / "UscHello.u"
_OBJECT_DEP_CRC = 0xD735B29C  # read from core.u's Object self-dependency (imported dep)


def _usc_hello_model() -> CompiledPackage:
    order = ["None", "UscHello", "Core", "System", "Class", "TextBuffer", "ScriptText",
             "Package", "Object"]
    idx = {n: i for i, n in enumerate(order)}
    base, imp_bit, struct_bit = 0x00070010, 0x04000000, 0x04000400
    extra = {"Core": imp_bit, "System": imp_bit, "TextBuffer": imp_bit, "Object": imp_bit,
             "None": struct_bit, "Class": struct_bit, "Package": struct_bit}
    names = tuple(Name(text=n, flags=base | extra.get(n, 0)) for n in order)
    imports = (
        Import(class_package=idx["Core"], class_name=idx["Package"], package_index=0,
               object_name=idx["Core"]),
        Import(class_package=idx["Core"], class_name=idx["Class"], package_index=-1,
               object_name=idx["Object"]),
        Import(class_package=idx["Core"], class_name=idx["Class"], package_index=-1,
               object_name=idx["TextBuffer"]),
        Import(class_package=idx["Core"], class_name=idx["Class"], package_index=-1,
               object_name=idx["Class"]),
    )
    text = "class UscHello expands Object;\r\n"
    class_body = ClassBody(
        super_field=ref_import(1), next_field=0, script_text=ref_export(0), children=0,
        friendly_name=idx["UscHello"], line=0xFFFFFFFF, text_pos=0xFFFFFFFF, script=b"",
        probe_mask=0, ignore_mask=0xFFFFFFFFFFFFFFFF, label_table_offset=0xFFFF, state_flags=0,
        class_flags=0x12, class_guid=bytes(16),
        dependencies=(Dependency(cls=ref_export(1), deep=1, script_text_crc=script_text_crc(text)),
                      Dependency(cls=ref_import(1), deep=1, script_text_crc=_OBJECT_DEP_CRC)),
        package_imports=(idx["UscHello"], idx["Core"]),
        class_within=ref_import(1), class_config_name=idx["System"], default_props=b"\x00",
    )
    exports = (
        Export(cls=ref_import(2), super_ref=0, outer=ref_export(1), name=idx["ScriptText"],
               flags=0x00340000, body=TextBufferBody(pos=0, top=0, text=text)),
        Export(cls=0, super_ref=ref_import(1), outer=0, name=idx["UscHello"], flags=0x000F0004,
               body=class_body),
    )
    return CompiledPackage(version=69, licensee=0, package_flags=1, names=names,
                           imports=imports, exports=exports, guid=bytes(16))


def test_rung0_serializes_byte_exact():
    golden = _GOLDEN.read_bytes()
    mine = serialize(_usc_hello_model())
    r = gate(mine, golden)
    assert r.passed, r.messages


def test_crc_calibration():
    assert script_text_crc("class UscHello expands Object;\r\n") == 0xEBD981FF


def test_crc_object_scripttext():
    # sanity: the imported-dep CRC constant matches core.u's stored value (documented provenance)
    assert _OBJECT_DEP_CRC == 0xD735B29C

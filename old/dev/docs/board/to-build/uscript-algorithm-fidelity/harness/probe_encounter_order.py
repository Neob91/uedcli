"""Controlled UCC compiles that pin the own-name compile ENCOUNTER order (name-table tie-break for a
package's own new names). Compiles each probe via reference.ucc_compile and prints its name table.

Findings (UED22, 2026-09-05) — encounter order = DECLARATION order (class, members decl order, then
defaultproperties value-names), independent of type and of which members have defaults:

  probe (members; defaults)                                observed member order  -> rule
  Qsame  int Zqaa,Zqab,Zqac; none                          decl                   decl
  Qmix   int,float,string (new); none                      decl                   decl
  Qmixd  int,float,string (new); int&float set             decl (string last)     decl
  Qrev   string,float,int (new); none                      decl                   decl
  Pf     float(set),string(unset) new                      decl (float,string)    decl
  Pg     float(unset),string(set) new                      decl                   decl
  Ph     float,string new; none                            decl                   decl
  Pc     int A(Core.u,set),float(set),string(unset)        decl (float,string)    decl

A member/value name already in a loaded package (Core.u: A,B,C,X,Y,Alpha,...) is NOT new — it keeps
its Core.u global index. That is why UscVars (member `Alpha` ∈ Core.u) exercises the reconstructed
Core.u index order, and is the one case reproduce_name_order.py does not yet match (an index-precision
residual, not an encounter-rule one — `Pc` has UscVars's structure with a different Core.u member and
DOES reproduce).

Run: needs docker + the UED22 substrate. Use a worktree-local TMPDIR (never the shared /tmp):
     TMPDIR=$PWD/_scratch/pttmp python3 <this>
"""
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from uedcli.upackage import read_fstring
from uedcli.uscript.reference import ucc_compile, ucc_container


def name_table(u: bytes) -> list[str]:
    _t, _v, _f, nc, no, *_ = struct.unpack_from("<9I", u, 0)
    out, pos = [], no
    for _ in range(nc):
        s, pos = read_fstring(u, pos); pos += 4; out.append(s)
    return out


PROBES = {
 "Qsame": "class Qsame expands Object;\n\nvar int Zqaa;\nvar int Zqab;\nvar int Zqac;\n",
 "Qmix":  "class Qmix expands Object;\n\nvar int Zqba;\nvar float Zqbb;\nvar string Zqbc;\n",
 "Qmixd": "class Qmixd expands Object;\n\nvar int Zqca;\nvar float Zqcb;\nvar string Zqcc;\n\ndefaultproperties\n{\n     Zqca=1\n     Zqcb=1.500000\n}\n",
 "Qrev":  "class Qrev expands Object;\n\nvar string Zqda;\nvar float Zqdb;\nvar int Zqdc;\n",
 "Pf":    "class Pf expands Object;\n\nvar float Zpfb;\nvar string Zpfc;\n\ndefaultproperties\n{\n     Zpfb=1.500000\n}\n",
 "Pc":    "class Pc expands Object;\n\nvar int A;\nvar float Zpcb;\nvar string Zpcc;\n\ndefaultproperties\n{\n     A=7\n     Zpcb=1.500000\n}\n",
}

if __name__ == "__main__":
    stable = os.path.abspath("_scratch/re/ucctmp")
    os.makedirs(stable, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=stable) as td:
        with ucc_container(state_dir=td) as c:
            for pkg, src in PROBES.items():
                cls = src.split()[1]
                try:
                    print(pkg, name_table(ucc_compile(c, pkg, {f"{cls}.uc": src})))
                except Exception as e:
                    print(pkg, "FAILED:", e)

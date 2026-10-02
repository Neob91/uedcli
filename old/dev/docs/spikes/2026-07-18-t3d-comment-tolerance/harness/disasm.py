#!/usr/bin/env python3
"""Disassemble a function from an UnrealEd DLL and resolve wide/ansi string
references, to reverse-engineer the T3D import line reader + property loop.

Static only: reads the bind-mounted DLLs, never runs the editor.

Usage:
  disasm.py <dll> <export-substr> [max_bytes]
  disasm.py <dll> @<rva_hex> [max_bytes]
"""
import sys, re
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

def load(path):
    pe = pefile.PE(path)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()  # RVA-indexed
    return pe, image_base, data

def wide_at(data, rva, maxlen=200):
    out=[]
    i=rva
    while i+1 < len(data) and len(out)<maxlen:
        lo,hi=data[i],data[i+1]
        if hi!=0: break
        if lo==0: break
        if lo<0x20 or lo>0x7e: break
        out.append(chr(lo)); i+=2
    return ''.join(out) if len(out)>=1 else None

def ansi_at(data, rva, maxlen=200):
    out=[]
    i=rva
    while i<len(data) and len(out)<maxlen:
        c=data[i]
        if c==0: break
        if c<0x20 or c>0x7e: break
        out.append(chr(c)); i+=1
    return ''.join(out) if len(out)>=2 else None

def resolve(data, image_base, ptr):
    rva = ptr - image_base
    if rva<0 or rva>=len(data): return None
    w=wide_at(data,rva)
    if w and len(w)>=2: return ('W',w)
    a=ansi_at(data,rva)
    if a: return ('A',a)
    if w: return ('W',w)
    return None

def exports(pe):
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    return {e.name.decode('latin1'):e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}

def find_rva(pe, spec):
    if spec.startswith('@'):
        return int(spec[1:],16)
    exp=exports(pe)
    cands=[(n,a) for n,a in exp.items() if spec in n]
    if not cands:
        print('no export matches',spec); sys.exit(1)
    if len(cands)>1:
        print('multiple matches:')
        for n,a in cands: print(f'  {a:#x} {n}')
    n,a=cands[0]
    print(f'# using {n} @ {a:#x}')
    return a

def main():
    path=sys.argv[1]; spec=sys.argv[2]
    maxb=int(sys.argv[3],0) if len(sys.argv)>3 else 0x1200
    pe,image_base,data=load(path)
    rva=find_rva(pe,spec)
    code=data[rva:rva+maxb]
    md=Cs(CS_ARCH_X86,CS_MODE_32)
    md.detail=True
    for ins in md.disasm(code, image_base+rva):
        line=f'{ins.address:#010x}  {ins.mnemonic:6} {ins.op_str}'
        # try to resolve any immediate that points into image as a string
        note=''
        for tok in re.findall(r'0x[0-9a-fA-F]+', ins.op_str):
            val=int(tok,16)
            r=resolve(data,image_base,val)
            if r:
                note += f"   ; {r[0]}\"{r[1]}\""
        # also flag byte compares with /,*,;,cr,lf
        if ins.mnemonic in ('cmp','mov','movzx') :
            for tok in re.findall(r'\b(0x[0-9a-fA-F]+|\d+)\b', ins.op_str):
                try: v=int(tok,0)
                except: continue
                if v in (0x2f,0x2a,0x3b,0x0d,0x0a,0x23,0x25):
                    note += f"   ; char {chr(v)!r}(={v:#x})"
        print(line+note)
        if ins.mnemonic=='ret':
            print('---- ret ----')

if __name__=='__main__':
    main()

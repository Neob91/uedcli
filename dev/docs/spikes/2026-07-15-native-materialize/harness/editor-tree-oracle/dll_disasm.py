import sys, pefile, capstone
path="/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/uned/UED22/Editor.dll"
rva=int(sys.argv[1],16); n=int(sys.argv[2]) if len(sys.argv)>2 else 400
pe=pefile.PE(path, fast_load=True)
base=pe.OPTIONAL_HEADER.ImageBase
data=pe.get_memory_mapped_image()
code=data[rva:rva+n*8]
md=capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail=False
cnt=0
for insn in md.disasm(code, base+rva):
    print(f"0x{insn.address:08x}: {insn.mnemonic:8s} {insn.op_str}")
    cnt+=1
    if cnt>=n: break
    if insn.mnemonic=='ret': break

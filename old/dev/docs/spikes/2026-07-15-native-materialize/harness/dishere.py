import sys, pe
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
p=sys.argv[1]; start=int(sys.argv[2],16); length=int(sys.argv[3],16)
peo=pe.load(p); base=pe.image_base(p)
off=start-base
code=peo.__data__[off:off+length]
md=Cs(CS_ARCH_X86,CS_MODE_32); md.detail=True
for i in md.disasm(bytes(code), start):
    print("0x%x:\t%s\t%s"%(i.address,i.mnemonic,i.op_str))

import pefile, struct
pe=pefile.PE("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/uned/UED22/Editor.dll")
base=pe.OPTIONAL_HEADER.ImageBase
data=pe.get_memory_mapped_image()
# map RVA->export name
exp={}
for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if e.name: exp[e.address]=e.name.decode(errors='replace')
target=0x100365b0-base  # bspNodeToFPoly RVA
# find a 4-byte little-endian VA pointing to bspNodeToFPoly
needle=struct.pack("<I",0x100365b0)
idx=0
found=[]
while True:
    i=data.find(needle, idx)
    if i<0: break
    found.append(i); idx=i+1
for slotloc in found:
    vt=slotloc-0x1f8  # vtable base if this is slot +0x1f8
    print(f"candidate vtable base RVA {vt:#x}")
    for off in (0x1f8,0x1fc,0x204,0x208,0x210,0x214,0x224,0x264):
        ptr=struct.unpack("<I", data[vt+off:vt+off+4])[0]
        name=exp.get(ptr-base,"?")
        print(f"   +{off:#05x} -> {ptr:#x}  {name[:60]}")
    print()

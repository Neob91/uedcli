import pefile, re, sys
pe=pefile.PE("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/uned/UED22/Editor.dll")
pat=sys.argv[1] if len(sys.argv)>1 else "bsp"
for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if e.name and pat.encode() in e.name:
        print(f"0x{e.address:06x}  {e.name.decode(errors='replace')[:90]}")

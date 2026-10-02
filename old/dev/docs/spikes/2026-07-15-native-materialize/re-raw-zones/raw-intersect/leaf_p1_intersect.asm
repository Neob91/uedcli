0x100339e0  push    ebp
0x100339e1  mov     ebp, esp
0x100339e3  push    -1
0x100339e5  push    0x100c49f0
0x100339ea  mov     eax, dword ptr fs:[0]
0x100339f0  push    eax
0x100339f1  sub     esp, 0xc
0x100339f4  push    ebx
0x100339f5  push    esi
0x100339f6  push    edi
0x100339f7  mov     eax, dword ptr [0x10140164]  ; f32=-0.00294341
0x100339fc  xor     eax, ebp
0x100339fe  push    eax
0x100339ff  lea     eax, [ebp - 0xc]
0x10033a02  mov     dword ptr fs:[0], eax
0x10033a08  mov     dword ptr [ebp - 0x10], esp
0x10033a0b  mov     dword ptr [ebp - 4], 0
0x10033a12  mov     eax, dword ptr [ebp + 0x14]
0x10033a15  sub     eax, 1
0x10033a18  je      0x10033a1f
0x10033a1a  sub     eax, 2
0x10033a1d  jne     0x10033a55
0x10033a1f  mov     ecx, dword ptr [ebp + 0x10]
0x10033a22  call    dword ptr [0x100cee38]
0x10033a28  cmp     eax, 3
0x10033a2b  jl      0x10033a55
0x10033a2d  mov     eax, dword ptr [0x101491c8]  ; a"+2d2l2y2"
0x10033a32  mov     eax, dword ptr [eax + 0x54]
0x10033a35  add     eax, 0x28
0x10033a38  push    eax
0x10033a39  push    0x1d8
0x10033a3e  call    0x10015710
0x10033a43  add     esp, 8
0x10033a46  test    eax, eax
0x10033a48  je      0x10033a55
0x10033a4a  push    dword ptr [ebp + 0x10]
0x10033a4d  mov     ecx, eax
0x10033a4f  call    dword ptr [0x100cee94]
0x10033a55  mov     dword ptr [ebp - 4], 0xffffffff
0x10033a5c  mov     ecx, dword ptr [ebp - 0xc]
0x10033a5f  mov     dword ptr fs:[0], ecx
0x10033a66  pop     ecx
0x10033a67  pop     edi
0x10033a68  pop     esi
0x10033a69  pop     ebx
0x10033a6a  mov     esp, ebp
0x10033a6c  pop     ebp
0x10033a6d  ret     

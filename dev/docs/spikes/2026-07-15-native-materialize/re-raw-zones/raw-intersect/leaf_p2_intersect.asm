0x10033ab0  push    ebp
0x10033ab1  mov     ebp, esp
0x10033ab3  push    -1
0x10033ab5  push    0x100c4a10
0x10033aba  mov     eax, dword ptr fs:[0]
0x10033ac0  push    eax
0x10033ac1  sub     esp, 0xc
0x10033ac4  push    ebx
0x10033ac5  push    esi
0x10033ac6  push    edi
0x10033ac7  mov     eax, dword ptr [0x10140164]  ; f32=-0.00294341
0x10033acc  xor     eax, ebp
0x10033ace  push    eax
0x10033acf  lea     eax, [ebp - 0xc]
0x10033ad2  mov     dword ptr fs:[0], eax
0x10033ad8  mov     dword ptr [ebp - 0x10], esp
0x10033adb  mov     dword ptr [ebp - 4], 0
0x10033ae2  mov     eax, dword ptr [ebp + 0x14]
0x10033ae5  sub     eax, 1
0x10033ae8  je      0x10033af4
0x10033aea  sub     eax, 2
0x10033aed  je      0x10033af4
0x10033aef  sub     eax, 2
0x10033af2  jne     0x10033b2a
0x10033af4  mov     ecx, dword ptr [ebp + 0x10]
0x10033af7  call    dword ptr [0x100cee38]
0x10033afd  cmp     eax, 3
0x10033b00  jl      0x10033b2a
0x10033b02  mov     eax, dword ptr [0x101491c8]  ; a"+2d2l2y2"
0x10033b07  mov     eax, dword ptr [eax + 0x54]
0x10033b0a  add     eax, 0x28
0x10033b0d  push    eax
0x10033b0e  push    0x1d8
0x10033b13  call    0x10015710
0x10033b18  add     esp, 8
0x10033b1b  test    eax, eax
0x10033b1d  je      0x10033b2a
0x10033b1f  push    dword ptr [ebp + 0x10]
0x10033b22  mov     ecx, eax
0x10033b24  call    dword ptr [0x100cee94]
0x10033b2a  mov     dword ptr [ebp - 4], 0xffffffff
0x10033b31  mov     ecx, dword ptr [ebp - 0xc]
0x10033b34  mov     dword ptr fs:[0], ecx
0x10033b3b  pop     ecx
0x10033b3c  pop     edi
0x10033b3d  pop     esi
0x10033b3e  pop     ebx
0x10033b3f  mov     esp, ebp
0x10033b41  pop     ebp
0x10033b42  ret     

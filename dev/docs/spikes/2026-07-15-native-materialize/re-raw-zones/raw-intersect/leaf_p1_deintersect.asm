0x10032390  push    ebp
0x10032391  mov     ebp, esp
0x10032393  push    -1
0x10032395  push    0x100c4820
0x1003239a  mov     eax, dword ptr fs:[0]
0x100323a0  push    eax
0x100323a1  sub     esp, 0xc
0x100323a4  push    ebx
0x100323a5  push    esi
0x100323a6  push    edi
0x100323a7  mov     eax, dword ptr [0x10140164]  ; f32=-0.00294341
0x100323ac  xor     eax, ebp
0x100323ae  push    eax
0x100323af  lea     eax, [ebp - 0xc]
0x100323b2  mov     dword ptr fs:[0], eax
0x100323b8  mov     dword ptr [ebp - 0x10], esp
0x100323bb  mov     dword ptr [ebp - 4], 0
0x100323c2  mov     eax, dword ptr [ebp + 0x14]
0x100323c5  sub     eax, 0
0x100323c8  je      0x100323cf
0x100323ca  sub     eax, 2
0x100323cd  jne     0x10032405
0x100323cf  mov     ecx, dword ptr [ebp + 0x10]
0x100323d2  call    dword ptr [0x100cee38]
0x100323d8  cmp     eax, 3
0x100323db  jl      0x10032405
0x100323dd  mov     eax, dword ptr [0x101491c8]  ; a"+2d2l2y2"
0x100323e2  mov     eax, dword ptr [eax + 0x54]
0x100323e5  add     eax, 0x28
0x100323e8  push    eax
0x100323e9  push    0x1d8
0x100323ee  call    0x10015710
0x100323f3  add     esp, 8
0x100323f6  test    eax, eax
0x100323f8  je      0x10032405
0x100323fa  push    dword ptr [ebp + 0x10]
0x100323fd  mov     ecx, eax
0x100323ff  call    dword ptr [0x100cee94]
0x10032405  mov     dword ptr [ebp - 4], 0xffffffff
0x1003240c  mov     ecx, dword ptr [ebp - 0xc]
0x1003240f  mov     dword ptr fs:[0], ecx
0x10032416  pop     ecx
0x10032417  pop     edi
0x10032418  pop     esi
0x10032419  pop     ebx
0x1003241a  mov     esp, ebp
0x1003241c  pop     ebp
0x1003241d  ret     

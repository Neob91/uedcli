0x10032460  push    ebp
0x10032461  mov     ebp, esp
0x10032463  push    -1
0x10032465  push    0x100c4840
0x1003246a  mov     eax, dword ptr fs:[0]
0x10032470  push    eax
0x10032471  sub     esp, 0xc
0x10032474  push    ebx
0x10032475  push    esi
0x10032476  push    edi
0x10032477  mov     eax, dword ptr [0x10140164]  ; f32=-0.00294341
0x1003247c  xor     eax, ebp
0x1003247e  push    eax
0x1003247f  lea     eax, [ebp - 0xc]
0x10032482  mov     dword ptr fs:[0], eax
0x10032488  mov     dword ptr [ebp - 0x10], esp
0x1003248b  mov     dword ptr [ebp - 4], 0
0x10032492  mov     eax, dword ptr [ebp + 0x14]
0x10032495  sub     eax, 1
0x10032498  je      0x100324a4
0x1003249a  sub     eax, 2
0x1003249d  je      0x100324a4
0x1003249f  sub     eax, 1
0x100324a2  jne     0x100324ea
0x100324a4  mov     esi, dword ptr [ebp + 0x10]
0x100324a7  mov     ecx, esi
0x100324a9  call    dword ptr [0x100cee38]
0x100324af  cmp     eax, 3
0x100324b2  jl      0x100324ea
0x100324b4  mov     ecx, esi
0x100324b6  call    dword ptr [0x100cee44]
0x100324bc  mov     eax, dword ptr [0x101491c8]  ; a"+2d2l2y2"
0x100324c1  mov     eax, dword ptr [eax + 0x54]
0x100324c4  add     eax, 0x28
0x100324c7  push    eax
0x100324c8  push    0x1d8
0x100324cd  call    0x10015710
0x100324d2  add     esp, 8
0x100324d5  test    eax, eax
0x100324d7  je      0x100324e2
0x100324d9  push    esi
0x100324da  mov     ecx, eax
0x100324dc  call    dword ptr [0x100cee94]
0x100324e2  mov     ecx, esi
0x100324e4  call    dword ptr [0x100cee44]
0x100324ea  mov     dword ptr [ebp - 4], 0xffffffff
0x100324f1  mov     ecx, dword ptr [ebp - 0xc]
0x100324f4  mov     dword ptr fs:[0], ecx
0x100324fb  pop     ecx
0x100324fc  pop     edi
0x100324fd  pop     esi
0x100324fe  pop     ebx
0x100324ff  mov     esp, ebp
0x10032501  pop     ebp
0x10032502  ret     

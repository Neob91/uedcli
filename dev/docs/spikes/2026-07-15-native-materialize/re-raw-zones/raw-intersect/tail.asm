0x10035ab3  push    1
0x10035ab5  push    1
0x10035ab7  mov     ecx, edx
0x10035ab9  call    dword ptr [0x100cee24]
0x10035abf  xor     esi, esi
0x10035ac1  mov     dword ptr [ebp - 0x3c8], esi
0x10035ac7  mov     eax, dword ptr [edi + 0xac]
0x10035acd  mov     ecx, dword ptr [eax + 0x54]
0x10035ad0  cmp     esi, dword ptr [ecx + 0x2c]
0x10035ad3  jge     0x10035b23
0x10035ad5  imul    eax, esi, 0x1d8
0x10035adb  add     eax, dword ptr [ecx + 0x28]
0x10035ade  push    eax
0x10035adf  lea     ecx, [ebp - 0x1ec]
0x10035ae5  call    dword ptr [0x100cee94]
0x10035aeb  mov     eax, dword ptr [ebp - 0x3cc]
0x10035af1  mov     dword ptr [0x101491c8], eax  ; a"+2d2l2y2"
0x10035af6  lea     eax, [ebp - 0x1ec]
0x10035afc  push    eax
0x10035afd  push    dword ptr [ebp - 0x3d0]
0x10035b03  mov     eax, 0x10032390
0x10035b08  cmp     dword ptr [ebp - 0x3d4], 3
0x10035b0f  mov     ecx, 0x100339e0
0x10035b14  cmove   eax, ecx
0x10035b17  push    eax
0x10035b18  call    0x10031f50
0x10035b1d  add     esp, 0xc
0x10035b20  inc     esi
0x10035b21  jmp     0x10035ac1
0x10035b23  mov     esi, dword ptr [ebp - 0x3cc]
0x10035b29  mov     eax, dword ptr [esi + 0x54]
0x10035b2c  mov     eax, dword ptr [eax + 0x2c]
0x10035b2f  mov     dword ptr [ebp - 0x3e8], eax
0x10035b35  jmp     0x10035b3d
0x10035b37  mov     esi, dword ptr [ebp - 0x3cc]
0x10035b3d  mov     eax, dword ptr [ebp - 0x3d0]
0x10035b43  cmp     dword ptr [eax + 0x5c], 0
0x10035b47  je      0x10035c00
0x10035b4d  test    byte ptr [ebp + 0x10], 0x28
0x10035b51  jne     0x10035c00
0x10035b57  cmp     dword ptr [ebp - 0x3dc], 0xc8
0x10035b61  jle     0x10035b81
0x10035b63  mov     eax, dword ptr [0x100ce884]
0x10035b68  mov     eax, dword ptr [eax]
0x10035b6a  mov     ecx, dword ptr [eax]
0x10035b6c  push    0x100dc4f0
0x10035b71  push    0x100d0bf4
0x10035b76  push    0
0x10035b78  push    0
0x10035b7a  push    eax
0x10035b7b  call    dword ptr [ecx + 0x10]
0x10035b7e  add     esp, 0x14
0x10035b81  mov     eax, dword ptr [edi]
0x10035b83  push    0
0x10035b85  push    1
0x10035b87  push    0
0x10035b89  push    0
0x10035b8b  push    dword ptr [edi + 0xac]
0x10035b91  mov     ecx, edi
0x10035b93  call    dword ptr [eax + 0x1fc]
0x10035b99  cmp     dword ptr [ebp - 0x3dc], 0xc8
0x10035ba3  jle     0x10035bc3
0x10035ba5  mov     eax, dword ptr [0x100ce884]
0x10035baa  mov     eax, dword ptr [eax]
0x10035bac  mov     ecx, dword ptr [eax]
0x10035bae  push    0x100dc50c
0x10035bb3  push    0x100d0bf4
0x10035bb8  push    0
0x10035bba  push    0
0x10035bbc  push    eax
0x10035bbd  call    dword ptr [ecx + 0x10]
0x10035bc0  add     esp, 0x14
0x10035bc3  mov     dword ptr [0x101491c8], esi  ; a"+2d2l2y2"
0x10035bc9  mov     ecx, dword ptr [edi + 0xac]
0x10035bcf  mov     esi, dword ptr [0x100cee8c]
0x10035bd5  call    esi
0x10035bd7  mov     ecx, dword ptr [edi + 0xac]
0x10035bdd  call    esi
0x10035bdf  mov     ecx, dword ptr [edi + 0xac]
0x10035be5  lea     eax, [ecx + 0x44]
0x10035be8  push    eax
0x10035be9  push    0
0x10035beb  push    dword ptr [ebp - 0x3d4]
0x10035bf1  push    ecx
0x10035bf2  push    dword ptr [ebp - 0x3d0]
0x10035bf8  call    0x10033250
0x10035bfd  add     esp, 0x14
0x10035c00  mov     edx, dword ptr [ebp - 0x3d4]
0x10035c06  cmp     edx, 3
0x10035c09  je      0x10035c14
0x10035c0b  cmp     edx, 4
0x10035c0e  jne     0x10035dc7
0x10035c14  cmp     dword ptr [ebp - 0x3dc], 0xc8
0x10035c1e  jle     0x10035c3e
0x10035c20  mov     eax, dword ptr [0x100ce884]
0x10035c25  mov     eax, dword ptr [eax]
0x10035c27  mov     ecx, dword ptr [eax]
0x10035c29  push    0x100dc52c
0x10035c2e  push    0x100d0bf4

0x10033398  mov     eax, dword ptr [eax + 0x1f8]
0x1003339e  call    eax
0x100333a0  mov     edx, dword ptr [ebp - 0x1f0]
0x100333a6  test    eax, eax
0x100333a8  jle     0x100334fd
0x100333ae  mov     eax, dword ptr [ebp - 0x204]
0x100333b4  shl     eax, 6
0x100333b7  mov     dword ptr [ebp - 0x204], eax
0x100333bd  mov     ecx, dword ptr [edx + 0x98]
0x100333c3  mov     eax, dword ptr [ecx + eax + 0x24]
0x100333c7  mov     dword ptr [ebp - 0x38], eax
0x100333ca  mov     eax, dword ptr [ebp - 0x204]
0x100333d0  mov     eax, dword ptr [ecx + eax + 0x1c]
0x100333d4  mov     dword ptr [ebp - 0x24], eax
0x100333d7  mov     ecx, dword ptr [ebp - 0x1f4]
0x100333dd  cmp     ecx, 1
0x100333e0  je      0x10033433
0x100333e2  cmp     ecx, 2
0x100333e5  je      0x10033433
0x100333e7  cmp     ecx, 3
0x100333ea  jne     0x1003340b
0x100333ec  lea     eax, [ebp - 0x1ec]
0x100333f2  push    eax
0x100333f3  push    dword ptr [ebp - 0x1f8]
0x100333f9  push    0x10033ab0
0x100333fe  call    0x10031f50
0x10033403  add     esp, 0xc
0x10033406  jmp     0x100334f7
0x1003340b  cmp     ecx, 4
0x1003340e  jne     0x10033503
0x10033414  lea     eax, [ebp - 0x1ec]
0x1003341a  push    eax
0x1003341b  push    dword ptr [ebp - 0x1f8]
0x10033421  push    0x10032460
0x10033426  call    0x10031f50
0x1003342b  add     esp, 0xc
0x1003342e  jmp     0x100334f7
0x10033433  mov     dword ptr [0x101491bc], esi
0x10033439  mov     dword ptr [0x101491c8], edx  ; a"+2d2l2y2"
0x1003343f  mov     dword ptr [0x101491b8], 0
0x10033449  mov     eax, dword ptr [edx + 0x5c]
0x1003344c  mov     dword ptr [0x101491c4], eax
0x10033451  mov     dword ptr [0x101491c0], esi
0x10033457  shl     esi, 6
0x1003345a  mov     eax, dword ptr [edi]
0x1003345c  mov     esi, dword ptr [esi + eax + 0x28]
0x10033460  cmp     esi, -1
0x10033463  jne     0x10033451

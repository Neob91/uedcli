0x10015090 +0     55                       push     ebp
0x10015091 +1     8b ec                    mov      ebp, esp
0x10015093 +3     6a ff                    push     -1
0x10015095 +5     68 91 34 03 10           push     0x10033491
0x1001509a +a     64 a1 00 00 00 00        mov      eax, dword ptr fs:[0]
0x100150a0 +10    50                       push     eax
0x100150a1 +11    81 ec 68 05 00 00        sub      esp, 0x568
0x100150a7 +17    a1 3c 60 04 10           mov      eax, dword ptr [0x1004603c]   ; [0x1004603c] f32=-0.002943414729088545
0x100150ac +1c    33 c5                    xor      eax, ebp
0x100150ae +1e    89 45 ec                 mov      dword ptr [ebp - 0x14], eax
0x100150b1 +21    53                       push     ebx
0x100150b2 +22    56                       push     esi
0x100150b3 +23    57                       push     edi
0x100150b4 +24    50                       push     eax
0x100150b5 +25    8d 45 f4                 lea      eax, [ebp - 0xc]
0x100150b8 +28    64 a3 00 00 00 00        mov      dword ptr fs:[0], eax
0x100150be +2e    89 65 f0                 mov      dword ptr [ebp - 0x10], esp
0x100150c1 +31    89 4d a4                 mov      dword ptr [ebp - 0x5c], ecx
0x100150c4 +34    8b 75 08                 mov      esi, dword ptr [ebp + 8]
0x100150c7 +37    89 75 c4                 mov      dword ptr [ebp - 0x3c], esi
0x100150ca +3a    c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x100150d1 +41    9b                       wait     
0x100150d2 +42    8b 3e                    mov      edi, dword ptr [esi]
0x100150d4 +44    89 7d c0                 mov      dword ptr [ebp - 0x40], edi
0x100150d7 +47    89 bd 88 fe ff ff        mov      dword ptr [ebp - 0x178], edi
0x100150dd +4d    8b 46 04                 mov      eax, dword ptr [esi + 4]
0x100150e0 +50    8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x100150e6 +56    89 45 a0                 mov      dword ptr [ebp - 0x60], eax
0x100150e9 +59    89 85 8c fe ff ff        mov      dword ptr [ebp - 0x174], eax
0x100150ef +5f    83 78 5c 00              cmp      dword ptr [eax + 0x5c], 0
0x100150f3 +63    7f 1b                    jg       0x10015110
0x100150f5 +65    68 97 09 00 00           push     0x997   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_Environment|PF_FakeBackdrop|PF_TwoSided|PF_NoSmooth
0x100150fa +6a    68 a0 6b 03 10           push     0x10036ba0
0x100150ff +6f    68 e8 6d 03 10           push     0x10036de8
0x10015104 +74    ff 15 84 41 03 10        call     dword ptr [0x10034184]   ; -> Core.dll!?appFailAssert@@YAXPBD0H@Z
0x1001510a +7a    83 c4 0c                 add      esp, 0xc
0x1001510d +7d    8b 4d a4                 mov      ecx, dword ptr [ebp - 0x5c]
0x10015110 +80    8b 76 10                 mov      esi, dword ptr [esi + 0x10]
0x10015113 +83    85 f6                    test     esi, esi
0x10015115 +85    74 0e                    je       0x10015125
0x10015117 +87    56                       push     esi
0x10015118 +88    e8 73 ff ff ff           call     0x10015090   ; -> ?DrawFrame@URender@@QAEXPAUFSceneNode@@@Z
0x1001511d +8d    8b 76 0c                 mov      esi, dword ptr [esi + 0xc]
0x10015120 +90    8b 4d a4                 mov      ecx, dword ptr [ebp - 0x5c]
0x10015123 +93    eb ee                    jmp      0x10015113
0x10015125 +95    8b 4f 5c                 mov      ecx, dword ptr [edi + 0x5c]
0x10015128 +98    8b 01                    mov      eax, dword ptr [ecx]
0x1001512a +9a    8b 75 c4                 mov      esi, dword ptr [ebp - 0x3c]
0x1001512d +9d    56                       push     esi
0x1001512e +9e    ff 90 ac 00 00 00        call     dword ptr [eax + 0xac]
0x10015134 +a4    83 be 98 00 00 00 00     cmp      dword ptr [esi + 0x98], 0
0x1001513b +ab    74 0c                    je       0x10015149
0x1001513d +ad    8b 4f 5c                 mov      ecx, dword ptr [edi + 0x5c]
0x10015140 +b0    8b 01                    mov      eax, dword ptr [ecx]
0x10015142 +b2    56                       push     esi
0x10015143 +b3    ff 90 90 00 00 00        call     dword ptr [eax + 0x90]
0x10015149 +b9    33 ff                    xor      edi, edi
0x1001514b +bb    89 7d e0                 mov      dword ptr [ebp - 0x20], edi
0x1001514e +be    89 7d e4                 mov      dword ptr [ebp - 0x1c], edi
0x10015151 +c1    89 7d e8                 mov      dword ptr [ebp - 0x18], edi
0x10015154 +c4    33 c9                    xor      ecx, ecx
0x10015156 +c6    89 4d ac                 mov      dword ptr [ebp - 0x54], ecx
0x10015159 +c9    83 f9 03                 cmp      ecx, 3   ; PF: PF_Invisible|PF_Masked
0x1001515c +cc    7d 1f                    jge      0x1001517d
0x1001515e +ce    8b 94 8e 98 00 00 00     mov      edx, dword ptr [esi + ecx*4 + 0x98]
0x10015165 +d5    85 d2                    test     edx, edx
0x10015167 +d7    74 11                    je       0x1001517a
0x10015169 +d9    8b 44 8d e0              mov      eax, dword ptr [ebp + ecx*4 - 0x20]
0x1001516d +dd    40                       inc      eax
0x1001516e +de    89 44 8d e0              mov      dword ptr [ebp + ecx*4 - 0x20], eax
0x10015172 +e2    8b 52 38                 mov      edx, dword ptr [edx + 0x38]
0x10015175 +e5    8b 7d e0                 mov      edi, dword ptr [ebp - 0x20]
0x10015178 +e8    eb eb                    jmp      0x10015165
0x1001517a +ea    41                       inc      ecx
0x1001517b +eb    eb d9                    jmp      0x10015156
0x1001517d +ed    6a 10                    push     0x10   ; PF: PF_Environment
0x1001517f +ef    8d 04 bd 00 00 00 00     lea      eax, [edi*4]
0x10015186 +f6    50                       push     eax
0x10015187 +f7    8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x1001518d +fd    ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x10015193 +103   8b f0                    mov      esi, eax
0x10015195 +105   89 75 d4                 mov      dword ptr [ebp - 0x2c], esi
0x10015198 +108   6a 10                    push     0x10   ; PF: PF_Environment
0x1001519a +10a   8b 55 e4                 mov      edx, dword ptr [ebp - 0x1c]
0x1001519d +10d   c1 e2 02                 shl      edx, 2
0x100151a0 +110   52                       push     edx
0x100151a1 +111   8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x100151a7 +117   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x100151ad +11d   89 45 d8                 mov      dword ptr [ebp - 0x28], eax
0x100151b0 +120   6a 10                    push     0x10   ; PF: PF_Environment
0x100151b2 +122   8b 55 e8                 mov      edx, dword ptr [ebp - 0x18]
0x100151b5 +125   c1 e2 02                 shl      edx, 2
0x100151b8 +128   52                       push     edx
0x100151b9 +129   8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x100151bf +12f   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x100151c5 +135   89 45 dc                 mov      dword ptr [ebp - 0x24], eax
0x100151c8 +138   89 75 c8                 mov      dword ptr [ebp - 0x38], esi
0x100151cb +13b   8b 4d d8                 mov      ecx, dword ptr [ebp - 0x28]
0x100151ce +13e   89 4d cc                 mov      dword ptr [ebp - 0x34], ecx
0x100151d1 +141   89 45 d0                 mov      dword ptr [ebp - 0x30], eax
0x100151d4 +144   33 d2                    xor      edx, edx
0x100151d6 +146   89 55 ac                 mov      dword ptr [ebp - 0x54], edx
0x100151d9 +149   83 fa 03                 cmp      edx, 3   ; PF: PF_Invisible|PF_Masked
0x100151dc +14c   7d 23                    jge      0x10015201
0x100151de +14e   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x100151e1 +151   8b 8c 90 98 00 00 00     mov      ecx, dword ptr [eax + edx*4 + 0x98]
0x100151e8 +158   85 c9                    test     ecx, ecx
0x100151ea +15a   74 12                    je       0x100151fe
0x100151ec +15c   8b 44 95 c8              mov      eax, dword ptr [ebp + edx*4 - 0x38]
0x100151f0 +160   89 08                    mov      dword ptr [eax], ecx
0x100151f2 +162   83 c0 04                 add      eax, 4
0x100151f5 +165   89 44 95 c8              mov      dword ptr [ebp + edx*4 - 0x38], eax
0x100151f9 +169   8b 49 38                 mov      ecx, dword ptr [ecx + 0x38]
0x100151fc +16c   eb ea                    jmp      0x100151e8
0x100151fe +16e   42                       inc      edx
0x100151ff +16f   eb d5                    jmp      0x100151d6
0x10015201 +171   33 f6                    xor      esi, esi
0x10015203 +173   89 b5 0c ff ff ff        mov      dword ptr [ebp - 0xf4], esi
0x10015209 +179   8b 4d d4                 mov      ecx, dword ptr [ebp - 0x2c]
0x1001520c +17c   0f 1f 40 00              nop      dword ptr [eax]
0x10015210 +180   8b c7                    mov      eax, edi
0x10015212 +182   99                       cdq      
0x10015213 +183   2b c2                    sub      eax, edx
0x10015215 +185   d1 f8                    sar      eax, 1
0x10015217 +187   3b f0                    cmp      esi, eax
0x10015219 +189   7d 23                    jge      0x1001523e
0x1001521b +18b   8b d7                    mov      edx, edi
0x1001521d +18d   2b d6                    sub      edx, esi
0x1001521f +18f   8b 04 b1                 mov      eax, dword ptr [ecx + esi*4]
0x10015222 +192   8b 4c 91 fc              mov      ecx, dword ptr [ecx + edx*4 - 4]
0x10015226 +196   8b 7d d4                 mov      edi, dword ptr [ebp - 0x2c]
0x10015229 +199   89 0c b7                 mov      dword ptr [edi + esi*4], ecx
0x1001522c +19c   8b cf                    mov      ecx, edi
0x1001522e +19e   89 44 91 fc              mov      dword ptr [ecx + edx*4 - 4], eax
0x10015232 +1a2   8b 7d e0                 mov      edi, dword ptr [ebp - 0x20]
0x10015235 +1a5   46                       inc      esi
0x10015236 +1a6   89 b5 0c ff ff ff        mov      dword ptr [ebp - 0xf4], esi
0x1001523c +1ac   eb d2                    jmp      0x10015210
0x1001523e +1ae   ff 75 e4                 push     dword ptr [ebp - 0x1c]
0x10015241 +1b1   ff 75 d8                 push     dword ptr [ebp - 0x28]
0x10015244 +1b4   e8 77 c9 ff ff           call     0x10011bc0   ; -> sub_11bc0
0x10015249 +1b9   83 c4 08                 add      esp, 8
0x1001524c +1bc   33 ff                    xor      edi, edi
0x1001524e +1be   89 7d ac                 mov      dword ptr [ebp - 0x54], edi
0x10015251 +1c1   8b 75 c0                 mov      esi, dword ptr [ebp - 0x40]
0x10015254 +1c4   8d 4e 30                 lea      ecx, [esi + 0x30]
0x10015257 +1c7   89 4d b0                 mov      dword ptr [ebp - 0x50], ecx
0x1001525a +1ca   f2 0f 10 05 d8 51 03 10  movsd    xmm0, qword ptr [0x100351d8]   ; [0x100351d8] f32=0.0
0x10015262 +1d2   f2 0f 11 85 68 ff ff ff  movsd    qword ptr [ebp - 0x98], xmm0
0x1001526a +1da   8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x1001526d +1dd   0f 1f 00                 nop      dword ptr [eax]
0x10015270 +1e0   83 ff 03                 cmp      edi, 3   ; PF: PF_Invisible|PF_Masked
0x10015273 +1e3   0f 8d f6 0a 00 00        jge      0x10015d6f
0x10015279 +1e9   8b 44 bd d4              mov      eax, dword ptr [ebp + edi*4 - 0x2c]
0x1001527d +1ed   89 85 28 ff ff ff        mov      dword ptr [ebp - 0xd8], eax
0x10015283 +1f3   8d 56 30                 lea      edx, [esi + 0x30]
0x10015286 +1f6   89 55 b0                 mov      dword ptr [ebp - 0x50], edx
0x10015289 +1f9   89 45 8c                 mov      dword ptr [ebp - 0x74], eax
0x1001528c +1fc   3b 44 bd c8              cmp      eax, dword ptr [ebp + edi*4 - 0x38]
0x10015290 +200   0f 83 c5 09 00 00        jae      0x10015c5b
0x10015296 +206   8b 30                    mov      esi, dword ptr [eax]
0x10015298 +208   89 75 b4                 mov      dword ptr [ebp - 0x4c], esi
0x1001529b +20b   89 b5 90 fe ff ff        mov      dword ptr [ebp - 0x170], esi
0x100152a1 +211   8b 7e 04                 mov      edi, dword ptr [esi + 4]
0x100152a4 +214   c1 e7 06                 shl      edi, 6
0x100152a7 +217   8b 45 a0                 mov      eax, dword ptr [ebp - 0x60]
0x100152aa +21a   03 b8 98 00 00 00        add      edi, dword ptr [eax + 0x98]
0x100152b0 +220   89 7d bc                 mov      dword ptr [ebp - 0x44], edi
0x100152b3 +223   89 bd 84 fe ff ff        mov      dword ptr [ebp - 0x17c], edi
0x100152b9 +229   8b 0f                    mov      ecx, dword ptr [edi]
0x100152bb +22b   85 c9                    test     ecx, ecx
0x100152bd +22d   74 17                    je       0x100152d6
0x100152bf +22f   8b 45 c0                 mov      eax, dword ptr [ebp - 0x40]
0x100152c2 +232   ff b0 ac 00 00 00        push     dword ptr [eax + 0xac]
0x100152c8 +238   ff b0 a8 00 00 00        push     dword ptr [eax + 0xa8]
0x100152ce +23e   ff 15 60 43 03 10        call     dword ptr [0x10034360]   ; -> Engine.dll!?Get@UTexture@@QAEPAV1@VFTime@@@Z
0x100152d4 +244   eb 0b                    jmp      0x100152e1
0x100152d6 +246   8b 02                    mov      eax, dword ptr [edx]
0x100152d8 +248   8b 40 64                 mov      eax, dword ptr [eax + 0x64]
0x100152db +24b   8b 80 08 04 00 00        mov      eax, dword ptr [eax + 0x408]
0x100152e1 +251   89 45 9c                 mov      dword ptr [ebp - 0x64], eax
0x100152e4 +254   0f bf 47 20              movsx    eax, word ptr [edi + 0x20]
0x100152e8 +258   66 0f 6e c0              movd     xmm0, eax
0x100152ec +25c   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x100152ef +25f   f3 0f 11 45 b8           movss    dword ptr [ebp - 0x48], xmm0
0x100152f4 +264   f3 0f 11 85 60 ff ff ff  movss    dword ptr [ebp - 0xa0], xmm0
0x100152fc +26c   f7 47 04 00 02 00 00     test     dword ptr [edi + 4], 0x200   ; PF: PF_AutoUPan
0x10015303 +273   74 65                    je       0x1001536a
0x10015305 +275   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x10015308 +278   8b 48 04                 mov      ecx, dword ptr [eax + 4]
0x1001530b +27b   ff 15 64 43 03 10        call     dword ptr [0x10034364]   ; -> Engine.dll!?GetLevelInfo@ULevel@@QAEPAVALevelInfo@@XZ
0x10015311 +281   f3 0f 10 88 6c 03 00 00  movss    xmm1, dword ptr [eax + 0x36c]
0x10015319 +289   f3 0f 59 0d 30 52 03 10  mulss    xmm1, dword ptr [0x10035230]   ; [0x10035230] f32=35.0
0x10015321 +291   8b 46 34                 mov      eax, dword ptr [esi + 0x34]
0x10015324 +294   f3 0f 59 88 90 02 00 00  mulss    xmm1, dword ptr [eax + 0x290]
0x1001532c +29c   f3 0f 59 0d 38 52 03 10  mulss    xmm1, dword ptr [0x10035238]   ; [0x10035238] f32=256.0
0x10015334 +2a4   f3 0f 11 8d 74 ff ff ff  movss    dword ptr [ebp - 0x8c], xmm1
0x1001533c +2ac   f3 0f 2d c1              cvtss2si eax, xmm1
0x10015340 +2b0   25 ff ff 03 00           and      eax, 0x3ffff   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Environment|PF_Semisolid|PF_Modulated|PF_FakeBackdrop|PF_TwoSided|PF_AutoUPan|PF_AutoVPan|PF_NoSmooth|PF_BigWavy|PF_SmallWavy|PF_Flat|PF_LowShadowDetail|PF_NoMerge|PF_CloudWavy
0x10015345 +2b5   66 0f 6e c0              movd     xmm0, eax
0x10015349 +2b9   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x1001534c +2bc   f3 0f 59 05 54 51 03 10  mulss    xmm0, dword ptr [0x10035154]   ; [0x10035154] f32=0.00390625
0x10015354 +2c4   f3 0f 10 4d b8           movss    xmm1, dword ptr [ebp - 0x48]
0x10015359 +2c9   f3 0f 58 c8              addss    xmm1, xmm0
0x1001535d +2cd   f3 0f 11 4d b8           movss    dword ptr [ebp - 0x48], xmm1
0x10015362 +2d2   f3 0f 11 8d 60 ff ff ff  movss    dword ptr [ebp - 0xa0], xmm1
0x1001536a +2da   0f bf 47 22              movsx    eax, word ptr [edi + 0x22]
0x1001536e +2de   66 0f 6e c0              movd     xmm0, eax
0x10015372 +2e2   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10015375 +2e5   f3 0f 11 45 a8           movss    dword ptr [ebp - 0x58], xmm0
0x1001537a +2ea   f3 0f 11 85 5c ff ff ff  movss    dword ptr [ebp - 0xa4], xmm0
0x10015382 +2f2   f7 47 04 00 04 00 00     test     dword ptr [edi + 4], 0x400   ; PF: PF_AutoVPan
0x10015389 +2f9   74 61                    je       0x100153ec
0x1001538b +2fb   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x1001538e +2fe   8b 48 04                 mov      ecx, dword ptr [eax + 4]
0x10015391 +301   ff 15 64 43 03 10        call     dword ptr [0x10034364]   ; -> Engine.dll!?GetLevelInfo@ULevel@@QAEPAVALevelInfo@@XZ
0x10015397 +307   f3 0f 10 88 6c 03 00 00  movss    xmm1, dword ptr [eax + 0x36c]
0x1001539f +30f   f3 0f 59 0d 30 52 03 10  mulss    xmm1, dword ptr [0x10035230]   ; [0x10035230] f32=35.0
0x100153a7 +317   8b 46 34                 mov      eax, dword ptr [esi + 0x34]
0x100153aa +31a   f3 0f 59 88 94 02 00 00  mulss    xmm1, dword ptr [eax + 0x294]
0x100153b2 +322   f3 0f 59 0d 38 52 03 10  mulss    xmm1, dword ptr [0x10035238]   ; [0x10035238] f32=256.0
0x100153ba +32a   f3 0f 11 8d 54 ff ff ff  movss    dword ptr [ebp - 0xac], xmm1
0x100153c2 +332   f3 0f 2d c1              cvtss2si eax, xmm1
0x100153c6 +336   25 ff ff 03 00           and      eax, 0x3ffff   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Environment|PF_Semisolid|PF_Modulated|PF_FakeBackdrop|PF_TwoSided|PF_AutoUPan|PF_AutoVPan|PF_NoSmooth|PF_BigWavy|PF_SmallWavy|PF_Flat|PF_LowShadowDetail|PF_NoMerge|PF_CloudWavy
0x100153cb +33b   66 0f 6e c0              movd     xmm0, eax
0x100153cf +33f   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x100153d2 +342   f3 0f 59 05 54 51 03 10  mulss    xmm0, dword ptr [0x10035154]   ; [0x10035154] f32=0.00390625
0x100153da +34a   f3 0f 58 45 a8           addss    xmm0, dword ptr [ebp - 0x58]
0x100153df +34f   f3 0f 11 45 a8           movss    dword ptr [ebp - 0x58], xmm0
0x100153e4 +354   f3 0f 11 85 5c ff ff ff  movss    dword ptr [ebp - 0xa4], xmm0
0x100153ec +35c   f7 47 04 00 20 00 00     test     dword ptr [edi + 4], 0x2000   ; PF: PF_SmallWavy
0x100153f3 +363   0f 84 f8 00 00 00        je       0x100154f1
0x100153f9 +369   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x100153fc +36c   8b 48 04                 mov      ecx, dword ptr [eax + 4]
0x100153ff +36f   ff 15 64 43 03 10        call     dword ptr [0x10034364]   ; -> Engine.dll!?GetLevelInfo@ULevel@@QAEPAVALevelInfo@@XZ
0x10015405 +375   f3 0f 10 80 6c 03 00 00  movss    xmm0, dword ptr [eax + 0x36c]
0x1001540d +37d   f3 0f 11 45 98           movss    dword ptr [ebp - 0x68], xmm0
0x10015412 +382   f3 0f 59 05 f8 6e 03 10  mulss    xmm0, dword ptr [0x10036ef8]   ; [0x10036ef8] f32=2.299999952316284
0x1001541a +38a   0f 5a c0                 cvtps2pd xmm0, xmm0
0x1001541d +38d   f2 0f 11 45 e4           movsd    qword ptr [ebp - 0x1c], xmm0
0x10015422 +392   83 ec 08                 sub      esp, 8
0x10015425 +395   f2 0f 11 04 24           movsd    qword ptr [esp], xmm0
0x1001542a +39a   ff 15 9c 42 03 10        call     dword ptr [0x1003429c]   ; -> Core.dll!?appCos@@YANN@Z
0x10015430 +3a0   dc 0d c8 51 03 10        fmul     qword ptr [0x100351c8]   ; [0x100351c8] f32=0.0
0x10015436 +3a6   dd 9d 50 ff ff ff        fstp     qword ptr [ebp - 0xb0]
0x1001543c +3ac   f3 0f 10 45 98           movss    xmm0, dword ptr [ebp - 0x68]
0x10015441 +3b1   0f 5a c0                 cvtps2pd xmm0, xmm0
0x10015444 +3b4   f2 0f 11 04 24           movsd    qword ptr [esp], xmm0
0x10015449 +3b9   ff 15 cc 41 03 10        call     dword ptr [0x100341cc]   ; -> Core.dll!?appSin@@YANN@Z
0x1001544f +3bf   dd 9d 70 ff ff ff        fstp     qword ptr [ebp - 0x90]
0x10015455 +3c5   f2 0f 10 8d 70 ff ff ff  movsd    xmm1, qword ptr [ebp - 0x90]
0x1001545d +3cd   f2 0f 59 8d 68 ff ff ff  mulsd    xmm1, qword ptr [ebp - 0x98]
0x10015465 +3d5   f2 0f 58 8d 50 ff ff ff  addsd    xmm1, qword ptr [ebp - 0xb0]
0x1001546d +3dd   f3 0f 10 45 b8           movss    xmm0, dword ptr [ebp - 0x48]
0x10015472 +3e2   0f 5a c0                 cvtps2pd xmm0, xmm0
0x10015475 +3e5   f2 0f 58 c8              addsd    xmm1, xmm0
0x10015479 +3e9   66 0f 5a c1              cvtpd2ps xmm0, xmm1
0x1001547d +3ed   f3 0f 11 45 b8           movss    dword ptr [ebp - 0x48], xmm0
0x10015482 +3f2   f3 0f 11 85 60 ff ff ff  movss    dword ptr [ebp - 0xa0], xmm0
0x1001548a +3fa   f2 0f 10 45 e4           movsd    xmm0, qword ptr [ebp - 0x1c]
0x1001548f +3ff   f2 0f 11 04 24           movsd    qword ptr [esp], xmm0
0x10015494 +404   ff 15 cc 41 03 10        call     dword ptr [0x100341cc]   ; -> Core.dll!?appSin@@YANN@Z
0x1001549a +40a   dc 0d c8 51 03 10        fmul     qword ptr [0x100351c8]   ; [0x100351c8] f32=0.0
0x100154a0 +410   dd 9d 70 ff ff ff        fstp     qword ptr [ebp - 0x90]
0x100154a6 +416   f3 0f 10 45 98           movss    xmm0, dword ptr [ebp - 0x68]
0x100154ab +41b   0f 5a c0                 cvtps2pd xmm0, xmm0
0x100154ae +41e   f2 0f 11 04 24           movsd    qword ptr [esp], xmm0
0x100154b3 +423   ff 15 9c 42 03 10        call     dword ptr [0x1003429c]   ; -> Core.dll!?appCos@@YANN@Z
0x100154b9 +429   83 c4 08                 add      esp, 8
0x100154bc +42c   dd 5d e4                 fstp     qword ptr [ebp - 0x1c]
0x100154bf +42f   f2 0f 10 4d e4           movsd    xmm1, qword ptr [ebp - 0x1c]
0x100154c4 +434   f2 0f 59 8d 68 ff ff ff  mulsd    xmm1, qword ptr [ebp - 0x98]
0x100154cc +43c   f2 0f 58 8d 70 ff ff ff  addsd    xmm1, qword ptr [ebp - 0x90]
0x100154d4 +444   f3 0f 10 45 a8           movss    xmm0, dword ptr [ebp - 0x58]
0x100154d9 +449   0f 5a c0                 cvtps2pd xmm0, xmm0
0x100154dc +44c   f2 0f 58 c8              addsd    xmm1, xmm0
0x100154e0 +450   66 0f 5a c1              cvtpd2ps xmm0, xmm1
0x100154e4 +454   f3 0f 11 45 a8           movss    dword ptr [ebp - 0x58], xmm0
0x100154e9 +459   f3 0f 11 85 5c ff ff ff  movss    dword ptr [ebp - 0xa4], xmm0
0x100154f1 +461   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x100154f4 +464   8b 40 04                 mov      eax, dword ptr [eax + 4]
0x100154f7 +467   89 85 34 ff ff ff        mov      dword ptr [ebp - 0xcc], eax
0x100154fd +46d   8b 46 10                 mov      eax, dword ptr [esi + 0x10]
0x10015500 +470   89 85 2c ff ff ff        mov      dword ptr [ebp - 0xd4], eax
0x10015506 +476   0f 57 c0                 xorps    xmm0, xmm0
0x10015509 +479   0f 11 85 3c ff ff ff     movups   xmmword ptr [ebp - 0xc4], xmm0
0x10015510 +480   8b 46 34                 mov      eax, dword ptr [esi + 0x34]
0x10015513 +483   89 85 4c ff ff ff        mov      dword ptr [ebp - 0xb4], eax
0x10015519 +489   8b 55 9c                 mov      edx, dword ptr [ebp - 0x64]
0x1001551c +48c   8b 02                    mov      eax, dword ptr [edx]
0x1001551e +48e   8b 4d c0                 mov      ecx, dword ptr [ebp - 0x40]
0x10015521 +491   ff 71 5c                 push     dword ptr [ecx + 0x5c]
0x10015524 +494   6a ff                    push     -1
0x10015526 +496   ff b1 ac 00 00 00        push     dword ptr [ecx + 0xac]
0x1001552c +49c   ff b1 a8 00 00 00        push     dword ptr [ecx + 0xa8]
0x10015532 +4a2   8d 8d 3c fc ff ff        lea      ecx, [ebp - 0x3c4]
0x10015538 +4a8   51                       push     ecx
0x10015539 +4a9   8b ca                    mov      ecx, edx
0x1001553b +4ab   ff 50 54                 call     dword ptr [eax + 0x54]
0x1001553e +4ae   f3 0f 10 4d b8           movss    xmm1, dword ptr [ebp - 0x48]
0x10015543 +4b3   0f 57 0d f0 52 03 10     xorps    xmm1, xmmword ptr [0x100352f0]   ; [0x100352f0] f32=-0.0
0x1001554a +4ba   f3 0f 11 8d 74 fe ff ff  movss    dword ptr [ebp - 0x18c], xmm1
0x10015552 +4c2   f3 0f 10 45 a8           movss    xmm0, dword ptr [ebp - 0x58]
0x10015557 +4c7   0f 57 05 f0 52 03 10     xorps    xmm0, xmmword ptr [0x100352f0]   ; [0x100352f0] f32=-0.0
0x1001555e +4ce   f3 0f 11 85 78 fe ff ff  movss    dword ptr [ebp - 0x188], xmm0
0x10015566 +4d6   c7 85 7c fe ff ff 00 00 00 00 mov      dword ptr [ebp - 0x184], 0
0x10015570 +4e0   f3 0f 11 8d 50 fc ff ff  movss    dword ptr [ebp - 0x3b0], xmm1
0x10015578 +4e8   f3 0f 11 85 54 fc ff ff  movss    dword ptr [ebp - 0x3ac], xmm0
0x10015580 +4f0   c7 85 58 fc ff ff 00 00 00 00 mov      dword ptr [ebp - 0x3a8], 0
0x1001558a +4fa   8d 85 3c fc ff ff        lea      eax, [ebp - 0x3c4]
0x10015590 +500   89 85 38 ff ff ff        mov      dword ptr [ebp - 0xc8], eax
0x10015596 +506   8b 4d 9c                 mov      ecx, dword ptr [ebp - 0x64]
0x10015599 +509   8b 49 58                 mov      ecx, dword ptr [ecx + 0x58]
0x1001559c +50c   85 c9                    test     ecx, ecx
0x1001559e +50e   74 49                    je       0x100155e9
0x100155a0 +510   f7 85 2c ff ff ff 00 00 00 04 test     dword ptr [ebp - 0xd4], 0x4000000   ; PF: PF_Portal
0x100155aa +51a   75 3d                    jne      0x100155e9
0x100155ac +51c   a1 04 43 03 10           mov      eax, dword ptr [0x10034304]
0x100155b1 +521   8b 00                    mov      eax, dword ptr [eax]
0x100155b3 +523   85 c0                    test     eax, eax
0x100155b5 +525   74 32                    je       0x100155e9
0x100155b7 +527   83 78 7c 00              cmp      dword ptr [eax + 0x7c], 0
0x100155bb +52b   75 2c                    jne      0x100155e9
0x100155bd +52d   8b 01                    mov      eax, dword ptr [ecx]
0x100155bf +52f   8b 55 c0                 mov      edx, dword ptr [ebp - 0x40]
0x100155c2 +532   ff 72 5c                 push     dword ptr [edx + 0x5c]
0x100155c5 +535   6a ff                    push     -1
0x100155c7 +537   ff b2 ac 00 00 00        push     dword ptr [edx + 0xac]
0x100155cd +53d   ff b2 a8 00 00 00        push     dword ptr [edx + 0xa8]
0x100155d3 +543   8d 95 3c fb ff ff        lea      edx, [ebp - 0x4c4]
0x100155d9 +549   52                       push     edx
0x100155da +54a   ff 50 54                 call     dword ptr [eax + 0x54]
0x100155dd +54d   8d 85 3c fb ff ff        lea      eax, [ebp - 0x4c4]
0x100155e3 +553   89 85 44 ff ff ff        mov      dword ptr [ebp - 0xbc], eax
0x100155e9 +559   8b 4d 9c                 mov      ecx, dword ptr [ebp - 0x64]
0x100155ec +55c   8b 49 5c                 mov      ecx, dword ptr [ecx + 0x5c]
0x100155ef +55f   85 c9                    test     ecx, ecx
0x100155f1 +561   74 2c                    je       0x1001561f
0x100155f3 +563   8b 01                    mov      eax, dword ptr [ecx]
0x100155f5 +565   8b 55 c0                 mov      edx, dword ptr [ebp - 0x40]
0x100155f8 +568   ff 72 5c                 push     dword ptr [edx + 0x5c]
0x100155fb +56b   6a ff                    push     -1
0x100155fd +56d   ff b2 ac 00 00 00        push     dword ptr [edx + 0xac]
0x10015603 +573   ff b2 a8 00 00 00        push     dword ptr [edx + 0xa8]
0x10015609 +579   8d 95 bc fa ff ff        lea      edx, [ebp - 0x544]
0x1001560f +57f   52                       push     edx
0x10015610 +580   ff 50 54                 call     dword ptr [eax + 0x54]
0x10015613 +583   8d 85 bc fa ff ff        lea      eax, [ebp - 0x544]
0x10015619 +589   89 85 40 ff ff ff        mov      dword ptr [ebp - 0xc0], eax
0x1001561f +58f   8b 46 44                 mov      eax, dword ptr [esi + 0x44]
0x10015622 +592   89 85 20 fe ff ff        mov      dword ptr [ebp - 0x1e0], eax
0x10015628 +598   8d 46 14                 lea      eax, [esi + 0x14]
0x1001562b +59b   89 45 98                 mov      dword ptr [ebp - 0x68], eax
0x1001562e +59e   89 85 1c fe ff ff        mov      dword ptr [ebp - 0x1e4], eax
0x10015634 +5a4   8b 45 a0                 mov      eax, dword ptr [ebp - 0x60]
0x10015637 +5a7   8b 70 78                 mov      esi, dword ptr [eax + 0x78]
0x1001563a +5aa   8b 47 14                 mov      eax, dword ptr [edi + 0x14]
0x1001563d +5ad   8d 04 40                 lea      eax, [eax + eax*2]
0x10015640 +5b0   8d 3c 86                 lea      edi, [esi + eax*4]
0x10015643 +5b3   8b 4d bc                 mov      ecx, dword ptr [ebp - 0x44]
0x10015646 +5b6   8b 41 10                 mov      eax, dword ptr [ecx + 0x10]
0x10015649 +5b9   8d 04 40                 lea      eax, [eax + eax*2]
0x1001564c +5bc   8d 14 86                 lea      edx, [esi + eax*4]
0x1001564f +5bf   8b 41 08                 mov      eax, dword ptr [ecx + 8]
0x10015652 +5c2   8d 0c 40                 lea      ecx, [eax + eax*2]
0x10015655 +5c5   8b 45 a0                 mov      eax, dword ptr [ebp - 0x60]
0x10015658 +5c8   8b 80 88 00 00 00        mov      eax, dword ptr [eax + 0x88]
0x1001565e +5ce   8d 0c 88                 lea      ecx, [eax + ecx*4]
0x10015661 +5d1   8b 45 bc                 mov      eax, dword ptr [ebp - 0x44]
0x10015664 +5d4   8b 40 0c                 mov      eax, dword ptr [eax + 0xc]
0x10015667 +5d7   8d 04 40                 lea      eax, [eax + eax*2]
0x1001566a +5da   8d 04 86                 lea      eax, [esi + eax*4]
0x1001566d +5dd   50                       push     eax
0x1001566e +5de   57                       push     edi
0x1001566f +5df   52                       push     edx
0x10015670 +5e0   51                       push     ecx
0x10015671 +5e1   8d 8d 8c fa ff ff        lea      ecx, [ebp - 0x574]
0x10015677 +5e7   ff 15 20 42 03 10        call     dword ptr [0x10034220]   ; -> Core.dll!??0FCoords@@QAE@ABVFVector@@000@Z
0x1001567d +5ed   50                       push     eax
0x1001567e +5ee   8d 8d bc fd ff ff        lea      ecx, [ebp - 0x244]
0x10015684 +5f4   ff 15 2c 42 03 10        call     dword ptr [0x1003422c]   ; -> Core.dll!??4FCoords@@QAEAAV0@$$QAV0@@Z
0x1001568a +5fa   8b 45 bc                 mov      eax, dword ptr [ebp - 0x44]
0x1001568d +5fd   8b 7d c0                 mov      edi, dword ptr [ebp - 0x40]
0x10015690 +600   83 78 18 ff              cmp      dword ptr [eax + 0x18], -1
0x10015694 +604   74 55                    je       0x100156eb
0x10015696 +606   8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10015699 +609   8b 00                    mov      eax, dword ptr [eax]
0x1001569b +60b   83 b8 80 04 00 00 05     cmp      dword ptr [eax + 0x480], 5   ; PF: PF_Invisible|PF_Translucent
0x100156a2 +612   75 47                    jne      0x100156eb
0x100156a4 +614   8b 45 a0                 mov      eax, dword ptr [ebp - 0x60]
0x100156a7 +617   83 b8 ac 00 00 00 00     cmp      dword ptr [eax + 0xac], 0
0x100156ae +61e   74 3b                    je       0x100156eb
0x100156b0 +620   8b 47 18                 mov      eax, dword ptr [edi + 0x18]
0x100156b3 +623   8b 75 b4                 mov      esi, dword ptr [ebp - 0x4c]
0x100156b6 +626   83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x100156ba +62a   75 32                    jne      0x100156ee
0x100156bc +62c   8b 0d 04 60 04 10        mov      ecx, dword ptr [0x10046004]   ; data ?GLightManager@@3PAVFLightManagerBase@@A
0x100156c2 +632   8b 11                    mov      edx, dword ptr [ecx]
0x100156c4 +634   33 c0                    xor      eax, eax
0x100156c6 +636   39 45 ac                 cmp      dword ptr [ebp - 0x54], eax
0x100156c9 +639   0f 94 c0                 sete     al
0x100156cc +63c   50                       push     eax
0x100156cd +63d   8d 85 48 ff ff ff        lea      eax, [ebp - 0xb8]
0x100156d3 +643   50                       push     eax
0x100156d4 +644   8d 85 3c ff ff ff        lea      eax, [ebp - 0xc4]
0x100156da +64a   50                       push     eax
0x100156db +64b   56                       push     esi
0x100156dc +64c   8d 85 bc fd ff ff        lea      eax, [ebp - 0x244]
0x100156e2 +652   50                       push     eax
0x100156e3 +653   ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x100156e6 +656   ff 52 0c                 call     dword ptr [edx + 0xc]
0x100156e9 +659   eb 03                    jmp      0x100156ee
0x100156eb +65b   8b 75 b4                 mov      esi, dword ptr [ebp - 0x4c]
0x100156ee +65e   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x100156f1 +661   83 c0 34                 add      eax, 0x34
0x100156f4 +664   50                       push     eax
0x100156f5 +665   8d 8d bc fd ff ff        lea      ecx, [ebp - 0x244]
0x100156fb +66b   ff 15 70 42 03 10        call     dword ptr [0x10034270]   ; -> Core.dll!??XFCoords@@QAEAAV0@ABV0@@Z
0x10015701 +671   8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10015704 +674   8b 10                    mov      edx, dword ptr [eax]
0x10015706 +676   8b 82 80 04 00 00        mov      eax, dword ptr [edx + 0x480]
0x1001570c +67c   83 f8 03                 cmp      eax, 3   ; PF: PF_Invisible|PF_Masked
0x1001570f +67f   74 0e                    je       0x1001571f
0x10015711 +681   83 f8 04                 cmp      eax, 4   ; PF: PF_Translucent
0x10015714 +684   74 09                    je       0x1001571f
0x10015716 +686   83 f8 02                 cmp      eax, 2   ; PF: PF_Masked
0x10015719 +689   0f 85 46 02 00 00        jne      0x10015965
0x1001571f +68f   8b 42 68                 mov      eax, dword ptr [edx + 0x68]
0x10015722 +692   8b 88 98 00 00 00        mov      ecx, dword ptr [eax + 0x98]
0x10015728 +698   8b 06                    mov      eax, dword ptr [esi]
0x1001572a +69a   c1 e0 06                 shl      eax, 6
0x1001572d +69d   03 41 58                 add      eax, dword ptr [ecx + 0x58]
0x10015730 +6a0   8b 40 1c                 mov      eax, dword ptr [eax + 0x1c]
0x10015733 +6a3   c1 e0 06                 shl      eax, 6
0x10015736 +6a6   03 81 98 00 00 00        add      eax, dword ptr [ecx + 0x98]
0x1001573c +6ac   8b 08                    mov      ecx, dword ptr [eax]
0x1001573e +6ae   85 c9                    test     ecx, ecx
0x10015740 +6b0   74 16                    je       0x10015758
0x10015742 +6b2   ff b7 ac 00 00 00        push     dword ptr [edi + 0xac]
0x10015748 +6b8   ff b7 a8 00 00 00        push     dword ptr [edi + 0xa8]
0x1001574e +6be   ff 15 60 43 03 10        call     dword ptr [0x10034360]   ; -> Engine.dll!?Get@UTexture@@QAEPAV1@VFTime@@@Z
0x10015754 +6c4   8b d0                    mov      edx, eax
0x10015756 +6c6   eb 09                    jmp      0x10015761
0x10015758 +6c8   8b 42 64                 mov      eax, dword ptr [edx + 0x64]
0x1001575b +6cb   8b 90 08 04 00 00        mov      edx, dword ptr [eax + 0x408]
0x10015761 +6d1   8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10015764 +6d4   8b 00                    mov      eax, dword ptr [eax]
0x10015766 +6d6   8b 80 80 04 00 00        mov      eax, dword ptr [eax + 0x480]
0x1001576c +6dc   83 f8 03                 cmp      eax, 3   ; PF: PF_Invisible|PF_Masked
0x1001576f +6df   0f 85 85 00 00 00        jne      0x100157fa
0x10015775 +6e5   8b 4a 04                 mov      ecx, dword ptr [edx + 4]
0x10015778 +6e8   6b c1 43                 imul     eax, ecx, 0x43
0x1001577b +6eb   0f b6 c0                 movzx    eax, al
0x1001577e +6ee   66 0f 6e d0              movd     xmm2, eax
0x10015782 +6f2   0f 5b d2                 cvtdq2ps xmm2, xmm2
0x10015785 +6f5   f3 0f 11 95 68 fe ff ff  movss    dword ptr [ebp - 0x198], xmm2
0x1001578d +6fd   6b c1 5b                 imul     eax, ecx, 0x5b
0x10015790 +700   0f b6 c0                 movzx    eax, al
0x10015793 +703   66 0f 6e c8              movd     xmm1, eax
0x10015797 +707   0f 5b c9                 cvtdq2ps xmm1, xmm1
0x1001579a +70a   f3 0f 11 8d 6c fe ff ff  movss    dword ptr [ebp - 0x194], xmm1
0x100157a2 +712   6b c1 c7                 imul     eax, ecx, -0x39
0x100157a5 +715   0f b6 c0                 movzx    eax, al
0x100157a8 +718   66 0f 6e c0              movd     xmm0, eax
0x100157ac +71c   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x100157af +71f   f3 0f 11 85 70 fe ff ff  movss    dword ptr [ebp - 0x190], xmm0
0x100157b7 +727   f3 0f 10 1d 54 51 03 10  movss    xmm3, dword ptr [0x10035154]   ; [0x10035154] f32=0.00390625
0x100157bf +72f   f3 0f 59 d3              mulss    xmm2, xmm3
0x100157c3 +733   f3 0f 59 cb              mulss    xmm1, xmm3
0x100157c7 +737   f3 0f 59 c3              mulss    xmm0, xmm3
0x100157cb +73b   f3 0f 11 95 5c fe ff ff  movss    dword ptr [ebp - 0x1a4], xmm2
0x100157d3 +743   f3 0f 11 8d 60 fe ff ff  movss    dword ptr [ebp - 0x1a0], xmm1
0x100157db +74b   f3 0f 11 85 64 fe ff ff  movss    dword ptr [ebp - 0x19c], xmm0
0x100157e3 +753   f3 0f 11 95 7c ff ff ff  movss    dword ptr [ebp - 0x84], xmm2
0x100157eb +75b   f3 0f 11 4d 80           movss    dword ptr [ebp - 0x80], xmm1
0x100157f0 +760   f3 0f 11 45 84           movss    dword ptr [ebp - 0x7c], xmm0
0x100157f5 +765   e9 33 01 00 00           jmp      0x1001592d
0x100157fa +76a   83 f8 04                 cmp      eax, 4   ; PF: PF_Translucent
0x100157fd +76d   75 48                    jne      0x10015847
0x100157ff +76f   68 ff 00 00 00           push     0xff   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Environment|PF_Semisolid|PF_Modulated|PF_FakeBackdrop
0x10015804 +774   6a 00                    push     0
0x10015806 +776   8b 06                    mov      eax, dword ptr [esi]
0x10015808 +778   99                       cdq      
0x10015809 +779   83 e2 1f                 and      edx, 0x1f   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Environment
0x1001580c +77c   03 c2                    add      eax, edx
0x1001580e +77e   c1 f8 05                 sar      eax, 5
0x10015811 +781   50                       push     eax
0x10015812 +782   8d 85 30 fe ff ff        lea      eax, [ebp - 0x1d0]
0x10015818 +788   50                       push     eax
0x10015819 +789   ff 15 70 43 03 10        call     dword ptr [0x10034370]   ; -> Engine.dll!?FGetHSV@@YA?AVFPlane@@EEE@Z
0x1001581f +78f   83 c4 10                 add      esp, 0x10
0x10015822 +792   f3 0f 10 00              movss    xmm0, dword ptr [eax]
0x10015826 +796   f3 0f 11 85 7c ff ff ff  movss    dword ptr [ebp - 0x84], xmm0
0x1001582e +79e   f3 0f 10 40 04           movss    xmm0, dword ptr [eax + 4]
0x10015833 +7a3   f3 0f 11 45 80           movss    dword ptr [ebp - 0x80], xmm0
0x10015838 +7a8   f3 0f 10 40 08           movss    xmm0, dword ptr [eax + 8]
0x1001583d +7ad   f3 0f 11 45 84           movss    dword ptr [ebp - 0x7c], xmm0
0x10015842 +7b2   e9 e6 00 00 00           jmp      0x1001592d
0x10015847 +7b7   8b 4e 08                 mov      ecx, dword ptr [esi + 8]
0x1001584a +7ba   85 c9                    test     ecx, ecx
0x1001584c +7bc   75 2d                    jne      0x1001587b
0x1001584e +7be   8d 85 a8 fe ff ff        lea      eax, [ebp - 0x158]
0x10015854 +7c4   50                       push     eax
0x10015855 +7c5   8d 4a 44                 lea      ecx, [edx + 0x44]
0x10015858 +7c8   ff 15 4c 43 03 10        call     dword ptr [0x1003434c]   ; -> Engine.dll!?Plane@FColor@@QBE?AVFVector@@XZ
0x1001585e +7ce   f3 0f 10 00              movss    xmm0, dword ptr [eax]
0x10015862 +7d2   f3 0f 11 85 7c ff ff ff  movss    dword ptr [ebp - 0x84], xmm0
0x1001586a +7da   f3 0f 10 40 04           movss    xmm0, dword ptr [eax + 4]
0x1001586f +7df   f3 0f 11 45 80           movss    dword ptr [ebp - 0x80], xmm0
0x10015874 +7e4   f3 0f 10 40 08           movss    xmm0, dword ptr [eax + 8]
0x10015879 +7e9   eb 78                    jmp      0x100158f3
0x1001587b +7eb   6b c1 43                 imul     eax, ecx, 0x43
0x1001587e +7ee   0f b6 c0                 movzx    eax, al
0x10015881 +7f1   66 0f 6e d0              movd     xmm2, eax
0x10015885 +7f5   0f 5b d2                 cvtdq2ps xmm2, xmm2
0x10015888 +7f8   6b c1 5b                 imul     eax, ecx, 0x5b
0x1001588b +7fb   0f b6 c0                 movzx    eax, al
0x1001588e +7fe   66 0f 6e c8              movd     xmm1, eax
0x10015892 +802   0f 5b c9                 cvtdq2ps xmm1, xmm1
0x10015895 +805   6b c1 c7                 imul     eax, ecx, -0x39
0x10015898 +808   0f b6 c0                 movzx    eax, al
0x1001589b +80b   66 0f 6e c0              movd     xmm0, eax
0x1001589f +80f   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x100158a2 +812   f3 0f 11 95 24 fe ff ff  movss    dword ptr [ebp - 0x1dc], xmm2
0x100158aa +81a   f3 0f 11 8d 28 fe ff ff  movss    dword ptr [ebp - 0x1d8], xmm1
0x100158b2 +822   f3 0f 11 85 2c fe ff ff  movss    dword ptr [ebp - 0x1d4], xmm0
0x100158ba +82a   f3 0f 10 1d 54 51 03 10  movss    xmm3, dword ptr [0x10035154]   ; [0x10035154] f32=0.00390625
0x100158c2 +832   f3 0f 59 d3              mulss    xmm2, xmm3
0x100158c6 +836   f3 0f 59 cb              mulss    xmm1, xmm3
0x100158ca +83a   f3 0f 59 c3              mulss    xmm0, xmm3
0x100158ce +83e   f3 0f 11 95 4c fe ff ff  movss    dword ptr [ebp - 0x1b4], xmm2
0x100158d6 +846   f3 0f 11 8d 50 fe ff ff  movss    dword ptr [ebp - 0x1b0], xmm1
0x100158de +84e   f3 0f 11 85 54 fe ff ff  movss    dword ptr [ebp - 0x1ac], xmm0
0x100158e6 +856   f3 0f 11 95 7c ff ff ff  movss    dword ptr [ebp - 0x84], xmm2
0x100158ee +85e   f3 0f 11 4d 80           movss    dword ptr [ebp - 0x80], xmm1
0x100158f3 +863   f3 0f 11 45 84           movss    dword ptr [ebp - 0x7c], xmm0
0x100158f8 +868   8b 06                    mov      eax, dword ptr [esi]
0x100158fa +86a   83 e0 07                 and      eax, 7   ; PF: PF_Invisible|PF_Masked|PF_Translucent
0x100158fd +86d   66 0f 6e c0              movd     xmm0, eax
0x10015901 +871   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10015904 +874   f3 0f 59 05 a4 55 03 10  mulss    xmm0, dword ptr [0x100355a4]   ; [0x100355a4] f32=0.0625
0x1001590c +87c   f3 0f 58 05 6c 4b 03 10  addss    xmm0, dword ptr [0x10034b6c]   ; [0x10034b6c] f32=0.5
0x10015914 +884   51                       push     ecx
0x10015915 +885   f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x1001591a +88a   8d 85 b4 fe ff ff        lea      eax, [ebp - 0x14c]
0x10015920 +890   50                       push     eax
0x10015921 +891   8d 8d 7c ff ff ff        lea      ecx, [ebp - 0x84]
0x10015927 +897   ff 15 68 42 03 10        call     dword ptr [0x10034268]   ; -> Core.dll!??XFVector@@QAE?AV0@M@Z
0x1001592d +89d   8d 85 7c ff ff ff        lea      eax, [ebp - 0x84]
0x10015933 +8a3   50                       push     eax
0x10015934 +8a4   8d 8d 98 fe ff ff        lea      ecx, [ebp - 0x168]
0x1001593a +8aa   ff 15 08 42 03 10        call     dword ptr [0x10034208]   ; -> Core.dll!??0FPlane@@QAE@ABVFVector@@@Z
0x10015940 +8b0   8d 85 98 fe ff ff        lea      eax, [ebp - 0x168]
0x10015946 +8b6   50                       push     eax
0x10015947 +8b7   8d 8d 80 fe ff ff        lea      ecx, [ebp - 0x180]
0x1001594d +8bd   ff 15 78 43 03 10        call     dword ptr [0x10034378]   ; -> Engine.dll!??0FColor@@QAE@ABVFPlane@@@Z
0x10015953 +8c3   8b 00                    mov      eax, dword ptr [eax]
0x10015955 +8c5   89 85 30 ff ff ff        mov      dword ptr [ebp - 0xd0], eax
0x1001595b +8cb   81 8d 2c ff ff ff 00 00 00 40 or       dword ptr [ebp - 0xd4], 0x40000000
0x10015965 +8d5   8b 7d c4                 mov      edi, dword ptr [ebp - 0x3c]
0x10015968 +8d8   8b 07                    mov      eax, dword ptr [edi]
0x1001596a +8da   83 b8 b8 00 00 00 00     cmp      dword ptr [eax + 0xb8], 0
0x10015971 +8e1   74 1a                    je       0x1001598d
0x10015973 +8e3   6a 0c                    push     0xc   ; PF: PF_Translucent|PF_NotSolid
0x10015975 +8e5   ff 76 04                 push     dword ptr [esi + 4]
0x10015978 +8e8   8d 8d c0 fe ff ff        lea      ecx, [ebp - 0x140]
0x1001597e +8ee   ff 15 08 43 03 10        call     dword ptr [0x10034308]   ; -> Engine.dll!??0HBspSurf@@QAE@H@Z
0x10015984 +8f4   50                       push     eax
0x10015985 +8f5   8b 0f                    mov      ecx, dword ptr [edi]
0x10015987 +8f7   ff 15 28 43 03 10        call     dword ptr [0x10034328]   ; -> Engine.dll!?PushHit@UViewport@@QAEXABUHHitProxy@@H@Z
0x1001598d +8fd   0f 31                    rdtsc    
0x1001598f +8ff   29 05 e8 fa 05 10        sub      dword ptr [0x1005fae8], eax
0x10015995 +905   8b 75 c0                 mov      esi, dword ptr [ebp - 0x40]
0x10015998 +908   8b 4e 5c                 mov      ecx, dword ptr [esi + 0x5c]
0x1001599b +90b   8b 01                    mov      eax, dword ptr [ecx]
0x1001599d +90d   8d 95 bc fd ff ff        lea      edx, [ebp - 0x244]
0x100159a3 +913   52                       push     edx
0x100159a4 +914   8d 95 2c ff ff ff        lea      edx, [ebp - 0xd4]
0x100159aa +91a   52                       push     edx
0x100159ab +91b   57                       push     edi
0x100159ac +91c   ff 50 74                 call     dword ptr [eax + 0x74]
0x100159af +91f   0f 31                    rdtsc    
0x100159b1 +921   8b 0d e8 fa 05 10        mov      ecx, dword ptr [0x1005fae8]
0x100159b7 +927   83 c1 de                 add      ecx, -0x22
0x100159ba +92a   03 c1                    add      eax, ecx
0x100159bc +92c   a3 e8 fa 05 10           mov      dword ptr [0x1005fae8], eax
0x100159c1 +931   8b 0f                    mov      ecx, dword ptr [edi]
0x100159c3 +933   83 b9 b8 00 00 00 00     cmp      dword ptr [ecx + 0xb8], 0
0x100159ca +93a   74 08                    je       0x100159d4
0x100159cc +93c   6a 00                    push     0
0x100159ce +93e   ff 15 24 43 03 10        call     dword ptr [0x10034324]   ; -> Engine.dll!?PopHit@UViewport@@QAEXH@Z
0x100159d4 +944   c6 45 fc 01              mov      byte ptr [ebp - 4], 1   ; PF: PF_Invisible
0x100159d8 +948   9b                       wait     
0x100159d9 +949   0f 31                    rdtsc    
0x100159db +94b   29 05 64 fb 05 10        sub      dword ptr [0x1005fb64], eax
0x100159e1 +951   8b 46 5c                 mov      eax, dword ptr [esi + 0x5c]
0x100159e4 +954   83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x100159e8 +958   0f 85 e0 01 00 00        jne      0x10015bce
0x100159ee +95e   8b 46 18                 mov      eax, dword ptr [esi + 0x18]
0x100159f1 +961   83 78 4c 00              cmp      dword ptr [eax + 0x4c], 0
0x100159f5 +965   0f 84 d3 01 00 00        je       0x10015bce
0x100159fb +96b   33 c0                    xor      eax, eax
0x100159fd +96d   33 d2                    xor      edx, edx
0x100159ff +96f   89 95 78 ff ff ff        mov      dword ptr [ebp - 0x88], edx
0x10015a05 +975   66 66 66 0f 1f 84 00 00 00 00 00 nop      word ptr [eax + eax]
0x10015a10 +980   8b 4d bc                 mov      ecx, dword ptr [ebp - 0x44]
0x10015a13 +983   3b 51 2c                 cmp      edx, dword ptr [ecx + 0x2c]
0x10015a16 +986   0f 8d b2 01 00 00        jge      0x10015bce
0x10015a1c +98c   c1 e2 06                 shl      edx, 6
0x10015a1f +98f   89 55 a8                 mov      dword ptr [ebp - 0x58], edx
0x10015a22 +992   8b 79 28                 mov      edi, dword ptr [ecx + 0x28]
0x10015a25 +995   03 fa                    add      edi, edx
0x10015a27 +997   33 c9                    xor      ecx, ecx
0x10015a29 +999   89 4d b4                 mov      dword ptr [ebp - 0x4c], ecx
0x10015a2c +99c   85 c0                    test     eax, eax
0x10015a2e +99e   75 51                    jne      0x10015a81
0x10015a30 +9a0   8b 47 30                 mov      eax, dword ptr [edi + 0x30]
0x10015a33 +9a3   8b 88 2c 01 00 00        mov      ecx, dword ptr [eax + 0x12c]
0x10015a39 +9a9   85 c9                    test     ecx, ecx
0x10015a3b +9ab   74 16                    je       0x10015a53
0x10015a3d +9ad   ff b6 ac 00 00 00        push     dword ptr [esi + 0xac]
0x10015a43 +9b3   ff b6 a8 00 00 00        push     dword ptr [esi + 0xa8]
0x10015a49 +9b9   ff 15 60 43 03 10        call     dword ptr [0x10034360]   ; -> Engine.dll!?Get@UTexture@@QAEPAV1@VFTime@@@Z
0x10015a4f +9bf   8b c8                    mov      ecx, eax
0x10015a51 +9c1   eb 0e                    jmp      0x10015a61
0x10015a53 +9c3   8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10015a56 +9c6   8b 00                    mov      eax, dword ptr [eax]
0x10015a58 +9c8   8b 40 64                 mov      eax, dword ptr [eax + 0x64]
0x10015a5b +9cb   8b 88 08 04 00 00        mov      ecx, dword ptr [eax + 0x408]
0x10015a61 +9d1   89 4d b4                 mov      dword ptr [ebp - 0x4c], ecx
0x10015a64 +9d4   8b 01                    mov      eax, dword ptr [ecx]
0x10015a66 +9d6   ff 76 5c                 push     dword ptr [esi + 0x5c]
0x10015a69 +9d9   6a ff                    push     -1
0x10015a6b +9db   ff b6 ac 00 00 00        push     dword ptr [esi + 0xac]
0x10015a71 +9e1   ff b6 a8 00 00 00        push     dword ptr [esi + 0xa8]
0x10015a77 +9e7   8d 95 bc fb ff ff        lea      edx, [ebp - 0x444]
0x10015a7d +9ed   52                       push     edx
0x10015a7e +9ee   ff 50 54                 call     dword ptr [eax + 0x54]
0x10015a81 +9f1   8b b5 20 fe ff ff        mov      esi, dword ptr [ebp - 0x1e0]
0x10015a87 +9f7   85 f6                    test     esi, esi
0x10015a89 +9f9   0f 84 d3 00 00 00        je       0x10015b62
0x10015a8f +9ff   83 7f 38 00              cmp      dword ptr [edi + 0x38], 0
0x10015a93 +a03   7e 18                    jle      0x10015aad
0x10015a95 +a05   8d 45 88                 lea      eax, [ebp - 0x78]
0x10015a98 +a08   50                       push     eax
0x10015a99 +a09   8d 46 04                 lea      eax, [esi + 4]
0x10015a9c +a0c   50                       push     eax
0x10015a9d +a0d   8d 4f 34                 lea      ecx, [edi + 0x34]
0x10015aa0 +a10   e8 6b 27 00 00           call     0x10018210   ; -> sub_18210
0x10015aa5 +a15   85 c0                    test     eax, eax
0x10015aa7 +a17   0f 84 ae 00 00 00        je       0x10015b5b
0x10015aad +a1d   c7 45 94 00 00 00 00     mov      dword ptr [ebp - 0x6c], 0
0x10015ab4 +a24   c7 45 90 00 00 00 00     mov      dword ptr [ebp - 0x70], 0
0x10015abb +a2b   0f 31                    rdtsc    
0x10015abd +a2d   29 05 68 fb 05 10        sub      dword ptr [0x1005fb68], eax
0x10015ac3 +a33   33 c0                    xor      eax, eax
0x10015ac5 +a35   39 85 48 ff ff ff        cmp      dword ptr [ebp - 0xb8], eax
0x10015acb +a3b   0f 95 c0                 setne    al
0x10015ace +a3e   50                       push     eax
0x10015acf +a3f   8d 45 94                 lea      eax, [ebp - 0x6c]
0x10015ad2 +a42   50                       push     eax
0x10015ad3 +a43   8d 45 90                 lea      eax, [ebp - 0x70]
0x10015ad6 +a46   50                       push     eax
0x10015ad7 +a47   56                       push     esi
0x10015ad8 +a48   ff 75 bc                 push     dword ptr [ebp - 0x44]
0x10015adb +a4b   ff 75 a0                 push     dword ptr [ebp - 0x60]
0x10015ade +a4e   57                       push     edi
0x10015adf +a4f   ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x10015ae2 +a52   8b 4d a4                 mov      ecx, dword ptr [ebp - 0x5c]
0x10015ae5 +a55   e8 76 e5 ff ff           call     0x10014060   ; -> ?ClipDecal@URender@@QAEHPAUFSceneNode@@PAVFDecal@@PAVUModel@@PAVFBspSurf@@PAUFSavedPoly@@AAPAPAUFTransTexture@@AAHH@Z
0x10015aea +a5a   0f 31                    rdtsc    
0x10015aec +a5c   83 c0 de                 add      eax, -0x22
0x10015aef +a5f   03 05 68 fb 05 10        add      eax, dword ptr [0x1005fb68]
0x10015af5 +a65   a3 68 fb 05 10           mov      dword ptr [0x1005fb68], eax
0x10015afa +a6a   83 7d 94 00              cmp      dword ptr [ebp - 0x6c], 0
0x10015afe +a6e   74 5b                    je       0x10015b5b
0x10015b00 +a70   8b 4f 30                 mov      ecx, dword ptr [edi + 0x30]
0x10015b03 +a73   8b 41 64                 mov      eax, dword ptr [ecx + 0x64]
0x10015b06 +a76   f3 0f 10 80 6c 03 00 00  movss    xmm0, dword ptr [eax + 0x36c]
0x10015b0e +a7e   f3 0f 11 81 10 02 00 00  movss    dword ptr [ecx + 0x210], xmm0
0x10015b16 +a86   ba 40 00 00 00           mov      edx, 0x40   ; PF: PF_Modulated
0x10015b1b +a8b   89 95 08 ff ff ff        mov      dword ptr [ebp - 0xf8], edx
0x10015b21 +a91   83 bd 48 ff ff ff 00     cmp      dword ptr [ebp - 0xb8], 0
0x10015b28 +a98   b8 40 00 00 40           mov      eax, 0x40000040
0x10015b2d +a9d   0f 45 d0                 cmovne   edx, eax
0x10015b30 +aa0   89 95 08 ff ff ff        mov      dword ptr [ebp - 0xf8], edx
0x10015b36 +aa6   8b 45 c0                 mov      eax, dword ptr [ebp - 0x40]
0x10015b39 +aa9   8b 48 5c                 mov      ecx, dword ptr [eax + 0x5c]
0x10015b3c +aac   8b 01                    mov      eax, dword ptr [ecx]
0x10015b3e +aae   ff 75 98                 push     dword ptr [ebp - 0x68]
0x10015b41 +ab1   52                       push     edx
0x10015b42 +ab2   ff 75 94                 push     dword ptr [ebp - 0x6c]
0x10015b45 +ab5   ff 75 90                 push     dword ptr [ebp - 0x70]
0x10015b48 +ab8   8d 95 bc fb ff ff        lea      edx, [ebp - 0x444]
0x10015b4e +abe   52                       push     edx
0x10015b4f +abf   ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x10015b52 +ac2   ff 50 78                 call     dword ptr [eax + 0x78]
0x10015b55 +ac5   ff 05 6c fb 05 10        inc      dword ptr [0x1005fb6c]
0x10015b5b +acb   8b 36                    mov      esi, dword ptr [esi]
0x10015b5d +acd   e9 25 ff ff ff           jmp      0x10015a87
0x10015b62 +ad2   8b 4d bc                 mov      ecx, dword ptr [ebp - 0x44]
0x10015b65 +ad5   8b 41 2c                 mov      eax, dword ptr [ecx + 0x2c]
0x10015b68 +ad8   48                       dec      eax
0x10015b69 +ad9   8b 95 78 ff ff ff        mov      edx, dword ptr [ebp - 0x88]
0x10015b6f +adf   3b d0                    cmp      edx, eax
0x10015b71 +ae1   7d 2f                    jge      0x10015ba2
0x10015b73 +ae3   8b 41 28                 mov      eax, dword ptr [ecx + 0x28]
0x10015b76 +ae6   8b 4d a8                 mov      ecx, dword ptr [ebp - 0x58]
0x10015b79 +ae9   8b 4c 08 70              mov      ecx, dword ptr [eax + ecx + 0x70]
0x10015b7d +aed   8b 47 30                 mov      eax, dword ptr [edi + 0x30]
0x10015b80 +af0   8b 80 2c 01 00 00        mov      eax, dword ptr [eax + 0x12c]
0x10015b86 +af6   3b 81 2c 01 00 00        cmp      eax, dword ptr [ecx + 0x12c]
0x10015b8c +afc   75 14                    jne      0x10015ba2
0x10015b8e +afe   b8 01 00 00 00           mov      eax, 1   ; PF: PF_Invisible
0x10015b93 +b03   42                       inc      edx
0x10015b94 +b04   89 95 78 ff ff ff        mov      dword ptr [ebp - 0x88], edx
0x10015b9a +b0a   8b 75 c0                 mov      esi, dword ptr [ebp - 0x40]
0x10015b9d +b0d   e9 6e fe ff ff           jmp      0x10015a10
0x10015ba2 +b12   8b 55 b4                 mov      edx, dword ptr [ebp - 0x4c]
0x10015ba5 +b15   85 d2                    test     edx, edx
0x10015ba7 +b17   74 0e                    je       0x10015bb7
0x10015ba9 +b19   8b 02                    mov      eax, dword ptr [edx]
0x10015bab +b1b   8d 8d bc fb ff ff        lea      ecx, [ebp - 0x444]
0x10015bb1 +b21   51                       push     ecx
0x10015bb2 +b22   8b ca                    mov      ecx, edx
0x10015bb4 +b24   ff 50 58                 call     dword ptr [eax + 0x58]
0x10015bb7 +b27   33 c0                    xor      eax, eax
0x10015bb9 +b29   8b 95 78 ff ff ff        mov      edx, dword ptr [ebp - 0x88]
0x10015bbf +b2f   42                       inc      edx
0x10015bc0 +b30   89 95 78 ff ff ff        mov      dword ptr [ebp - 0x88], edx
0x10015bc6 +b36   8b 75 c0                 mov      esi, dword ptr [ebp - 0x40]
0x10015bc9 +b39   e9 42 fe ff ff           jmp      0x10015a10
0x10015bce +b3e   0f 31                    rdtsc    
0x10015bd0 +b40   83 c0 de                 add      eax, -0x22
0x10015bd3 +b43   03 05 64 fb 05 10        add      eax, dword ptr [0x1005fb64]
0x10015bd9 +b49   a3 64 fb 05 10           mov      dword ptr [0x1005fb64], eax
0x10015bde +b4e   9b                       wait     
0x10015bdf +b4f   c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x10015be6 +b56   8b 75 9c                 mov      esi, dword ptr [ebp - 0x64]
0x10015be9 +b59   8b 06                    mov      eax, dword ptr [esi]
0x10015beb +b5b   8d 8d 3c fc ff ff        lea      ecx, [ebp - 0x3c4]
0x10015bf1 +b61   51                       push     ecx
0x10015bf2 +b62   8b ce                    mov      ecx, esi
0x10015bf4 +b64   ff 50 58                 call     dword ptr [eax + 0x58]
0x10015bf7 +b67   83 bd 44 ff ff ff 00     cmp      dword ptr [ebp - 0xbc], 0
0x10015bfe +b6e   74 0f                    je       0x10015c0f
0x10015c00 +b70   8b 4e 58                 mov      ecx, dword ptr [esi + 0x58]
0x10015c03 +b73   8b 01                    mov      eax, dword ptr [ecx]
0x10015c05 +b75   8d 95 3c fb ff ff        lea      edx, [ebp - 0x4c4]
0x10015c0b +b7b   52                       push     edx
0x10015c0c +b7c   ff 50 58                 call     dword ptr [eax + 0x58]
0x10015c0f +b7f   83 bd 40 ff ff ff 00     cmp      dword ptr [ebp - 0xc0], 0
0x10015c16 +b86   74 0f                    je       0x10015c27
0x10015c18 +b88   8b 4e 5c                 mov      ecx, dword ptr [esi + 0x5c]
0x10015c1b +b8b   8b 01                    mov      eax, dword ptr [ecx]
0x10015c1d +b8d   8d 95 bc fa ff ff        lea      edx, [ebp - 0x544]
0x10015c23 +b93   52                       push     edx
0x10015c24 +b94   ff 50 58                 call     dword ptr [eax + 0x58]
0x10015c27 +b97   83 bd 3c ff ff ff 00     cmp      dword ptr [ebp - 0xc4], 0
0x10015c2e +b9e   75 09                    jne      0x10015c39
0x10015c30 +ba0   83 bd 48 ff ff ff 00     cmp      dword ptr [ebp - 0xb8], 0
0x10015c37 +ba7   74 0b                    je       0x10015c44
0x10015c39 +ba9   8b 0d 04 60 04 10        mov      ecx, dword ptr [0x10046004]   ; data ?GLightManager@@3PAVFLightManagerBase@@A
0x10015c3f +baf   8b 01                    mov      eax, dword ptr [ecx]
0x10015c41 +bb1   ff 50 10                 call     dword ptr [eax + 0x10]
0x10015c44 +bb4   8b 45 8c                 mov      eax, dword ptr [ebp - 0x74]
0x10015c47 +bb7   83 c0 04                 add      eax, 4
0x10015c4a +bba   89 85 28 ff ff ff        mov      dword ptr [ebp - 0xd8], eax
0x10015c50 +bc0   8b 55 b0                 mov      edx, dword ptr [ebp - 0x50]
0x10015c53 +bc3   8b 7d ac                 mov      edi, dword ptr [ebp - 0x54]
0x10015c56 +bc6   e9 2b f6 ff ff           jmp      0x10015286
0x10015c5b +bcb   8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x10015c5e +bce   8b ba a4 00 00 00        mov      edi, dword ptr [edx + 0xa4]
0x10015c64 +bd4   85 ff                    test     edi, edi
0x10015c66 +bd6   0f 84 f4 00 00 00        je       0x10015d60
0x10015c6c +bdc   8b 87 94 00 00 00        mov      eax, dword ptr [edi + 0x94]
0x10015c72 +be2   85 c0                    test     eax, eax
0x10015c74 +be4   74 10                    je       0x10015c86
0x10015c76 +be6   80 b8 25 01 00 00 03     cmp      byte ptr [eax + 0x125], 3   ; PF: PF_Invisible|PF_Masked
0x10015c7d +bed   75 07                    jne      0x10015c86
0x10015c7f +bef   be 01 00 00 00           mov      esi, 1   ; PF: PF_Invisible
0x10015c84 +bf4   eb 02                    jmp      0x10015c88
0x10015c86 +bf6   33 f6                    xor      esi, esi
0x10015c88 +bf8   89 b5 20 ff ff ff        mov      dword ptr [ebp - 0xe0], esi
0x10015c8e +bfe   85 f6                    test     esi, esi
0x10015c90 +c00   75 47                    jne      0x10015cd9
0x10015c92 +c02   80 b8 24 01 00 00 02     cmp      byte ptr [eax + 0x124], 2   ; PF: PF_Masked
0x10015c99 +c09   75 3e                    jne      0x10015cd9
0x10015c9b +c0b   ff b0 34 01 00 00        push     dword ptr [eax + 0x134]
0x10015ca1 +c11   e8 da be ff ff           call     0x10011b80   ; -> sub_11b80
0x10015ca6 +c16   83 c4 04                 add      esp, 4
0x10015ca9 +c19   8b d0                    mov      edx, eax
0x10015cab +c1b   85 d2                    test     edx, edx
0x10015cad +c1d   74 27                    je       0x10015cd6
0x10015caf +c1f   33 c9                    xor      ecx, ecx
0x10015cb1 +c21   89 8d 1c ff ff ff        mov      dword ptr [ebp - 0xe4], ecx
0x10015cb7 +c27   3b 8a 6c 01 00 00        cmp      ecx, dword ptr [edx + 0x16c]
0x10015cbd +c2d   7d 17                    jge      0x10015cd6
0x10015cbf +c2f   8b 82 68 01 00 00        mov      eax, dword ptr [edx + 0x168]
0x10015cc5 +c35   f6 04 c8 04              test     byte ptr [eax + ecx*8], 4   ; PF: PF_Translucent
0x10015cc9 +c39   74 3d                    je       0x10015d08
0x10015ccb +c3b   be 01 00 00 00           mov      esi, 1   ; PF: PF_Invisible
0x10015cd0 +c40   89 b5 20 ff ff ff        mov      dword ptr [ebp - 0xe0], esi
0x10015cd6 +c46   8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x10015cd9 +c49   8b 4d ac                 mov      ecx, dword ptr [ebp - 0x54]
0x10015cdc +c4c   83 f9 02                 cmp      ecx, 2   ; PF: PF_Masked
0x10015cdf +c4f   75 04                    jne      0x10015ce5
0x10015ce1 +c51   85 f6                    test     esi, esi
0x10015ce3 +c53   75 2f                    jne      0x10015d14
0x10015ce5 +c55   8b 45 c0                 mov      eax, dword ptr [ebp - 0x40]
0x10015ce8 +c58   8b 40 5c                 mov      eax, dword ptr [eax + 0x5c]
0x10015ceb +c5b   83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x10015cef +c5f   74 1a                    je       0x10015d0b
0x10015cf1 +c61   33 c0                    xor      eax, eax
0x10015cf3 +c63   83 f9 02                 cmp      ecx, 2   ; PF: PF_Masked
0x10015cf6 +c66   0f 94 c0                 sete     al
0x10015cf9 +c69   85 c0                    test     eax, eax
0x10015cfb +c6b   75 17                    jne      0x10015d14
0x10015cfd +c6d   8b 7f 10                 mov      edi, dword ptr [edi + 0x10]
0x10015d00 +c70   8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x10015d03 +c73   e9 5c ff ff ff           jmp      0x10015c64
0x10015d08 +c78   41                       inc      ecx
0x10015d09 +c79   eb a6                    jmp      0x10015cb1
0x10015d0b +c7b   83 f9 01                 cmp      ecx, 1   ; PF: PF_Invisible
0x10015d0e +c7e   75 ed                    jne      0x10015cfd
0x10015d10 +c80   85 f6                    test     esi, esi
0x10015d12 +c82   75 e9                    jne      0x10015cfd
0x10015d14 +c84   8b 87 94 00 00 00        mov      eax, dword ptr [edi + 0x94]
0x10015d1a +c8a   f6 80 60 01 00 00 40     test     byte ptr [eax + 0x160], 0x40   ; PF: PF_Modulated
0x10015d21 +c91   75 15                    jne      0x10015d38
0x10015d23 +c93   57                       push     edi
0x10015d24 +c94   52                       push     edx
0x10015d25 +c95   8b 4d a4                 mov      ecx, dword ptr [ebp - 0x5c]
0x10015d28 +c98   e8 73 93 00 00           call     0x1001f0a0   ; -> ?DrawActorSprite@URender@@QAEXPAUFSceneNode@@PAUFDynamicSprite@@@Z
0x10015d2d +c9d   8b 7f 10                 mov      edi, dword ptr [edi + 0x10]
0x10015d30 +ca0   8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x10015d33 +ca3   e9 2c ff ff ff           jmp      0x10015c64
0x10015d38 +ca8   33 f6                    xor      esi, esi
0x10015d3a +caa   89 b5 18 ff ff ff        mov      dword ptr [ebp - 0xe8], esi
0x10015d40 +cb0   3b b7 c0 00 00 00        cmp      esi, dword ptr [edi + 0xc0]
0x10015d46 +cb6   7d b5                    jge      0x10015cfd
0x10015d48 +cb8   8b 87 bc 00 00 00        mov      eax, dword ptr [edi + 0xbc]
0x10015d4e +cbe   ff 34 b0                 push     dword ptr [eax + esi*4]
0x10015d51 +cc1   52                       push     edx
0x10015d52 +cc2   8b 4d a4                 mov      ecx, dword ptr [ebp - 0x5c]
0x10015d55 +cc5   e8 46 93 00 00           call     0x1001f0a0   ; -> ?DrawActorSprite@URender@@QAEXPAUFSceneNode@@PAUFDynamicSprite@@@Z
0x10015d5a +cca   46                       inc      esi
0x10015d5b +ccb   8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x10015d5e +cce   eb da                    jmp      0x10015d3a
0x10015d60 +cd0   8b 7d ac                 mov      edi, dword ptr [ebp - 0x54]
0x10015d63 +cd3   47                       inc      edi
0x10015d64 +cd4   89 7d ac                 mov      dword ptr [ebp - 0x54], edi
0x10015d67 +cd7   8b 75 c0                 mov      esi, dword ptr [ebp - 0x40]
0x10015d6a +cda   e9 01 f5 ff ff           jmp      0x10015270
0x10015d6f +cdf   83 7a 1c 00              cmp      dword ptr [edx + 0x1c], 0
0x10015d73 +ce3   0f 85 6d 08 00 00        jne      0x100165e6
0x10015d79 +ce9   8b 46 5c                 mov      eax, dword ptr [esi + 0x5c]
0x10015d7c +cec   83 78 60 00              cmp      dword ptr [eax + 0x60], 0
0x10015d80 +cf0   0f 84 60 08 00 00        je       0x100165e6
0x10015d86 +cf6   8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10015d89 +cf9   8b 00                    mov      eax, dword ptr [eax]
0x10015d8b +cfb   83 b8 80 04 00 00 05     cmp      dword ptr [eax + 0x480], 5   ; PF: PF_Invisible|PF_Translucent
0x10015d92 +d02   0f 85 4e 08 00 00        jne      0x100165e6
0x10015d98 +d08   85 c0                    test     eax, eax
0x10015d9a +d0a   0f 84 46 08 00 00        je       0x100165e6
0x10015da0 +d10   f7 80 7c 04 00 00 00 48 00 00 test     dword ptr [eax + 0x47c], 0x4800   ; PF: PF_NoSmooth|PF_Flat
0x10015daa +d1a   0f 84 36 08 00 00        je       0x100165e6
0x10015db0 +d20   83 be b8 00 00 00 00     cmp      dword ptr [esi + 0xb8], 0
0x10015db7 +d27   0f 85 29 08 00 00        jne      0x100165e6
0x10015dbd +d2d   83 b8 8c 00 00 00 ff     cmp      dword ptr [eax + 0x8c], -1
0x10015dc4 +d34   0f 84 1c 08 00 00        je       0x100165e6
0x10015dca +d3a   83 b8 88 00 00 00 00     cmp      dword ptr [eax + 0x88], 0
0x10015dd1 +d41   0f 84 0f 08 00 00        je       0x100165e6
0x10015dd7 +d47   c7 45 a4 00 00 00 00     mov      dword ptr [ebp - 0x5c], 0
0x10015dde +d4e   a1 c0 41 03 10           mov      eax, dword ptr [0x100341c0]
0x10015de3 +d53   83 38 00                 cmp      dword ptr [eax], 0
0x10015de6 +d56   74 2e                    je       0x10015e16
0x10015de8 +d58   a1 78 41 03 10           mov      eax, dword ptr [0x10034178]
0x10015ded +d5d   8b 08                    mov      ecx, dword ptr [eax]
0x10015def +d5f   8b 01                    mov      eax, dword ptr [ecx]
0x10015df1 +d61   68 a0 45 03 10           push     0x100345a0
0x10015df6 +d66   68 80 01 00 00           push     0x180   ; PF: PF_FakeBackdrop|PF_TwoSided
0x10015dfb +d6b   8b 00                    mov      eax, dword ptr [eax]
0x10015dfd +d6d   ff d0                    call     eax
0x10015dff +d6f   8b f8                    mov      edi, eax
0x10015e01 +d71   89 7d b8                 mov      dword ptr [ebp - 0x48], edi
0x10015e04 +d74   68 80 01 00 00           push     0x180   ; PF: PF_FakeBackdrop|PF_TwoSided
0x10015e09 +d79   6a 00                    push     0
0x10015e0b +d7b   57                       push     edi
0x10015e0c +d7c   e8 7f d6 00 00           call     0x10023490   ; -> sub_23490
0x10015e11 +d81   83 c4 0c                 add      esp, 0xc
0x10015e14 +d84   eb 4f                    jmp      0x10015e65
0x10015e16 +d86   b8 70 6e 03 10           mov      eax, 0x10036e70
0x10015e1b +d8b   25 00 ff ff ff           and      eax, 0xffffff00
0x10015e20 +d90   99                       cdq      
0x10015e21 +d91   8b f0                    mov      esi, eax
0x10015e23 +d93   8b fa                    mov      edi, edx
0x10015e25 +d95   83 c6 27                 add      esi, 0x27
0x10015e28 +d98   83 d7 00                 adc      edi, 0
0x10015e2b +d9b   6a 10                    push     0x10   ; PF: PF_Environment
0x10015e2d +d9d   8d 45 a4                 lea      eax, [ebp - 0x5c]
0x10015e30 +da0   50                       push     eax
0x10015e31 +da1   57                       push     edi
0x10015e32 +da2   56                       push     esi
0x10015e33 +da3   8b 0d 80 43 03 10        mov      ecx, dword ptr [0x10034380]
0x10015e39 +da9   ff 15 b0 41 03 10        call     dword ptr [0x100341b0]   ; -> Core.dll!?Get@FMemCache@@QAEPAE_KAAPAVFCacheItem@1@H@Z
0x10015e3f +daf   89 45 b8                 mov      dword ptr [ebp - 0x48], eax
0x10015e42 +db2   85 c0                    test     eax, eax
0x10015e44 +db4   75 1c                    jne      0x10015e62
0x10015e46 +db6   50                       push     eax
0x10015e47 +db7   6a 10                    push     0x10   ; PF: PF_Environment
0x10015e49 +db9   68 80 01 00 00           push     0x180   ; PF: PF_FakeBackdrop|PF_TwoSided
0x10015e4e +dbe   8d 45 a4                 lea      eax, [ebp - 0x5c]
0x10015e51 +dc1   50                       push     eax
0x10015e52 +dc2   57                       push     edi
0x10015e53 +dc3   56                       push     esi
0x10015e54 +dc4   8b 0d 80 43 03 10        mov      ecx, dword ptr [0x10034380]
0x10015e5a +dca   ff 15 ac 41 03 10        call     dword ptr [0x100341ac]   ; -> Core.dll!?Create@FMemCache@@QAEPAE_KAAPAVFCacheItem@1@HHH@Z
0x10015e60 +dd0   eb 9d                    jmp      0x10015dff
0x10015e62 +dd2   8b 7d b8                 mov      edi, dword ptr [ebp - 0x48]
0x10015e65 +dd5   8b 0d cc 15 06 10        mov      ecx, dword ptr [0x100615cc]
0x10015e6b +ddb   64 a1 2c 00 00 00        mov      eax, dword ptr fs:[0x2c]
0x10015e71 +de1   8b 0c 88                 mov      ecx, dword ptr [eax + ecx*4]
0x10015e74 +de4   a1 7c 15 06 10           mov      eax, dword ptr [0x1006157c]
0x10015e79 +de9   3b 81 04 00 00 00        cmp      eax, dword ptr [ecx + 4]
0x10015e7f +def   0f 8f 2d 08 00 00        jg       0x100166b2
0x10015e85 +df5   0f 31                    rdtsc    
0x10015e87 +df7   89 45 e4                 mov      dword ptr [ebp - 0x1c], eax
0x10015e8a +dfa   89 55 e8                 mov      dword ptr [ebp - 0x18], edx
0x10015e8d +dfd   8b f0                    mov      esi, eax
0x10015e8f +dff   2b 35 74 15 06 10        sub      esi, dword ptr [0x10061574]
0x10015e95 +e05   8b ca                    mov      ecx, edx
0x10015e97 +e07   1b 0d 78 15 06 10        sbb      ecx, dword ptr [0x10061578]
0x10015e9d +e0d   89 75 e4                 mov      dword ptr [ebp - 0x1c], esi
0x10015ea0 +e10   89 4d e8                 mov      dword ptr [ebp - 0x18], ecx
0x10015ea3 +e13   a3 74 15 06 10           mov      dword ptr [0x10061574], eax
0x10015ea8 +e18   89 15 78 15 06 10        mov      dword ptr [0x10061578], edx
0x10015eae +e1e   51                       push     ecx
0x10015eaf +e1f   56                       push     esi
0x10015eb0 +e20   57                       push     edi
0x10015eb1 +e21   ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x10015eb4 +e24   e8 e7 25 00 00           call     0x100184a0   ; -> sub_184a0
0x10015eb9 +e29   83 c4 10                 add      esp, 0x10
0x10015ebc +e2c   33 f6                    xor      esi, esi
0x10015ebe +e2e   89 b5 58 ff ff ff        mov      dword ptr [ebp - 0xa8], esi
0x10015ec4 +e34   83 fe 20                 cmp      esi, 0x20   ; PF: PF_Semisolid
0x10015ec7 +e37   0f 8d f0 06 00 00        jge      0x100165bd
0x10015ecd +e3d   8d 04 76                 lea      eax, [esi + esi*2]
0x10015ed0 +e40   89 45 8c                 mov      dword ptr [ebp - 0x74], eax
0x10015ed3 +e43   8b 3c 87                 mov      edi, dword ptr [edi + eax*4]
0x10015ed6 +e46   89 7d bc                 mov      dword ptr [ebp - 0x44], edi
0x10015ed9 +e49   85 ff                    test     edi, edi
0x10015edb +e4b   0f 84 cd 06 00 00        je       0x100165ae
0x10015ee1 +e51   8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x10015ee4 +e54   83 c0 34                 add      eax, 0x34
0x10015ee7 +e57   50                       push     eax
0x10015ee8 +e58   8d 85 fc fe ff ff        lea      eax, [ebp - 0x104]
0x10015eee +e5e   50                       push     eax
0x10015eef +e5f   8d 8f d0 00 00 00        lea      ecx, [edi + 0xd0]
0x10015ef5 +e65   ff 15 f8 41 03 10        call     dword ptr [0x100341f8]   ; -> Core.dll!?TransformPointBy@FVector@@QBE?AV1@ABVFCoords@@@Z
0x10015efb +e6b   f3 0f 10 35 70 4b 03 10  movss    xmm6, dword ptr [0x10034b70]   ; [0x10034b70] f32=1.0
0x10015f03 +e73   0f 2f b5 04 ff ff ff     comiss   xmm6, dword ptr [ebp - 0xfc]
0x10015f0a +e7a   0f 87 9e 06 00 00        ja       0x100165ae
0x10015f10 +e80   8a 87 9f 01 00 00        mov      al, byte ptr [edi + 0x19f]
0x10015f16 +e86   0f b6 c8                 movzx    ecx, al
0x10015f19 +e89   3c 56                    cmp      al, 0x56   ; PF: PF_Masked|PF_Translucent|PF_Environment|PF_Modulated
0x10015f1b +e8b   73 47                    jae      0x10015f64
0x10015f1d +e8d   66 0f 6e e1              movd     xmm4, ecx
0x10015f21 +e91   0f 5b e4                 cvtdq2ps xmm4, xmm4
0x10015f24 +e94   f3 0f 5e 25 14 6f 03 10  divss    xmm4, dword ptr [0x10036f14]   ; [0x10036f14] f32=85.0
0x10015f2c +e9c   b8 55 00 00 00           mov      eax, 0x55   ; PF: PF_Invisible|PF_Translucent|PF_Environment|PF_Modulated
0x10015f31 +ea1   2b c1                    sub      eax, ecx
0x10015f33 +ea3   66 0f 6e c8              movd     xmm1, eax
0x10015f37 +ea7   0f 5b c9                 cvtdq2ps xmm1, xmm1
0x10015f3a +eaa   f3 0f 5e 0d 14 6f 03 10  divss    xmm1, dword ptr [0x10036f14]   ; [0x10036f14] f32=85.0
0x10015f42 +eb2   f3 0f 11 8d 40 fe ff ff  movss    dword ptr [ebp - 0x1c0], xmm1
0x10015f4a +eba   f3 0f 11 a5 44 fe ff ff  movss    dword ptr [ebp - 0x1bc], xmm4
0x10015f52 +ec2   c7 85 48 fe ff ff 00 00 00 00 mov      dword ptr [ebp - 0x1b8], 0
0x10015f5c +ecc   0f 57 ed                 xorps    xmm5, xmm5
0x10015f5f +ecf   e9 ab 00 00 00           jmp      0x1001600f
0x10015f64 +ed4   3c ab                    cmp      al, 0xab   ; PF: PF_Invisible|PF_Masked|PF_NotSolid|PF_Semisolid|PF_FakeBackdrop
0x10015f66 +ed6   73 47                    jae      0x10015faf
0x10015f68 +ed8   8d 41 ab                 lea      eax, [ecx - 0x55]
0x10015f6b +edb   66 0f 6e e8              movd     xmm5, eax
0x10015f6f +edf   0f 5b ed                 cvtdq2ps xmm5, xmm5
0x10015f72 +ee2   f3 0f 5e 2d 14 6f 03 10  divss    xmm5, dword ptr [0x10036f14]   ; [0x10036f14] f32=85.0
0x10015f7a +eea   b8 aa 00 00 00           mov      eax, 0xaa   ; PF: PF_Masked|PF_NotSolid|PF_Semisolid|PF_FakeBackdrop
0x10015f7f +eef   2b c1                    sub      eax, ecx
0x10015f81 +ef1   66 0f 6e e0              movd     xmm4, eax
0x10015f85 +ef5   0f 5b e4                 cvtdq2ps xmm4, xmm4
0x10015f88 +ef8   f3 0f 5e 25 14 6f 03 10  divss    xmm4, dword ptr [0x10036f14]   ; [0x10036f14] f32=85.0
0x10015f90 +f00   c7 85 34 fe ff ff 00 00 00 00 mov      dword ptr [ebp - 0x1cc], 0
0x10015f9a +f0a   f3 0f 11 a5 38 fe ff ff  movss    dword ptr [ebp - 0x1c8], xmm4
0x10015fa2 +f12   f3 0f 11 ad 3c fe ff ff  movss    dword ptr [ebp - 0x1c4], xmm5
0x10015faa +f1a   0f 57 c9                 xorps    xmm1, xmm1
0x10015fad +f1d   eb 48                    jmp      0x10015ff7
0x10015faf +f1f   b8 ff 00 00 00           mov      eax, 0xff   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Environment|PF_Semisolid|PF_Modulated|PF_FakeBackdrop
0x10015fb4 +f24   2b c1                    sub      eax, ecx
0x10015fb6 +f26   66 0f 6e e8              movd     xmm5, eax
0x10015fba +f2a   0f 5b ed                 cvtdq2ps xmm5, xmm5
0x10015fbd +f2d   f3 0f 5e 2d 10 6f 03 10  divss    xmm5, dword ptr [0x10036f10]   ; [0x10036f10] f32=84.0
0x10015fc5 +f35   8d 81 56 ff ff ff        lea      eax, [ecx - 0xaa]
0x10015fcb +f3b   66 0f 6e c8              movd     xmm1, eax
0x10015fcf +f3f   0f 5b c9                 cvtdq2ps xmm1, xmm1
0x10015fd2 +f42   f3 0f 5e 0d 14 6f 03 10  divss    xmm1, dword ptr [0x10036f14]   ; [0x10036f14] f32=85.0
0x10015fda +f4a   f3 0f 11 8d 9c fe ff ff  movss    dword ptr [ebp - 0x164], xmm1
0x10015fe2 +f52   c7 85 a0 fe ff ff 00 00 00 00 mov      dword ptr [ebp - 0x160], 0
0x10015fec +f5c   f3 0f 11 ad a4 fe ff ff  movss    dword ptr [ebp - 0x15c], xmm5
0x10015ff4 +f64   0f 57 e4                 xorps    xmm4, xmm4
0x10015ff7 +f67   f3 0f 11 8d c0 fe ff ff  movss    dword ptr [ebp - 0x140], xmm1
0x10015fff +f6f   f3 0f 11 a5 c4 fe ff ff  movss    dword ptr [ebp - 0x13c], xmm4
0x10016007 +f77   f3 0f 11 ad c8 fe ff ff  movss    dword ptr [ebp - 0x138], xmm5
0x1001600f +f7f   f3 0f 11 8d cc fe ff ff  movss    dword ptr [ebp - 0x134], xmm1
0x10016017 +f87   f3 0f 11 a5 d0 fe ff ff  movss    dword ptr [ebp - 0x130], xmm4
0x1001601f +f8f   f3 0f 11 ad d4 fe ff ff  movss    dword ptr [ebp - 0x12c], xmm5
0x10016027 +f97   0f b6 87 a0 01 00 00     movzx    eax, byte ptr [edi + 0x1a0]
0x1001602e +f9e   66 0f 6e c0              movd     xmm0, eax
0x10016032 +fa2   f3 0f e6 c0              cvtdq2pd xmm0, xmm0
0x10016036 +fa6   f2 0f 5e 05 00 6f 03 10  divsd    xmm0, qword ptr [0x10036f00]   ; [0x10036f00] f32=0.0
0x1001603e +fae   66 0f 5a d8              cvtpd2ps xmm3, xmm0
0x10016042 +fb2   c7 85 b4 fe ff ff 00 00 80 3f mov      dword ptr [ebp - 0x14c], 0x3f800000
0x1001604c +fbc   c7 85 b8 fe ff ff 00 00 80 3f mov      dword ptr [ebp - 0x148], 0x3f800000
0x10016056 +fc6   c7 85 bc fe ff ff 00 00 80 3f mov      dword ptr [ebp - 0x144], 0x3f800000
0x10016060 +fd0   0f 28 d6                 movaps   xmm2, xmm6
0x10016063 +fd3   f3 0f 5c d1              subss    xmm2, xmm1
0x10016067 +fd7   0f 28 ce                 movaps   xmm1, xmm6
0x1001606a +fda   f3 0f 5c cc              subss    xmm1, xmm4
0x1001606e +fde   0f 28 c6                 movaps   xmm0, xmm6
0x10016071 +fe1   f3 0f 5c c5              subss    xmm0, xmm5
0x10016075 +fe5   f3 0f 11 95 a8 fe ff ff  movss    dword ptr [ebp - 0x158], xmm2
0x1001607d +fed   f3 0f 11 8d ac fe ff ff  movss    dword ptr [ebp - 0x154], xmm1
0x10016085 +ff5   f3 0f 11 85 b0 fe ff ff  movss    dword ptr [ebp - 0x150], xmm0
0x1001608d +ffd   f3 0f 59 d3              mulss    xmm2, xmm3
0x10016091 +1001  f3 0f 59 cb              mulss    xmm1, xmm3
0x10016095 +1005  f3 0f 59 c3              mulss    xmm0, xmm3
0x10016099 +1009  f3 0f 11 95 d8 fe ff ff  movss    dword ptr [ebp - 0x128], xmm2
0x100160a1 +1011  f3 0f 11 8d dc fe ff ff  movss    dword ptr [ebp - 0x124], xmm1
0x100160a9 +1019  f3 0f 11 85 e0 fe ff ff  movss    dword ptr [ebp - 0x120], xmm0
0x100160b1 +1021  8d 85 d8 fe ff ff        lea      eax, [ebp - 0x128]
0x100160b7 +1027  50                       push     eax
0x100160b8 +1028  8d 85 64 ff ff ff        lea      eax, [ebp - 0x9c]
0x100160be +102e  50                       push     eax
0x100160bf +102f  8d 8d cc fe ff ff        lea      ecx, [ebp - 0x134]
0x100160c5 +1035  ff 15 e4 41 03 10        call     dword ptr [0x100341e4]   ; -> Core.dll!??HFVector@@QBE?AV0@ABV0@@Z
0x100160cb +103b  8b 4d c4                 mov      ecx, dword ptr [ebp - 0x3c]
0x100160ce +103e  f3 0f 10 81 dc 00 00 00  movss    xmm0, dword ptr [ecx + 0xdc]
0x100160d6 +1046  f3 0f 5e 85 04 ff ff ff  divss    xmm0, dword ptr [ebp - 0xfc]
0x100160de +104e  f3 0f 11 45 9c           movss    dword ptr [ebp - 0x64], xmm0
0x100160e3 +1053  f3 0f 10 95 fc fe ff ff  movss    xmm2, dword ptr [ebp - 0x104]
0x100160eb +105b  f3 0f 59 d0              mulss    xmm2, xmm0
0x100160ef +105f  f3 0f 58 91 c8 00 00 00  addss    xmm2, dword ptr [ecx + 0xc8]
0x100160f7 +1067  f3 0f 11 55 94           movss    dword ptr [ebp - 0x6c], xmm2
0x100160fc +106c  f3 0f 10 b5 00 ff ff ff  movss    xmm6, dword ptr [ebp - 0x100]
0x10016104 +1074  f3 0f 59 f0              mulss    xmm6, xmm0
0x10016108 +1078  f3 0f 58 b1 cc 00 00 00  addss    xmm6, dword ptr [ecx + 0xcc]
0x10016110 +1080  f3 0f 11 75 98           movss    dword ptr [ebp - 0x68], xmm6
0x10016115 +1085  8b 81 a8 00 00 00        mov      eax, dword ptr [ecx + 0xa8]
0x1001611b +108b  f3 0f 10 af 3c 01 00 00  movss    xmm5, dword ptr [edi + 0x13c]
0x10016123 +1093  f3 0f 59 2d 1c 6f 03 10  mulss    xmm5, dword ptr [0x10036f1c]   ; [0x10036f1c] f32=512.0
0x1001612b +109b  66 0f 6e c0              movd     xmm0, eax
0x1001612f +109f  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10016132 +10a2  f3 0f 59 e8              mulss    xmm5, xmm0
0x10016136 +10a6  f3 0f 5e 2d c8 55 03 10  divss    xmm5, dword ptr [0x100355c8]   ; [0x100355c8] f32=640.0
0x1001613e +10ae  f3 0f 11 6d 90           movss    dword ptr [ebp - 0x70], xmm5
0x10016143 +10b3  f6 87 a8 01 00 00 08     test     byte ptr [edi + 0x1a8], 8   ; PF: PF_NotSolid
0x1001614a +10ba  0f 84 d7 02 00 00        je       0x10016427
0x10016150 +10c0  0f 28 e5                 movaps   xmm4, xmm5
0x10016153 +10c3  f3 0f 59 25 6c 4b 03 10  mulss    xmm4, dword ptr [0x10034b6c]   ; [0x10034b6c] f32=0.5
0x1001615b +10cb  f3 0f 11 a5 74 ff ff ff  movss    dword ptr [ebp - 0x8c], xmm4
0x10016163 +10d3  2b 81 ac 00 00 00        sub      eax, dword ptr [ecx + 0xac]
0x10016169 +10d9  99                       cdq      
0x1001616a +10da  2b c2                    sub      eax, edx
0x1001616c +10dc  d1 f8                    sar      eax, 1
0x1001616e +10de  66 0f 6e c0              movd     xmm0, eax
0x10016172 +10e2  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10016175 +10e5  0f 28 dd                 movaps   xmm3, xmm5
0x10016178 +10e8  f3 0f 5c d8              subss    xmm3, xmm0
0x1001617c +10ec  f3 0f 59 1d 6c 4b 03 10  mulss    xmm3, dword ptr [0x10034b6c]   ; [0x10034b6c] f32=0.5
0x10016184 +10f4  f3 0f 11 9d 54 ff ff ff  movss    dword ptr [ebp - 0xac], xmm3
0x1001618c +10fc  33 f6                    xor      esi, esi
0x1001618e +10fe  89 b5 10 ff ff ff        mov      dword ptr [ebp - 0xf0], esi
0x10016194 +1104  83 fe 0c                 cmp      esi, 0xc   ; PF: PF_Translucent|PF_NotSolid
0x10016197 +1107  0f 83 87 02 00 00        jae      0x10016424
0x1001619d +110d  8b 87 88 00 00 00        mov      eax, dword ptr [edi + 0x88]
0x100161a3 +1113  8b bc b0 cc 02 00 00     mov      edi, dword ptr [eax + esi*4 + 0x2cc]
0x100161aa +111a  85 ff                    test     edi, edi
0x100161ac +111c  0f 84 6f 02 00 00        je       0x10016421
0x100161b2 +1122  f3 0f 10 84 b0 fc 02 00 00 movss    xmm0, dword ptr [eax + esi*4 + 0x2fc]
0x100161bb +112b  0f 57 05 f0 52 03 10     xorps    xmm0, xmmword ptr [0x100352f0]   ; [0x100352f0] f32=-0.0
0x100161c2 +1132  8b 45 c0                 mov      eax, dword ptr [ebp - 0x40]
0x100161c5 +1135  8b 48 54                 mov      ecx, dword ptr [eax + 0x54]
0x100161c8 +1138  8b 41 60                 mov      eax, dword ptr [ecx + 0x60]
0x100161cb +113b  99                       cdq      
0x100161cc +113c  2b c2                    sub      eax, edx
0x100161ce +113e  d1 f8                    sar      eax, 1
0x100161d0 +1140  66 0f 6e c8              movd     xmm1, eax
0x100161d4 +1144  0f 5b c9                 cvtdq2ps xmm1, xmm1
0x100161d7 +1147  f3 0f 5c ca              subss    xmm1, xmm2
0x100161db +114b  f3 0f 59 c8              mulss    xmm1, xmm0
0x100161df +114f  f3 0f 58 ca              addss    xmm1, xmm2
0x100161e3 +1153  f3 0f 11 4d a8           movss    dword ptr [ebp - 0x58], xmm1
0x100161e8 +1158  8b 41 64                 mov      eax, dword ptr [ecx + 0x64]
0x100161eb +115b  99                       cdq      
0x100161ec +115c  2b c2                    sub      eax, edx
0x100161ee +115e  d1 f8                    sar      eax, 1
0x100161f0 +1160  66 0f 6e d0              movd     xmm2, eax
0x100161f4 +1164  0f 5b d2                 cvtdq2ps xmm2, xmm2
0x100161f7 +1167  f3 0f 5c d6              subss    xmm2, xmm6
0x100161fb +116b  f3 0f 59 d0              mulss    xmm2, xmm0
0x100161ff +116f  f3 0f 58 d6              addss    xmm2, xmm6
0x10016203 +1173  f3 0f 11 55 b4           movss    dword ptr [ebp - 0x4c], xmm2
0x10016208 +1178  85 f6                    test     esi, esi
0x1001620a +117a  75 36                    jne      0x10016242
0x1001620c +117c  0f 2f e1                 comiss   xmm4, xmm1
0x1001620f +117f  0f 87 0c 02 00 00        ja       0x10016421
0x10016215 +1185  0f 2f da                 comiss   xmm3, xmm2
0x10016218 +1188  0f 87 03 02 00 00        ja       0x10016421
0x1001621e +118e  f3 0f 10 41 3c           movss    xmm0, dword ptr [ecx + 0x3c]
0x10016223 +1193  f3 0f 5c c4              subss    xmm0, xmm4
0x10016227 +1197  0f 2f c8                 comiss   xmm1, xmm0
0x1001622a +119a  0f 87 f1 01 00 00        ja       0x10016421
0x10016230 +11a0  f3 0f 10 41 40           movss    xmm0, dword ptr [ecx + 0x40]
0x10016235 +11a5  f3 0f 5c c3              subss    xmm0, xmm3
0x10016239 +11a9  0f 2f d0                 comiss   xmm2, xmm0
0x1001623c +11ac  0f 87 df 01 00 00        ja       0x10016421
0x10016242 +11b2  8b 4d bc                 mov      ecx, dword ptr [ebp - 0x44]
0x10016245 +11b5  8b 81 88 00 00 00        mov      eax, dword ptr [ecx + 0x88]
0x1001624b +11bb  f3 0f 10 8c b0 2c 03 00 00 movss    xmm1, dword ptr [eax + esi*4 + 0x32c]
0x10016254 +11c4  0f 5a c9                 cvtps2pd xmm1, xmm1
0x10016257 +11c7  0f 5a c5                 cvtps2pd xmm0, xmm5
0x1001625a +11ca  f2 0f 59 05 e0 6e 03 10  mulsd    xmm0, qword ptr [0x10036ee0]
0x10016262 +11d2  f2 0f 59 c8              mulsd    xmm1, xmm0
0x10016266 +11d6  66 0f 5a c1              cvtpd2ps xmm0, xmm1
0x1001626a +11da  f3 0f 11 45 a0           movss    dword ptr [ebp - 0x60], xmm0
0x1001626f +11df  8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10016272 +11e2  8b 00                    mov      eax, dword ptr [eax]
0x10016274 +11e4  85 c0                    test     eax, eax
0x10016276 +11e6  74 27                    je       0x1001629f
0x10016278 +11e8  f7 80 7c 04 00 00 00 48 00 00 test     dword ptr [eax + 0x47c], 0x4800   ; PF: PF_NoSmooth|PF_Flat
0x10016282 +11f2  74 1b                    je       0x1001629f
0x10016284 +11f4  8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x10016287 +11f7  8b 00                    mov      eax, dword ptr [eax]
0x10016289 +11f9  ff b0 ac 00 00 00        push     dword ptr [eax + 0xac]
0x1001628f +11ff  ff b0 a8 00 00 00        push     dword ptr [eax + 0xa8]
0x10016295 +1205  8b cf                    mov      ecx, edi
0x10016297 +1207  ff 15 60 43 03 10        call     dword ptr [0x10034360]   ; -> Engine.dll!?Get@UTexture@@QAEPAV1@VFTime@@@Z
0x1001629d +120d  8b f8                    mov      edi, eax
0x1001629f +120f  8b 07                    mov      eax, dword ptr [edi]
0x100162a1 +1211  8b 4d c0                 mov      ecx, dword ptr [ebp - 0x40]
0x100162a4 +1214  ff 71 5c                 push     dword ptr [ecx + 0x5c]
0x100162a7 +1217  6a ff                    push     -1
0x100162a9 +1219  ff b1 ac 00 00 00        push     dword ptr [ecx + 0xac]
0x100162af +121f  ff b1 a8 00 00 00        push     dword ptr [ecx + 0xa8]
0x100162b5 +1225  8d 8d 3c fd ff ff        lea      ecx, [ebp - 0x2c4]
0x100162bb +122b  51                       push     ecx
0x100162bc +122c  8b cf                    mov      ecx, edi
0x100162be +122e  ff 50 54                 call     dword ptr [eax + 0x54]
0x100162c1 +1231  68 04 01 00 00           push     0x104   ; PF: PF_Translucent|PF_TwoSided
0x100162c6 +1236  83 ec 10                 sub      esp, 0x10
0x100162c9 +1239  8b c4                    mov      eax, esp
0x100162cb +123b  0f 57 c0                 xorps    xmm0, xmm0
0x100162ce +123e  0f 11 00                 movups   xmmword ptr [eax], xmm0
0x100162d1 +1241  83 ec 10                 sub      esp, 0x10
0x100162d4 +1244  8b c4                    mov      eax, esp
0x100162d6 +1246  f3 0f 10 55 9c           movss    xmm2, dword ptr [ebp - 0x64]
0x100162db +124b  8b 4d b8                 mov      ecx, dword ptr [ebp - 0x48]
0x100162de +124e  8b 55 8c                 mov      edx, dword ptr [ebp - 0x74]
0x100162e1 +1251  f3 0f 59 54 91 08        mulss    xmm2, dword ptr [ecx + edx*4 + 8]
0x100162e7 +1257  f3 0f 10 9d 64 ff ff ff  movss    xmm3, dword ptr [ebp - 0x9c]
0x100162ef +125f  f3 0f 59 da              mulss    xmm3, xmm2
0x100162f3 +1263  f3 0f 10 8d 68 ff ff ff  movss    xmm1, dword ptr [ebp - 0x98]
0x100162fb +126b  f3 0f 59 ca              mulss    xmm1, xmm2
0x100162ff +126f  f3 0f 10 85 6c ff ff ff  movss    xmm0, dword ptr [ebp - 0x94]
0x10016307 +1277  f3 0f 59 c2              mulss    xmm0, xmm2
0x1001630b +127b  f3 0f 11 9d f0 fe ff ff  movss    dword ptr [ebp - 0x110], xmm3
0x10016313 +1283  f3 0f 11 8d f4 fe ff ff  movss    dword ptr [ebp - 0x10c], xmm1
0x1001631b +128b  f3 0f 11 85 f8 fe ff ff  movss    dword ptr [ebp - 0x108], xmm0
0x10016323 +1293  f3 0f 11 18              movss    dword ptr [eax], xmm3
0x10016327 +1297  f3 0f 10 85 f4 fe ff ff  movss    xmm0, dword ptr [ebp - 0x10c]
0x1001632f +129f  f3 0f 11 40 04           movss    dword ptr [eax + 4], xmm0
0x10016334 +12a4  f3 0f 10 85 f8 fe ff ff  movss    xmm0, dword ptr [ebp - 0x108]
0x1001633c +12ac  f3 0f 11 40 08           movss    dword ptr [eax + 8], xmm0
0x10016341 +12b1  c7 40 0c 00 00 00 00     mov      dword ptr [eax + 0xc], 0
0x10016348 +12b8  8b 45 c0                 mov      eax, dword ptr [ebp - 0x40]
0x1001634b +12bb  8b 48 5c                 mov      ecx, dword ptr [eax + 0x5c]
0x1001634e +12be  f3 0f 10 55 a0           movss    xmm2, dword ptr [ebp - 0x60]
0x10016353 +12c3  0f 28 ca                 movaps   xmm1, xmm2
0x10016356 +12c6  f3 0f 59 0d 6c 4b 03 10  mulss    xmm1, dword ptr [0x10034b6c]   ; [0x10034b6c] f32=0.5
0x1001635e +12ce  8b 01                    mov      eax, dword ptr [ecx]
0x10016360 +12d0  51                       push     ecx
0x10016361 +12d1  c7 04 24 00 00 80 3f     mov      dword ptr [esp], 0x3f800000
0x10016368 +12d8  6a 00                    push     0
0x1001636a +12da  66 0f 6e 85 70 fd ff ff  movd     xmm0, dword ptr [ebp - 0x290]
0x10016372 +12e2  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10016375 +12e5  f3 0f 59 85 68 fd ff ff  mulss    xmm0, dword ptr [ebp - 0x298]
0x1001637d +12ed  83 ec 20                 sub      esp, 0x20
0x10016380 +12f0  f3 0f 11 44 24 1c        movss    dword ptr [esp + 0x1c], xmm0
0x10016386 +12f6  66 0f 6e 85 6c fd ff ff  movd     xmm0, dword ptr [ebp - 0x294]
0x1001638e +12fe  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10016391 +1301  f3 0f 59 85 64 fd ff ff  mulss    xmm0, dword ptr [ebp - 0x29c]
0x10016399 +1309  f3 0f 11 44 24 18        movss    dword ptr [esp + 0x18], xmm0
0x1001639f +130f  c7 44 24 14 00 00 00 00  mov      dword ptr [esp + 0x14], 0
0x100163a7 +1317  c7 44 24 10 00 00 00 00  mov      dword ptr [esp + 0x10], 0
0x100163af +131f  f3 0f 11 54 24 0c        movss    dword ptr [esp + 0xc], xmm2
0x100163b5 +1325  f3 0f 11 54 24 08        movss    dword ptr [esp + 8], xmm2
0x100163bb +132b  f3 0f 10 45 b4           movss    xmm0, dword ptr [ebp - 0x4c]
0x100163c0 +1330  f3 0f 5c c1              subss    xmm0, xmm1
0x100163c4 +1334  f3 0f 11 44 24 04        movss    dword ptr [esp + 4], xmm0
0x100163ca +133a  f3 0f 10 45 a8           movss    xmm0, dword ptr [ebp - 0x58]
0x100163cf +133f  f3 0f 5c c1              subss    xmm0, xmm1
0x100163d3 +1343  f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x100163d8 +1348  8d 95 3c fd ff ff        lea      edx, [ebp - 0x2c4]
0x100163de +134e  52                       push     edx
0x100163df +134f  ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x100163e2 +1352  ff 50 7c                 call     dword ptr [eax + 0x7c]
0x100163e5 +1355  8b 07                    mov      eax, dword ptr [edi]
0x100163e7 +1357  8d 8d 3c fd ff ff        lea      ecx, [ebp - 0x2c4]
0x100163ed +135d  51                       push     ecx
0x100163ee +135e  8b cf                    mov      ecx, edi
0x100163f0 +1360  ff 50 58                 call     dword ptr [eax + 0x58]
0x100163f3 +1363  46                       inc      esi
0x100163f4 +1364  89 b5 10 ff ff ff        mov      dword ptr [ebp - 0xf0], esi
0x100163fa +136a  f3 0f 10 9d 54 ff ff ff  movss    xmm3, dword ptr [ebp - 0xac]
0x10016402 +1372  f3 0f 10 a5 74 ff ff ff  movss    xmm4, dword ptr [ebp - 0x8c]
0x1001640a +137a  f3 0f 10 6d 90           movss    xmm5, dword ptr [ebp - 0x70]
0x1001640f +137f  f3 0f 10 55 94           movss    xmm2, dword ptr [ebp - 0x6c]
0x10016414 +1384  f3 0f 10 75 98           movss    xmm6, dword ptr [ebp - 0x68]
0x10016419 +1389  8b 7d bc                 mov      edi, dword ptr [ebp - 0x44]
0x1001641c +138c  e9 73 fd ff ff           jmp      0x10016194
0x10016421 +1391  8b 7d bc                 mov      edi, dword ptr [ebp - 0x44]
0x10016424 +1394  8b 4d c4                 mov      ecx, dword ptr [ebp - 0x3c]
0x10016427 +1397  8b b7 30 01 00 00        mov      esi, dword ptr [edi + 0x130]
0x1001642d +139d  85 f6                    test     esi, esi
0x1001642f +139f  0f 84 73 01 00 00        je       0x100165a8
0x10016435 +13a5  8b 45 b0                 mov      eax, dword ptr [ebp - 0x50]
0x10016438 +13a8  8b 00                    mov      eax, dword ptr [eax]
0x1001643a +13aa  85 c0                    test     eax, eax
0x1001643c +13ac  74 24                    je       0x10016462
0x1001643e +13ae  f7 80 7c 04 00 00 00 48 00 00 test     dword ptr [eax + 0x47c], 0x4800   ; PF: PF_NoSmooth|PF_Flat
0x10016448 +13b8  74 18                    je       0x10016462
0x1001644a +13ba  8b 01                    mov      eax, dword ptr [ecx]
0x1001644c +13bc  ff b0 ac 00 00 00        push     dword ptr [eax + 0xac]
0x10016452 +13c2  ff b0 a8 00 00 00        push     dword ptr [eax + 0xa8]
0x10016458 +13c8  8b ce                    mov      ecx, esi
0x1001645a +13ca  ff 15 60 43 03 10        call     dword ptr [0x10034360]   ; -> Engine.dll!?Get@UTexture@@QAEPAV1@VFTime@@@Z
0x10016460 +13d0  8b f0                    mov      esi, eax
0x10016462 +13d2  8b 06                    mov      eax, dword ptr [esi]
0x10016464 +13d4  8b 7d c0                 mov      edi, dword ptr [ebp - 0x40]
0x10016467 +13d7  ff 77 5c                 push     dword ptr [edi + 0x5c]
0x1001646a +13da  6a ff                    push     -1
0x1001646c +13dc  ff b7 ac 00 00 00        push     dword ptr [edi + 0xac]
0x10016472 +13e2  ff b7 a8 00 00 00        push     dword ptr [edi + 0xa8]
0x10016478 +13e8  8d 8d bc fc ff ff        lea      ecx, [ebp - 0x344]
0x1001647e +13ee  51                       push     ecx
0x1001647f +13ef  8b ce                    mov      ecx, esi
0x10016481 +13f1  ff 50 54                 call     dword ptr [eax + 0x54]
0x10016484 +13f4  68 04 01 00 00           push     0x104   ; PF: PF_Translucent|PF_TwoSided
0x10016489 +13f9  83 ec 10                 sub      esp, 0x10
0x1001648c +13fc  8b c4                    mov      eax, esp
0x1001648e +13fe  0f 57 c0                 xorps    xmm0, xmm0
0x10016491 +1401  0f 11 00                 movups   xmmword ptr [eax], xmm0
0x10016494 +1404  8b 45 b8                 mov      eax, dword ptr [ebp - 0x48]
0x10016497 +1407  8b 4d 8c                 mov      ecx, dword ptr [ebp - 0x74]
0x1001649a +140a  f3 0f 10 4c 88 08        movss    xmm1, dword ptr [eax + ecx*4 + 8]
0x100164a0 +1410  0f 28 d1                 movaps   xmm2, xmm1
0x100164a3 +1413  f3 0f 59 95 64 ff ff ff  mulss    xmm2, dword ptr [ebp - 0x9c]
0x100164ab +141b  0f 28 c1                 movaps   xmm0, xmm1
0x100164ae +141e  f3 0f 59 85 68 ff ff ff  mulss    xmm0, dword ptr [ebp - 0x98]
0x100164b6 +1426  f3 0f 59 8d 6c ff ff ff  mulss    xmm1, dword ptr [ebp - 0x94]
0x100164be +142e  f3 0f 11 95 e4 fe ff ff  movss    dword ptr [ebp - 0x11c], xmm2
0x100164c6 +1436  f3 0f 11 85 e8 fe ff ff  movss    dword ptr [ebp - 0x118], xmm0
0x100164ce +143e  f3 0f 11 8d ec fe ff ff  movss    dword ptr [ebp - 0x114], xmm1
0x100164d6 +1446  83 ec 10                 sub      esp, 0x10
0x100164d9 +1449  8b c4                    mov      eax, esp
0x100164db +144b  f3 0f 11 10              movss    dword ptr [eax], xmm2
0x100164df +144f  f3 0f 10 85 e8 fe ff ff  movss    xmm0, dword ptr [ebp - 0x118]
0x100164e7 +1457  f3 0f 11 40 04           movss    dword ptr [eax + 4], xmm0
0x100164ec +145c  f3 0f 10 85 ec fe ff ff  movss    xmm0, dword ptr [ebp - 0x114]
0x100164f4 +1464  f3 0f 11 40 08           movss    dword ptr [eax + 8], xmm0
0x100164f9 +1469  c7 40 0c 00 00 00 00     mov      dword ptr [eax + 0xc], 0
0x10016500 +1470  8b 4f 5c                 mov      ecx, dword ptr [edi + 0x5c]
0x10016503 +1473  f3 0f 10 55 90           movss    xmm2, dword ptr [ebp - 0x70]
0x10016508 +1478  0f 28 ca                 movaps   xmm1, xmm2
0x1001650b +147b  f3 0f 59 0d 6c 4b 03 10  mulss    xmm1, dword ptr [0x10034b6c]   ; [0x10034b6c] f32=0.5
0x10016513 +1483  8b 01                    mov      eax, dword ptr [ecx]
0x10016515 +1485  51                       push     ecx
0x10016516 +1486  c7 04 24 00 00 80 3f     mov      dword ptr [esp], 0x3f800000
0x1001651d +148d  6a 00                    push     0
0x1001651f +148f  66 0f 6e 85 f0 fc ff ff  movd     xmm0, dword ptr [ebp - 0x310]
0x10016527 +1497  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x1001652a +149a  f3 0f 59 85 e8 fc ff ff  mulss    xmm0, dword ptr [ebp - 0x318]
0x10016532 +14a2  83 ec 20                 sub      esp, 0x20
0x10016535 +14a5  f3 0f 11 44 24 1c        movss    dword ptr [esp + 0x1c], xmm0
0x1001653b +14ab  66 0f 6e 85 ec fc ff ff  movd     xmm0, dword ptr [ebp - 0x314]
0x10016543 +14b3  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10016546 +14b6  f3 0f 59 85 e4 fc ff ff  mulss    xmm0, dword ptr [ebp - 0x31c]
0x1001654e +14be  f3 0f 11 44 24 18        movss    dword ptr [esp + 0x18], xmm0
0x10016554 +14c4  c7 44 24 14 00 00 00 00  mov      dword ptr [esp + 0x14], 0
0x1001655c +14cc  c7 44 24 10 00 00 00 00  mov      dword ptr [esp + 0x10], 0
0x10016564 +14d4  f3 0f 11 54 24 0c        movss    dword ptr [esp + 0xc], xmm2
0x1001656a +14da  f3 0f 11 54 24 08        movss    dword ptr [esp + 8], xmm2
0x10016570 +14e0  f3 0f 10 45 98           movss    xmm0, dword ptr [ebp - 0x68]
0x10016575 +14e5  f3 0f 5c c1              subss    xmm0, xmm1
0x10016579 +14e9  f3 0f 11 44 24 04        movss    dword ptr [esp + 4], xmm0
0x1001657f +14ef  f3 0f 10 45 94           movss    xmm0, dword ptr [ebp - 0x6c]
0x10016584 +14f4  f3 0f 5c c1              subss    xmm0, xmm1
0x10016588 +14f8  f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x1001658d +14fd  8d 95 bc fc ff ff        lea      edx, [ebp - 0x344]
0x10016593 +1503  52                       push     edx
0x10016594 +1504  ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x10016597 +1507  ff 50 7c                 call     dword ptr [eax + 0x7c]
0x1001659a +150a  8b 06                    mov      eax, dword ptr [esi]
0x1001659c +150c  8d 8d bc fc ff ff        lea      ecx, [ebp - 0x344]
0x100165a2 +1512  51                       push     ecx
0x100165a3 +1513  8b ce                    mov      ecx, esi
0x100165a5 +1515  ff 50 58                 call     dword ptr [eax + 0x58]
0x100165a8 +1518  8b b5 58 ff ff ff        mov      esi, dword ptr [ebp - 0xa8]
0x100165ae +151e  46                       inc      esi
0x100165af +151f  89 b5 58 ff ff ff        mov      dword ptr [ebp - 0xa8], esi
0x100165b5 +1525  8b 7d b8                 mov      edi, dword ptr [ebp - 0x48]
0x100165b8 +1528  e9 07 f9 ff ff           jmp      0x10015ec4
0x100165bd +152d  8b 4d a4                 mov      ecx, dword ptr [ebp - 0x5c]
0x100165c0 +1530  85 c9                    test     ecx, ecx
0x100165c2 +1532  74 0d                    je       0x100165d1
0x100165c4 +1534  8b 41 10                 mov      eax, dword ptr [ecx + 0x10]
0x100165c7 +1537  2d 00 00 00 01           sub      eax, 0x1000000
0x100165cc +153c  89 41 10                 mov      dword ptr [ecx + 0x10], eax
0x100165cf +153f  eb 0f                    jmp      0x100165e0
0x100165d1 +1541  85 ff                    test     edi, edi
0x100165d3 +1543  74 0b                    je       0x100165e0
0x100165d5 +1545  6a 0c                    push     0xc   ; PF: PF_Translucent|PF_NotSolid
0x100165d7 +1547  57                       push     edi
0x100165d8 +1548  e8 fd b4 00 00           call     0x10021ada   ; -> sub_21ada
0x100165dd +154d  83 c4 08                 add      esp, 8
0x100165e0 +1550  8b 75 c0                 mov      esi, dword ptr [ebp - 0x40]
0x100165e3 +1553  8b 55 c4                 mov      edx, dword ptr [ebp - 0x3c]
0x100165e6 +1556  8b 42 18                 mov      eax, dword ptr [edx + 0x18]
0x100165e9 +1559  8d 0c 40                 lea      ecx, [eax + eax*2]
0x100165ec +155c  8b 42 04                 mov      eax, dword ptr [edx + 4]
0x100165ef +155f  8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x100165f5 +1565  ff b4 c8 04 01 00 00     push     dword ptr [eax + ecx*8 + 0x104]
0x100165fc +156c  e8 3f b5 ff ff           call     0x10011b40   ; -> sub_11b40
0x10016601 +1571  83 c4 04                 add      esp, 4
0x10016604 +1574  85 c0                    test     eax, eax
0x10016606 +1576  74 0e                    je       0x10016616
0x10016608 +1578  8b 4e 5c                 mov      ecx, dword ptr [esi + 0x5c]
0x1001660b +157b  8b 01                    mov      eax, dword ptr [ecx]
0x1001660d +157d  ff 75 c4                 push     dword ptr [ebp - 0x3c]
0x10016610 +1580  ff 90 90 00 00 00        call     dword ptr [eax + 0x90]
0x10016616 +1586  8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x1001661c +158c  8b 35 f4 40 03 10        mov      esi, dword ptr [0x100340f4]
0x10016622 +1592  ff d6                    call     esi
0x10016624 +1594  01 05 18 fb 05 10        add      dword ptr [0x1005fb18], eax
0x1001662a +159a  b9 f0 6b 04 10           mov      ecx, 0x10046bf0
0x1001662f +159f  ff d6                    call     esi
0x10016631 +15a1  01 05 1c fb 05 10        add      dword ptr [0x1005fb1c], eax
0x10016637 +15a7  8b 45 c4                 mov      eax, dword ptr [ebp - 0x3c]
0x1001663a +15aa  8b 40 04                 mov      eax, dword ptr [eax + 4]
0x1001663d +15ad  8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x10016643 +15b3  8b 40 5c                 mov      eax, dword ptr [eax + 0x5c]
0x10016646 +15b6  01 05 b4 fa 05 10        add      dword ptr [0x1005fab4], eax
0x1001664c +15bc  9b                       wait     
0x1001664d +15bd  c7 45 fc ff ff ff ff     mov      dword ptr [ebp - 4], 0xffffffff
0x10016654 +15c4  8b 4d f4                 mov      ecx, dword ptr [ebp - 0xc]
0x10016657 +15c7  64 89 0d 00 00 00 00     mov      dword ptr fs:[0], ecx
0x1001665e +15ce  59                       pop      ecx
0x1001665f +15cf  5f                       pop      edi
0x10016660 +15d0  5e                       pop      esi
0x10016661 +15d1  5b                       pop      ebx
0x10016662 +15d2  8b 4d ec                 mov      ecx, dword ptr [ebp - 0x14]
0x10016665 +15d5  33 cd                    xor      ecx, ebp
0x10016667 +15d7  e8 7c b4 00 00           call     0x10021ae8   ; -> sub_21ae8
0x1001666c +15dc  8b e5                    mov      esp, ebp
0x1001666e +15de  5d                       pop      ebp
0x1001666f +15df  c2 04 00                 ret      4
0x10016672 +15e2  68 30 6e 03 10           push     0x10036e30
0x10016677 +15e7  eb 22                    jmp      0x1001669b
0x10016679 +15e9  8b 85 58 fe ff ff        mov      eax, dword ptr [ebp - 0x1a8]
0x1001667f +15ef  89 85 24 ff ff ff        mov      dword ptr [ebp - 0xdc], eax
0x10016685 +15f5  68 7c ea 03 10           push     0x1003ea7c
0x1001668a +15fa  8d 85 24 ff ff ff        lea      eax, [ebp - 0xdc]
0x10016690 +1600  50                       push     eax
0x10016691 +1601  e8 8e cd 00 00           call     0x10023424   ; -> sub_23424
0x10016696 +1606  68 58 6e 03 10           push     0x10036e58
0x1001669b +160b  68 88 46 03 10           push     0x10034688
0x100166a0 +1610  ff 15 88 41 03 10        call     dword ptr [0x10034188]   ; -> Core.dll!?appUnwindf@@YAXPBGZZ
0x100166a6 +1616  83 c4 08                 add      esp, 8
0x100166a9 +1619  6a 00                    push     0
0x100166ab +161b  6a 00                    push     0
0x100166ad +161d  e8 72 cd 00 00           call     0x10023424   ; -> sub_23424
0x100166b2 +1622  68 7c 15 06 10           push     0x1006157c
0x100166b7 +1627  e8 08 ba 00 00           call     0x100220c4   ; -> sub_220c4
0x100166bc +162c  83 c4 04                 add      esp, 4
0x100166bf +162f  83 3d 7c 15 06 10 ff     cmp      dword ptr [0x1006157c], -1
0x100166c6 +1636  0f 85 b9 f7 ff ff        jne      0x10015e85
0x100166cc +163c  c6 45 fc 03              mov      byte ptr [ebp - 4], 3   ; PF: PF_Invisible|PF_Masked
0x100166d0 +1640  0f 31                    rdtsc    
0x100166d2 +1642  a3 74 15 06 10           mov      dword ptr [0x10061574], eax
0x100166d7 +1647  89 15 78 15 06 10        mov      dword ptr [0x10061578], edx
0x100166dd +164d  c6 45 fc 00              mov      byte ptr [ebp - 4], 0
0x100166e1 +1651  68 7c 15 06 10           push     0x1006157c
0x100166e6 +1656  e8 8f b9 00 00           call     0x1002207a   ; -> sub_2207a
0x100166eb +165b  83 c4 04                 add      esp, 4
0x100166ee +165e  e9 92 f7 ff ff           jmp      0x10015e85
0x100166f3 +1663  8b 85 94 fe ff ff        mov      eax, dword ptr [ebp - 0x16c]
0x100166f9 +1669  89 85 14 ff ff ff        mov      dword ptr [ebp - 0xec], eax
0x100166ff +166f  68 7c ea 03 10           push     0x1003ea7c
0x10016704 +1674  8d 85 14 ff ff ff        lea      eax, [ebp - 0xec]
0x1001670a +167a  50                       push     eax
0x1001670b +167b  e8 14 cd 00 00           call     0x10023424   ; -> sub_23424
0x10016710 +1680  cc                       int3     
0x10016711 +1681  cc                       int3     
0x10016712 +1682  cc                       int3     
0x10016713 +1683  cc                       int3     
0x10016714 +1684  cc                       int3     
0x10016715 +1685  cc                       int3     
0x10016716 +1686  cc                       int3     
0x10016717 +1687  cc                       int3     
0x10016718 +1688  cc                       int3     
0x10016719 +1689  cc                       int3     
0x1001671a +168a  cc                       int3     
0x1001671b +168b  cc                       int3     
0x1001671c +168c  cc                       int3     
0x1001671d +168d  cc                       int3     
0x1001671e +168e  cc                       int3     
0x1001671f +168f  cc                       int3     

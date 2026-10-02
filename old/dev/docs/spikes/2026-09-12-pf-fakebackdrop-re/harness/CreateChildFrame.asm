0x100149c0 +0     55                       push     ebp
0x100149c1 +1     8b ec                    mov      ebp, esp
0x100149c3 +3     6a ff                    push     -1
0x100149c5 +5     68 20 34 03 10           push     0x10033420
0x100149ca +a     64 a1 00 00 00 00        mov      eax, dword ptr fs:[0]
0x100149d0 +10    50                       push     eax
0x100149d1 +11    83 ec 3c                 sub      esp, 0x3c
0x100149d4 +14    53                       push     ebx
0x100149d5 +15    56                       push     esi
0x100149d6 +16    57                       push     edi
0x100149d7 +17    a1 3c 60 04 10           mov      eax, dword ptr [0x1004603c]   ; [0x1004603c] f32=-0.002943414729088545
0x100149dc +1c    33 c5                    xor      eax, ebp
0x100149de +1e    50                       push     eax
0x100149df +1f    8d 45 f4                 lea      eax, [ebp - 0xc]
0x100149e2 +22    64 a3 00 00 00 00        mov      dword ptr fs:[0], eax
0x100149e8 +28    89 65 f0                 mov      dword ptr [ebp - 0x10], esp
0x100149eb +2b    c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x100149f2 +32    9b                       wait     
0x100149f3 +33    8b 75 08                 mov      esi, dword ptr [ebp + 8]
0x100149f6 +36    8b 7e 10                 mov      edi, dword ptr [esi + 0x10]
0x100149f9 +39    0f 1f 80 00 00 00 00     nop      dword ptr [eax]
0x10014a00 +40    85 ff                    test     edi, edi
0x10014a02 +42    0f 84 0c 01 00 00        je       0x10014b14
0x10014a08 +48    8b 45 10                 mov      eax, dword ptr [ebp + 0x10]
0x10014a0b +4b    39 47 04                 cmp      dword ptr [edi + 4], eax
0x10014a0e +4e    0f 85 f8 00 00 00        jne      0x10014b0c
0x10014a14 +54    8b 45 14                 mov      eax, dword ptr [ebp + 0x14]
0x10014a17 +57    39 47 14                 cmp      dword ptr [edi + 0x14], eax
0x10014a1a +5a    0f 85 ec 00 00 00        jne      0x10014b0c
0x10014a20 +60    39 77 08                 cmp      dword ptr [edi + 8], esi
0x10014a23 +63    0f 85 e3 00 00 00        jne      0x10014b0c
0x10014a29 +69    ff 75 20                 push     dword ptr [ebp + 0x20]
0x10014a2c +6c    8d 4f 24                 lea      ecx, [edi + 0x24]
0x10014a2f +6f    ff 15 d4 40 03 10        call     dword ptr [0x100340d4]   ; -> Core.dll!??8FPlane@@QBEHABV0@@Z
0x10014a35 +75    85 c0                    test     eax, eax
0x10014a37 +77    0f 84 cf 00 00 00        je       0x10014b0c
0x10014a3d +7d    8b 45 18                 mov      eax, dword ptr [ebp + 0x18]
0x10014a40 +80    39 47 18                 cmp      dword ptr [edi + 0x18], eax
0x10014a43 +83    0f 85 c3 00 00 00        jne      0x10014b0c
0x10014a49 +89    ff 75 0c                 push     dword ptr [ebp + 0xc]
0x10014a4c +8c    8b 8f 94 00 00 00        mov      ecx, dword ptr [edi + 0x94]
0x10014a52 +92    e8 59 99 00 00           call     0x1001e3b0   ; -> ?MergeWith@FSpanBuffer@@QAEXABV1@@Z
0x10014a57 +97    8b 45 28                 mov      eax, dword ptr [ebp + 0x28]
0x10014a5a +9a    85 c0                    test     eax, eax
0x10014a5c +9c    0f 84 24 02 00 00        je       0x10014c86
0x10014a62 +a2    f3 0f 10 8f ec 00 00 00  movss    xmm1, dword ptr [edi + 0xec]
0x10014a6a +aa    f3 0f 10 97 c8 00 00 00  movss    xmm2, dword ptr [edi + 0xc8]
0x10014a72 +b2    f3 0f 10 a7 e8 00 00 00  movss    xmm4, dword ptr [edi + 0xe8]
0x10014a7a +ba    0f 28 dc                 movaps   xmm3, xmm4
0x10014a7d +bd    0f 57 1d f0 52 03 10     xorps    xmm3, xmmword ptr [0x100352f0]   ; [0x100352f0] f32=-0.0
0x10014a84 +c4    f3 0f 10 00              movss    xmm0, dword ptr [eax]
0x10014a88 +c8    f3 0f 5c c2              subss    xmm0, xmm2
0x10014a8c +cc    f3 0f 59 c3              mulss    xmm0, xmm3
0x10014a90 +d0    f3 0f 5f c8              maxss    xmm1, xmm0
0x10014a94 +d4    f3 0f 11 8f ec 00 00 00  movss    dword ptr [edi + 0xec], xmm1
0x10014a9c +dc    f3 0f 10 8f f4 00 00 00  movss    xmm1, dword ptr [edi + 0xf4]
0x10014aa4 +e4    f3 0f 10 40 08           movss    xmm0, dword ptr [eax + 8]
0x10014aa9 +e9    f3 0f 5c c2              subss    xmm0, xmm2
0x10014aad +ed    f3 0f 59 c4              mulss    xmm0, xmm4
0x10014ab1 +f1    f3 0f 5f c8              maxss    xmm1, xmm0
0x10014ab5 +f5    f3 0f 11 8f f4 00 00 00  movss    dword ptr [edi + 0xf4], xmm1
0x10014abd +fd    f3 0f 10 8f f0 00 00 00  movss    xmm1, dword ptr [edi + 0xf0]
0x10014ac5 +105   f3 0f 10 97 cc 00 00 00  movss    xmm2, dword ptr [edi + 0xcc]
0x10014acd +10d   f3 0f 10 40 04           movss    xmm0, dword ptr [eax + 4]
0x10014ad2 +112   f3 0f 5c c2              subss    xmm0, xmm2
0x10014ad6 +116   f3 0f 59 c3              mulss    xmm0, xmm3
0x10014ada +11a   f3 0f 5f c8              maxss    xmm1, xmm0
0x10014ade +11e   f3 0f 11 8f f0 00 00 00  movss    dword ptr [edi + 0xf0], xmm1
0x10014ae6 +126   f3 0f 10 8f f8 00 00 00  movss    xmm1, dword ptr [edi + 0xf8]
0x10014aee +12e   f3 0f 10 40 0c           movss    xmm0, dword ptr [eax + 0xc]
0x10014af3 +133   f3 0f 5c c2              subss    xmm0, xmm2
0x10014af7 +137   f3 0f 59 c4              mulss    xmm0, xmm4
0x10014afb +13b   f3 0f 5f c8              maxss    xmm1, xmm0
0x10014aff +13f   f3 0f 11 8f f8 00 00 00  movss    dword ptr [edi + 0xf8], xmm1
0x10014b07 +147   e9 7a 01 00 00           jmp      0x10014c86
0x10014b0c +14c   8b 7f 0c                 mov      edi, dword ptr [edi + 0xc]
0x10014b0f +14f   e9 ec fe ff ff           jmp      0x10014a00
0x10014b14 +154   6a 10                    push     0x10   ; PF: PF_Environment
0x10014b16 +156   68 6c 01 00 00           push     0x16c   ; PF: PF_Translucent|PF_NotSolid|PF_Semisolid|PF_Modulated|PF_TwoSided
0x10014b1b +15b   b9 00 6c 04 10           mov      ecx, 0x10046c00
0x10014b20 +160   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x10014b26 +166   85 c0                    test     eax, eax
0x10014b28 +168   74 0d                    je       0x10014b37
0x10014b2a +16a   56                       push     esi
0x10014b2b +16b   8b c8                    mov      ecx, eax
0x10014b2d +16d   ff 15 14 43 03 10        call     dword ptr [0x10034314]   ; -> Engine.dll!??0FSceneNode@@QAE@ABU0@@Z
0x10014b33 +173   8b f8                    mov      edi, eax
0x10014b35 +175   eb 02                    jmp      0x10014b39
0x10014b37 +177   33 ff                    xor      edi, edi
0x10014b39 +179   6a 10                    push     0x10   ; PF: PF_Environment
0x10014b3b +17b   6a 20                    push     0x20   ; PF: PF_Semisolid
0x10014b3d +17d   b9 00 6c 04 10           mov      ecx, 0x10046c00
0x10014b42 +182   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x10014b48 +188   89 87 94 00 00 00        mov      dword ptr [edi + 0x94], eax
0x10014b4e +18e   8b 06                    mov      eax, dword ptr [esi]
0x10014b50 +190   89 07                    mov      dword ptr [edi], eax
0x10014b52 +192   8b 45 10                 mov      eax, dword ptr [ebp + 0x10]
0x10014b55 +195   89 47 04                 mov      dword ptr [edi + 4], eax
0x10014b58 +198   8b 45 14                 mov      eax, dword ptr [ebp + 0x14]
0x10014b5b +19b   89 47 14                 mov      dword ptr [edi + 0x14], eax
0x10014b5e +19e   8b 45 18                 mov      eax, dword ptr [ebp + 0x18]
0x10014b61 +1a1   89 47 18                 mov      dword ptr [edi + 0x18], eax
0x10014b64 +1a4   8b 46 1c                 mov      eax, dword ptr [esi + 0x1c]
0x10014b67 +1a7   40                       inc      eax
0x10014b68 +1a8   89 47 1c                 mov      dword ptr [edi + 0x1c], eax
0x10014b6b +1ab   f3 0f 10 45 1c           movss    xmm0, dword ptr [ebp + 0x1c]
0x10014b70 +1b0   f3 0f 11 47 20           movss    dword ptr [edi + 0x20], xmm0
0x10014b75 +1b5   8b 45 20                 mov      eax, dword ptr [ebp + 0x20]
0x10014b78 +1b8   0f 10 00                 movups   xmm0, xmmword ptr [eax]
0x10014b7b +1bb   0f 11 47 24              movups   xmmword ptr [edi + 0x24], xmm0
0x10014b7f +1bf   8b 75 24                 mov      esi, dword ptr [ebp + 0x24]
0x10014b82 +1c2   56                       push     esi
0x10014b83 +1c3   8d 4f 34                 lea      ecx, [edi + 0x34]
0x10014b86 +1c6   ff 15 78 42 03 10        call     dword ptr [0x10034278]   ; -> Core.dll!??4FCoords@@QAEAAV0@ABV0@@Z
0x10014b8c +1cc   8d 45 b8                 lea      eax, [ebp - 0x48]
0x10014b8f +1cf   50                       push     eax
0x10014b90 +1d0   8b ce                    mov      ecx, esi
0x10014b92 +1d2   ff 15 24 42 03 10        call     dword ptr [0x10034224]   ; -> Core.dll!?Transpose@FCoords@@QBE?AV1@XZ
0x10014b98 +1d8   50                       push     eax
0x10014b99 +1d9   8d 4f 64                 lea      ecx, [edi + 0x64]
0x10014b9c +1dc   ff 15 2c 42 03 10        call     dword ptr [0x1003422c]   ; -> Core.dll!??4FCoords@@QAEAAV0@$$QAV0@@Z
0x10014ba2 +1e2   c7 87 98 00 00 00 00 00 00 00 mov      dword ptr [edi + 0x98], 0
0x10014bac +1ec   c7 87 9c 00 00 00 00 00 00 00 mov      dword ptr [edi + 0x9c], 0
0x10014bb6 +1f6   c7 87 a0 00 00 00 00 00 00 00 mov      dword ptr [edi + 0xa0], 0
0x10014bc0 +200   c7 87 a4 00 00 00 00 00 00 00 mov      dword ptr [edi + 0xa4], 0
0x10014bca +20a   8b 4d 08                 mov      ecx, dword ptr [ebp + 8]
0x10014bcd +20d   89 4f 08                 mov      dword ptr [edi + 8], ecx
0x10014bd0 +210   c7 47 10 00 00 00 00     mov      dword ptr [edi + 0x10], 0
0x10014bd7 +217   8b 41 10                 mov      eax, dword ptr [ecx + 0x10]
0x10014bda +21a   89 47 0c                 mov      dword ptr [edi + 0xc], eax
0x10014bdd +21d   89 79 10                 mov      dword ptr [ecx + 0x10], edi
0x10014be0 +220   8b cf                    mov      ecx, edi
0x10014be2 +222   ff 15 20 43 03 10        call     dword ptr [0x10034320]   ; -> Engine.dll!?ComputeRenderSize@FSceneNode@@QAEXXZ
0x10014be8 +228   8b 45 28                 mov      eax, dword ptr [ebp + 0x28]
0x10014beb +22b   85 c0                    test     eax, eax
0x10014bed +22d   74 75                    je       0x10014c64
0x10014bef +22f   f3 0f 10 8f c8 00 00 00  movss    xmm1, dword ptr [edi + 0xc8]
0x10014bf7 +237   f3 0f 10 9f e8 00 00 00  movss    xmm3, dword ptr [edi + 0xe8]
0x10014bff +23f   0f 28 d3                 movaps   xmm2, xmm3
0x10014c02 +242   0f 57 15 f0 52 03 10     xorps    xmm2, xmmword ptr [0x100352f0]   ; [0x100352f0] f32=-0.0
0x10014c09 +249   f3 0f 10 00              movss    xmm0, dword ptr [eax]
0x10014c0d +24d   f3 0f 5c c1              subss    xmm0, xmm1
0x10014c11 +251   f3 0f 59 c2              mulss    xmm0, xmm2
0x10014c15 +255   f3 0f 11 87 ec 00 00 00  movss    dword ptr [edi + 0xec], xmm0
0x10014c1d +25d   f3 0f 10 40 08           movss    xmm0, dword ptr [eax + 8]
0x10014c22 +262   f3 0f 5c c1              subss    xmm0, xmm1
0x10014c26 +266   f3 0f 59 c3              mulss    xmm0, xmm3
0x10014c2a +26a   f3 0f 11 87 f4 00 00 00  movss    dword ptr [edi + 0xf4], xmm0
0x10014c32 +272   f3 0f 10 8f cc 00 00 00  movss    xmm1, dword ptr [edi + 0xcc]
0x10014c3a +27a   f3 0f 10 40 04           movss    xmm0, dword ptr [eax + 4]
0x10014c3f +27f   f3 0f 5c c1              subss    xmm0, xmm1
0x10014c43 +283   f3 0f 59 c2              mulss    xmm0, xmm2
0x10014c47 +287   f3 0f 11 87 f0 00 00 00  movss    dword ptr [edi + 0xf0], xmm0
0x10014c4f +28f   f3 0f 10 40 0c           movss    xmm0, dword ptr [eax + 0xc]
0x10014c54 +294   f3 0f 5c c1              subss    xmm0, xmm1
0x10014c58 +298   f3 0f 59 c3              mulss    xmm0, xmm3
0x10014c5c +29c   f3 0f 11 87 f8 00 00 00  movss    dword ptr [edi + 0xf8], xmm0
0x10014c64 +2a4   68 00 6c 04 10           push     0x10046c00
0x10014c69 +2a9   6a 00                    push     0
0x10014c6b +2ab   6a 00                    push     0
0x10014c6d +2ad   8b 8f 94 00 00 00        mov      ecx, dword ptr [edi + 0x94]
0x10014c73 +2b3   e8 78 88 00 00           call     0x1001d4f0   ; -> ?AllocIndex@FSpanBuffer@@QAEXHHPAVFMemStack@@@Z
0x10014c78 +2b8   ff 75 0c                 push     dword ptr [ebp + 0xc]
0x10014c7b +2bb   8b 8f 94 00 00 00        mov      ecx, dword ptr [edi + 0x94]
0x10014c81 +2c1   e8 2a 97 00 00           call     0x1001e3b0   ; -> ?MergeWith@FSpanBuffer@@QAEXABV1@@Z
0x10014c86 +2c6   8b c7                    mov      eax, edi
0x10014c88 +2c8   9b                       wait     
0x10014c89 +2c9   8b 4d f4                 mov      ecx, dword ptr [ebp - 0xc]
0x10014c8c +2cc   64 89 0d 00 00 00 00     mov      dword ptr fs:[0], ecx
0x10014c93 +2d3   59                       pop      ecx
0x10014c94 +2d4   5f                       pop      edi
0x10014c95 +2d5   5e                       pop      esi
0x10014c96 +2d6   5b                       pop      ebx
0x10014c97 +2d7   8b e5                    mov      esp, ebp
0x10014c99 +2d9   5d                       pop      ebp
0x10014c9a +2da   c2 24 00                 ret      0x24
0x10014c9d +2dd   68 e4 6b 03 10           push     0x10036be4
0x10014ca2 +2e2   68 88 46 03 10           push     0x10034688
0x10014ca7 +2e7   ff 15 88 41 03 10        call     dword ptr [0x10034188]   ; -> Core.dll!?appUnwindf@@YAXPBGZZ
0x10014cad +2ed   83 c4 08                 add      esp, 8
0x10014cb0 +2f0   6a 00                    push     0
0x10014cb2 +2f2   6a 00                    push     0
0x10014cb4 +2f4   e8 6b e7 00 00           call     0x10023424   ; -> sub_23424
0x10014cb9 +2f9   8b 45 e8                 mov      eax, dword ptr [ebp - 0x18]
0x10014cbc +2fc   89 45 ec                 mov      dword ptr [ebp - 0x14], eax
0x10014cbf +2ff   68 7c ea 03 10           push     0x1003ea7c
0x10014cc4 +304   8d 45 ec                 lea      eax, [ebp - 0x14]
0x10014cc7 +307   50                       push     eax
0x10014cc8 +308   e8 57 e7 00 00           call     0x10023424   ; -> sub_23424
0x10014ccd +30d   cc                       int3     
0x10014cce +30e   cc                       int3     
0x10014ccf +30f   cc                       int3     
0x10014cd0 +310   cc                       int3     
0x10014cd1 +311   cc                       int3     
0x10014cd2 +312   cc                       int3     
0x10014cd3 +313   cc                       int3     
0x10014cd4 +314   cc                       int3     
0x10014cd5 +315   cc                       int3     
0x10014cd6 +316   cc                       int3     
0x10014cd7 +317   cc                       int3     
0x10014cd8 +318   cc                       int3     
0x10014cd9 +319   cc                       int3     
0x10014cda +31a   cc                       int3     
0x10014cdb +31b   cc                       int3     
0x10014cdc +31c   cc                       int3     
0x10014cdd +31d   cc                       int3     
0x10014cde +31e   cc                       int3     
0x10014cdf +31f   cc                       int3     

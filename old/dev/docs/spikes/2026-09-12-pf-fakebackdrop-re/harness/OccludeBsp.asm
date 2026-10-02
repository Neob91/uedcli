0x10018e10 +0     55                       push     ebp
0x10018e11 +1     8b ec                    mov      ebp, esp
0x10018e13 +3     6a ff                    push     -1
0x10018e15 +5     68 21 36 03 10           push     0x10033621
0x10018e1a +a     64 a1 00 00 00 00        mov      eax, dword ptr fs:[0]
0x10018e20 +10    50                       push     eax
0x10018e21 +11    81 ec 10 0b 00 00        sub      esp, 0xb10
0x10018e27 +17    a1 3c 60 04 10           mov      eax, dword ptr [0x1004603c]   ; [0x1004603c] f32=-0.002943414729088545
0x10018e2c +1c    33 c5                    xor      eax, ebp
0x10018e2e +1e    89 45 ec                 mov      dword ptr [ebp - 0x14], eax
0x10018e31 +21    53                       push     ebx
0x10018e32 +22    56                       push     esi
0x10018e33 +23    57                       push     edi
0x10018e34 +24    50                       push     eax
0x10018e35 +25    8d 45 f4                 lea      eax, [ebp - 0xc]
0x10018e38 +28    64 a3 00 00 00 00        mov      dword ptr fs:[0], eax
0x10018e3e +2e    89 65 f0                 mov      dword ptr [ebp - 0x10], esp
0x10018e41 +31    89 8d 48 f7 ff ff        mov      dword ptr [ebp - 0x8b8], ecx
0x10018e47 +37    8b 7d 08                 mov      edi, dword ptr [ebp + 8]
0x10018e4a +3a    89 bd 4c f7 ff ff        mov      dword ptr [ebp - 0x8b4], edi
0x10018e50 +40    c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x10018e57 +47    9b                       wait     
0x10018e58 +48    8b 47 04                 mov      eax, dword ptr [edi + 4]
0x10018e5b +4b    8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x10018e61 +51    8b 35 84 41 03 10        mov      esi, dword ptr [0x10034184]
0x10018e67 +57    81 b8 8c 00 00 00 00 f4 01 00 cmp      dword ptr [eax + 0x8c], 0x1f400   ; PF: PF_AutoVPan|PF_BigWavy|PF_SmallWavy|PF_Flat|PF_LowShadowDetail|PF_NoMerge
0x10018e71 +61    7e 14                    jle      0x10018e87
0x10018e73 +63    68 ff 05 00 00           push     0x5ff   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Environment|PF_Semisolid|PF_Modulated|PF_FakeBackdrop|PF_TwoSided|PF_AutoVPan
0x10018e78 +68    68 a0 6b 03 10           push     0x10036ba0
0x10018e7d +6d    68 38 6d 03 10           push     0x10036d38
0x10018e82 +72    ff d6                    call     esi
0x10018e84 +74    83 c4 0c                 add      esp, 0xc
0x10018e87 +77    8b 47 04                 mov      eax, dword ptr [edi + 4]
0x10018e8a +7a    8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x10018e90 +80    89 85 20 f7 ff ff        mov      dword ptr [ebp - 0x8e0], eax
0x10018e96 +86    83 78 5c 00              cmp      dword ptr [eax + 0x5c], 0
0x10018e9a +8a    0f 84 93 03 00 00        je       0x10019233
0x10018ea0 +90    0f 31                    rdtsc    
0x10018ea2 +92    29 05 a0 fa 05 10        sub      dword ptr [0x1005faa0], eax
0x10018ea8 +98    33 c0                    xor      eax, eax
0x10018eaa +9a    89 85 d8 f6 ff ff        mov      dword ptr [ebp - 0x928], eax
0x10018eb0 +a0    a1 c0 41 03 10           mov      eax, dword ptr [0x100341c0]
0x10018eb5 +a5    83 38 00                 cmp      dword ptr [eax], 0
0x10018eb8 +a8    74 3e                    je       0x10018ef8
0x10018eba +aa    8d 8d 64 f6 ff ff        lea      ecx, [ebp - 0x99c]
0x10018ec0 +b0    e8 6b 8f ff ff           call     0x10011e30   ; -> sub_11e30
0x10018ec5 +b5    a1 18 40 03 10           mov      eax, dword ptr [0x10034018]
0x10018eca +ba    8b 8d 68 f6 ff ff        mov      ecx, dword ptr [ebp - 0x998]
0x10018ed0 +c0    3b 48 04                 cmp      ecx, dword ptr [eax + 4]
0x10018ed3 +c3    7d 23                    jge      0x10018ef8
0x10018ed5 +c5    8b 00                    mov      eax, dword ptr [eax]
0x10018ed7 +c7    8b 04 88                 mov      eax, dword ptr [eax + ecx*4]
0x10018eda +ca    89 85 d8 f6 ff ff        mov      dword ptr [ebp - 0x928], eax
0x10018ee0 +d0    85 c0                    test     eax, eax
0x10018ee2 +d2    75 14                    jne      0x10018ef8
0x10018ee4 +d4    68 11 06 00 00           push     0x611   ; PF: PF_Invisible|PF_Environment|PF_AutoUPan|PF_AutoVPan
0x10018ee9 +d9    68 a0 6b 03 10           push     0x10036ba0
0x10018eee +de    68 68 6d 03 10           push     0x10036d68
0x10018ef3 +e3    ff d6                    call     esi
0x10018ef5 +e5    83 c4 0c                 add      esp, 0xc
0x10018ef8 +e8    ff 05 1c fa 05 10        inc      dword ptr [0x1005fa1c]   ; data ?Stamp@URender@@2KA
0x10018efe +ee    8b 37                    mov      esi, dword ptr [edi]
0x10018f00 +f0    89 b5 d4 f6 ff ff        mov      dword ptr [ebp - 0x92c], esi
0x10018f06 +f6    8b 46 5c                 mov      eax, dword ptr [esi + 0x5c]
0x10018f09 +f9    89 85 0c f7 ff ff        mov      dword ptr [ebp - 0x8f4], eax
0x10018f0f +ff    89 85 2c f6 ff ff        mov      dword ptr [ebp - 0x9d4], eax
0x10018f15 +105   6a 10                    push     0x10   ; PF: PF_Environment
0x10018f17 +107   6a 4c                    push     0x4c   ; PF: PF_Translucent|PF_NotSolid|PF_Modulated
0x10018f19 +109   8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x10018f1f +10f   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x10018f25 +115   89 85 38 f7 ff ff        mov      dword ptr [ebp - 0x8c8], eax
0x10018f2b +11b   6a 10                    push     0x10   ; PF: PF_Environment
0x10018f2d +11d   8b 85 20 f7 ff ff        mov      eax, dword ptr [ebp - 0x8e0]
0x10018f33 +123   ff b0 9c 00 00 00        push     dword ptr [eax + 0x9c]
0x10018f39 +129   6a 01                    push     1   ; PF: PF_Invisible
0x10018f3b +12b   ff 35 b8 41 03 10        push     dword ptr [0x100341b8]
0x10018f41 +131   6a 04                    push     4   ; PF: PF_Translucent
0x10018f43 +133   e8 78 a4 fe ff           call     0x100033c0   ; -> sub_33c0
0x10018f48 +138   83 c4 14                 add      esp, 0x14
0x10018f4b +13b   89 85 b8 f6 ff ff        mov      dword ptr [ebp - 0x948], eax
0x10018f51 +141   8d 47 34                 lea      eax, [edi + 0x34]
0x10018f54 +144   89 85 ec f6 ff ff        mov      dword ptr [ebp - 0x914], eax
0x10018f5a +14a   f3 0f 10 00              movss    xmm0, dword ptr [eax]
0x10018f5e +14e   f3 0f 11 85 98 f6 ff ff  movss    dword ptr [ebp - 0x968], xmm0
0x10018f66 +156   f3 0f 10 40 04           movss    xmm0, dword ptr [eax + 4]
0x10018f6b +15b   f3 0f 11 85 9c f6 ff ff  movss    dword ptr [ebp - 0x964], xmm0
0x10018f73 +163   f3 0f 10 40 08           movss    xmm0, dword ptr [eax + 8]
0x10018f78 +168   f3 0f 11 85 a0 f6 ff ff  movss    dword ptr [ebp - 0x960], xmm0
0x10018f80 +170   ff 15 3c 43 03 10        call     dword ptr [0x1003433c]   ; -> Engine.dll!?StaticClass@APlayerPawn@@SAPAVUClass@@XZ
0x10018f86 +176   8b d0                    mov      edx, eax
0x10018f88 +178   83 c6 30                 add      esi, 0x30
0x10018f8b +17b   89 b5 f8 f6 ff ff        mov      dword ptr [ebp - 0x908], esi
0x10018f91 +181   8b 0e                    mov      ecx, dword ptr [esi]
0x10018f93 +183   8b 49 24                 mov      ecx, dword ptr [ecx + 0x24]
0x10018f96 +186   85 c9                    test     ecx, ecx
0x10018f98 +188   74 09                    je       0x10018fa3
0x10018f9a +18a   3b ca                    cmp      ecx, edx
0x10018f9c +18c   74 10                    je       0x10018fae
0x10018f9e +18e   8b 49 28                 mov      ecx, dword ptr [ecx + 0x28]
0x10018fa1 +191   eb f3                    jmp      0x10018f96
0x10018fa3 +193   33 c0                    xor      eax, eax
0x10018fa5 +195   85 d2                    test     edx, edx
0x10018fa7 +197   0f 94 c0                 sete     al
0x10018faa +19a   85 c0                    test     eax, eax
0x10018fac +19c   74 35                    je       0x10018fe3
0x10018fae +19e   8b 36                    mov      esi, dword ptr [esi]
0x10018fb0 +1a0   8b d6                    mov      edx, esi
0x10018fb2 +1a2   89 b5 d0 f6 ff ff        mov      dword ptr [ebp - 0x930], esi
0x10018fb8 +1a8   85 f6                    test     esi, esi
0x10018fba +1aa   74 35                    je       0x10018ff1
0x10018fbc +1ac   8b 06                    mov      eax, dword ptr [esi]
0x10018fbe +1ae   ff b5 20 f7 ff ff        push     dword ptr [ebp - 0x8e0]
0x10018fc4 +1b4   ff 77 18                 push     dword ptr [edi + 0x18]
0x10018fc7 +1b7   8b ce                    mov      ecx, esi
0x10018fc9 +1b9   8b 80 b0 00 00 00        mov      eax, dword ptr [eax + 0xb0]
0x10018fcf +1bf   ff d0                    call     eax
0x10018fd1 +1c1   8b 8d f8 f6 ff ff        mov      ecx, dword ptr [ebp - 0x908]
0x10018fd7 +1c7   8b 09                    mov      ecx, dword ptr [ecx]
0x10018fd9 +1c9   8b d1                    mov      edx, ecx
0x10018fdb +1cb   89 b5 d0 f6 ff ff        mov      dword ptr [ebp - 0x930], esi
0x10018fe1 +1d1   eb 13                    jmp      0x10018ff6
0x10018fe3 +1d3   c7 85 d0 f6 ff ff 00 00 00 00 mov      dword ptr [ebp - 0x930], 0
0x10018fed +1dd   8b 36                    mov      esi, dword ptr [esi]
0x10018fef +1df   8b d6                    mov      edx, esi
0x10018ff1 +1e1   8a 47 18                 mov      al, byte ptr [edi + 0x18]
0x10018ff4 +1e4   8b ce                    mov      ecx, esi
0x10018ff6 +1e6   88 85 53 f7 ff ff        mov      byte ptr [ebp - 0x8ad], al
0x10018ffc +1ec   c7 85 f4 f6 ff ff 01 00 00 00 mov      dword ptr [ebp - 0x90c], 1   ; PF: PF_Invisible
0x10019006 +1f6   88 45 ac                 mov      byte ptr [ebp - 0x54], al
0x10019009 +1f9   0f b6 c0                 movzx    eax, al
0x1001900c +1fc   89 85 c0 f6 ff ff        mov      dword ptr [ebp - 0x940], eax
0x10019012 +202   33 f6                    xor      esi, esi
0x10019014 +204   89 b5 30 f7 ff ff        mov      dword ptr [ebp - 0x8d0], esi
0x1001901a +20a   8b fe                    mov      edi, esi
0x1001901c +20c   0f ab c7                 bts      edi, eax
0x1001901f +20f   83 f8 20                 cmp      eax, 0x20   ; PF: PF_Semisolid
0x10019022 +212   0f 43 f7                 cmovae   esi, edi
0x10019025 +215   33 fe                    xor      edi, esi
0x10019027 +217   89 bd 30 f7 ff ff        mov      dword ptr [ebp - 0x8d0], edi
0x1001902d +21d   83 f8 40                 cmp      eax, 0x40   ; PF: PF_Modulated
0x10019030 +220   8b c7                    mov      eax, edi
0x10019032 +222   0f 43 f0                 cmovae   esi, eax
0x10019035 +225   89 b5 00 f7 ff ff        mov      dword ptr [ebp - 0x900], esi
0x1001903b +22b   89 85 a4 f6 ff ff        mov      dword ptr [ebp - 0x95c], eax
0x10019041 +231   89 b5 a8 f6 ff ff        mov      dword ptr [ebp - 0x958], esi
0x10019047 +237   8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x1001904d +23d   83 78 58 00              cmp      dword ptr [eax + 0x58], 0
0x10019051 +241   8b bd 4c f7 ff ff        mov      edi, dword ptr [ebp - 0x8b4]
0x10019057 +247   74 27                    je       0x10019080
0x10019059 +249   83 78 50 00              cmp      dword ptr [eax + 0x50], 0
0x1001905d +24d   74 21                    je       0x10019080
0x1001905f +24f   8b 82 88 00 00 00        mov      eax, dword ptr [edx + 0x88]
0x10019065 +255   8b ca                    mov      ecx, edx
0x10019067 +257   85 c0                    test     eax, eax
0x10019069 +259   74 15                    je       0x10019080
0x1001906b +25b   f6 80 7c 02 00 00 02     test     byte ptr [eax + 0x27c], 2   ; PF: PF_Masked
0x10019072 +262   74 0c                    je       0x10019080
0x10019074 +264   c7 85 c4 f6 ff ff 01 00 00 00 mov      dword ptr [ebp - 0x93c], 1   ; PF: PF_Invisible
0x1001907e +26e   eb 0c                    jmp      0x1001908c
0x10019080 +270   c7 85 c4 f6 ff ff 00 00 00 00 mov      dword ptr [ebp - 0x93c], 0
0x1001908a +27a   8b d1                    mov      edx, ecx
0x1001908c +27c   8b 82 7c 04 00 00        mov      eax, dword ptr [edx + 0x47c]
0x10019092 +282   c1 e8 0b                 shr      eax, 0xb
0x10019095 +285   83 c8 fe                 or       eax, 0xfffffffe
0x10019098 +288   89 85 48 f6 ff ff        mov      dword ptr [ebp - 0x9b8], eax
0x1001909e +28e   8b 85 d4 f6 ff ff        mov      eax, dword ptr [ebp - 0x92c]
0x100190a4 +294   8b 80 90 00 00 00        mov      eax, dword ptr [eax + 0x90]
0x100190aa +29a   89 85 50 f6 ff ff        mov      dword ptr [ebp - 0x9b0], eax
0x100190b0 +2a0   8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x100190b6 +2a6   c7 40 30 00 00 00 00     mov      dword ptr [eax + 0x30], 0
0x100190bd +2ad   89 3d 28 fa 05 10        mov      dword ptr [0x1005fa28], edi
0x100190c3 +2b3   8b b5 20 f7 ff ff        mov      esi, dword ptr [ebp - 0x8e0]
0x100190c9 +2b9   8b 46 58                 mov      eax, dword ptr [esi + 0x58]
0x100190cc +2bc   a3 2c fa 05 10           mov      dword ptr [0x1005fa2c], eax
0x100190d1 +2c1   8b 86 98 00 00 00        mov      eax, dword ptr [esi + 0x98]
0x100190d7 +2c7   a3 30 fa 05 10           mov      dword ptr [0x1005fa30], eax
0x100190dc +2cc   8b 46 68                 mov      eax, dword ptr [esi + 0x68]
0x100190df +2cf   a3 34 fa 05 10           mov      dword ptr [0x1005fa34], eax
0x100190e4 +2d4   8d 86 88 00 00 00        lea      eax, [esi + 0x88]
0x100190ea +2da   a3 38 fa 05 10           mov      dword ptr [0x1005fa38], eax
0x100190ef +2df   8b 4f 04                 mov      ecx, dword ptr [edi + 4]
0x100190f2 +2e2   ff 15 64 43 03 10        call     dword ptr [0x10034364]   ; -> Engine.dll!?GetLevelInfo@ULevel@@QAEPAVALevelInfo@@XZ
0x100190f8 +2e8   f3 0f 10 80 6c 03 00 00  movss    xmm0, dword ptr [eax + 0x36c]
0x10019100 +2f0   f3 0f 11 85 8c f6 ff ff  movss    dword ptr [ebp - 0x974], xmm0
0x10019108 +2f8   8b 8d c0 f6 ff ff        mov      ecx, dword ptr [ebp - 0x940]
0x1001910e +2fe   8d 04 49                 lea      eax, [ecx + ecx*2]
0x10019111 +301   f3 0f 11 84 c6 08 01 00 00 movss    dword ptr [esi + eax*8 + 0x108], xmm0
0x1001911a +30a   8d 04 49                 lea      eax, [ecx + ecx*2]
0x1001911d +30d   8b b4 c6 04 01 00 00     mov      esi, dword ptr [esi + eax*8 + 0x104]
0x10019124 +314   85 f6                    test     esi, esi
0x10019126 +316   0f 84 26 01 00 00        je       0x10019252
0x1001912c +31c   ff 15 34 43 03 10        call     dword ptr [0x10034334]   ; -> Engine.dll!?StaticClass@AWarpZoneInfo@@SAPAVUClass@@XZ
0x10019132 +322   8b d0                    mov      edx, eax
0x10019134 +324   8b 4e 24                 mov      ecx, dword ptr [esi + 0x24]
0x10019137 +327   85 c9                    test     ecx, ecx
0x10019139 +329   74 09                    je       0x10019144
0x1001913b +32b   3b ca                    cmp      ecx, edx
0x1001913d +32d   74 14                    je       0x10019153
0x1001913f +32f   8b 49 28                 mov      ecx, dword ptr [ecx + 0x28]
0x10019142 +332   eb f3                    jmp      0x10019137
0x10019144 +334   33 c0                    xor      eax, eax
0x10019146 +336   85 d2                    test     edx, edx
0x10019148 +338   0f 94 c0                 sete     al
0x1001914b +33b   85 c0                    test     eax, eax
0x1001914d +33d   0f 84 ff 00 00 00        je       0x10019252
0x10019153 +343   83 be b0 03 00 00 00     cmp      dword ptr [esi + 0x3b0], 0
0x1001915a +34a   0f 84 f2 00 00 00        je       0x10019252
0x10019160 +350   83 be b4 03 00 00 00     cmp      dword ptr [esi + 0x3b4], 0
0x10019167 +357   0f 84 e5 00 00 00        je       0x10019252
0x1001916d +35d   c6 45 fc 01              mov      byte ptr [ebp - 4], 1   ; PF: PF_Invisible
0x10019171 +361   9b                       wait     
0x10019172 +362   8d 86 80 03 00 00        lea      eax, [esi + 0x380]
0x10019178 +368   50                       push     eax
0x10019179 +369   8d 47 34                 lea      eax, [edi + 0x34]
0x1001917c +36c   50                       push     eax
0x1001917d +36d   8d 8d 14 f5 ff ff        lea      ecx, [ebp - 0xaec]
0x10019183 +373   ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x10019189 +379   8b c8                    mov      ecx, eax
0x1001918b +37b   ff 15 70 42 03 10        call     dword ptr [0x10034270]   ; -> Core.dll!??XFCoords@@QAEAAV0@ABV0@@Z
0x10019191 +381   50                       push     eax
0x10019192 +382   8d 8d 7c f7 ff ff        lea      ecx, [ebp - 0x884]
0x10019198 +388   ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x1001919e +38e   8d 85 e4 f4 ff ff        lea      eax, [ebp - 0xb1c]
0x100191a4 +394   50                       push     eax
0x100191a5 +395   8b 8e b0 03 00 00        mov      ecx, dword ptr [esi + 0x3b0]
0x100191ab +39b   81 c1 80 03 00 00        add      ecx, 0x380
0x100191b1 +3a1   ff 15 24 42 03 10        call     dword ptr [0x10034224]   ; -> Core.dll!?Transpose@FCoords@@QBE?AV1@XZ
0x100191b7 +3a7   50                       push     eax
0x100191b8 +3a8   8d 85 7c f7 ff ff        lea      eax, [ebp - 0x884]
0x100191be +3ae   50                       push     eax
0x100191bf +3af   8d 8d 54 f5 ff ff        lea      ecx, [ebp - 0xaac]
0x100191c5 +3b5   ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x100191cb +3bb   8b c8                    mov      ecx, eax
0x100191cd +3bd   ff 15 70 42 03 10        call     dword ptr [0x10034270]   ; -> Core.dll!??XFCoords@@QAEAAV0@ABV0@@Z
0x100191d3 +3c3   50                       push     eax
0x100191d4 +3c4   8d 8d c4 f5 ff ff        lea      ecx, [ebp - 0xa3c]
0x100191da +3ca   ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x100191e0 +3d0   8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x100191e6 +3d6   8b 11                    mov      edx, dword ptr [ecx]
0x100191e8 +3d8   6a 00                    push     0
0x100191ea +3da   8d 85 c4 f5 ff ff        lea      eax, [ebp - 0xa3c]
0x100191f0 +3e0   50                       push     eax
0x100191f1 +3e1   8d 47 24                 lea      eax, [edi + 0x24]
0x100191f4 +3e4   50                       push     eax
0x100191f5 +3e5   51                       push     ecx
0x100191f6 +3e6   f3 0f 10 47 20           movss    xmm0, dword ptr [edi + 0x20]
0x100191fb +3eb   f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x10019200 +3f0   8b 86 b0 03 00 00        mov      eax, dword ptr [esi + 0x3b0]
0x10019206 +3f6   ff b0 7c 03 00 00        push     dword ptr [eax + 0x37c]
0x1001920c +3fc   6a ff                    push     -1
0x1001920e +3fe   ff 77 04                 push     dword ptr [edi + 4]
0x10019211 +401   ff b7 94 00 00 00        push     dword ptr [edi + 0x94]
0x10019217 +407   57                       push     edi
0x10019218 +408   ff 52 68                 call     dword ptr [edx + 0x68]
0x1001921b +40b   0f 31                    rdtsc    
0x1001921d +40d   83 c0 de                 add      eax, -0x22
0x10019220 +410   03 05 a0 fa 05 10        add      eax, dword ptr [0x1005faa0]
0x10019226 +416   a3 a0 fa 05 10           mov      dword ptr [0x1005faa0], eax
0x1001922b +41b   9b                       wait     
0x1001922c +41c   c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x10019233 +423   9b                       wait     
0x10019234 +424   8b 4d f4                 mov      ecx, dword ptr [ebp - 0xc]
0x10019237 +427   64 89 0d 00 00 00 00     mov      dword ptr fs:[0], ecx
0x1001923e +42e   59                       pop      ecx
0x1001923f +42f   5f                       pop      edi
0x10019240 +430   5e                       pop      esi
0x10019241 +431   5b                       pop      ebx
0x10019242 +432   8b 4d ec                 mov      ecx, dword ptr [ebp - 0x14]
0x10019245 +435   33 cd                    xor      ecx, ebp
0x10019247 +437   e8 9c 88 00 00           call     0x10021ae8   ; -> sub_21ae8
0x1001924c +43c   8b e5                    mov      esp, ebp
0x1001924e +43e   5d                       pop      ebp
0x1001924f +43f   c2 04 00                 ret      4
0x10019252 +442   33 f6                    xor      esi, esi
0x10019254 +444   89 b5 58 f6 ff ff        mov      dword ptr [ebp - 0x9a8], esi
0x1001925a +44a   83 fe 40                 cmp      esi, 0x40   ; PF: PF_Modulated
0x1001925d +44d   7d 1e                    jge      0x1001927d
0x1001925f +44f   68 f0 6b 04 10           push     0x10046bf0
0x10019264 +454   6a 00                    push     0
0x10019266 +456   6a 00                    push     0
0x10019268 +458   8b c6                    mov      eax, esi
0x1001926a +45a   c1 e0 05                 shl      eax, 5
0x1001926d +45d   8d 8d ac f7 ff ff        lea      ecx, [ebp - 0x854]
0x10019273 +463   03 c8                    add      ecx, eax
0x10019275 +465   e8 76 42 00 00           call     0x1001d4f0   ; -> ?AllocIndex@FSpanBuffer@@QAEXHHPAVFMemStack@@@Z
0x1001927a +46a   46                       inc      esi
0x1001927b +46b   eb d7                    jmp      0x10019254
0x1001927d +46d   8b 8d c0 f6 ff ff        mov      ecx, dword ptr [ebp - 0x940]
0x10019283 +473   c1 e1 05                 shl      ecx, 5
0x10019286 +476   8b 87 94 00 00 00        mov      eax, dword ptr [edi + 0x94]
0x1001928c +47c   0f 10 00                 movups   xmm0, xmmword ptr [eax]
0x1001928f +47f   0f 11 84 0d ac f7 ff ff  movups   xmmword ptr [ebp + ecx - 0x854], xmm0
0x10019297 +487   0f 10 40 10              movups   xmm0, xmmword ptr [eax + 0x10]
0x1001929b +48b   0f 11 84 0d bc f7 ff ff  movups   xmmword ptr [ebp + ecx - 0x844], xmm0
0x100192a3 +493   6a 10                    push     0x10   ; PF: PF_Environment
0x100192a5 +495   6a 18                    push     0x18   ; PF: PF_NotSolid|PF_Environment
0x100192a7 +497   8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x100192ad +49d   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x100192b3 +4a3   8b d0                    mov      edx, eax
0x100192b5 +4a5   89 95 1c f7 ff ff        mov      dword ptr [ebp - 0x8e4], edx
0x100192bb +4ab   c7 42 14 00 00 00 00     mov      dword ptr [edx + 0x14], 0
0x100192c2 +4b2   33 f6                    xor      esi, esi
0x100192c4 +4b4   89 b5 34 f7 ff ff        mov      dword ptr [ebp - 0x8cc], esi
0x100192ca +4ba   8b 85 20 f7 ff ff        mov      eax, dword ptr [ebp - 0x8e0]
0x100192d0 +4c0   8b 80 f0 00 00 00        mov      eax, dword ptr [eax + 0xf0]
0x100192d6 +4c6   33 c9                    xor      ecx, ecx
0x100192d8 +4c8   89 85 18 f7 ff ff        mov      dword ptr [ebp - 0x8e8], eax
0x100192de +4ce   8b fe                    mov      edi, esi
0x100192e0 +4d0   c1 e7 06                 shl      edi, 6
0x100192e3 +4d3   89 bd 68 f6 ff ff        mov      dword ptr [ebp - 0x998], edi
0x100192e9 +4d9   03 3d 2c fa 05 10        add      edi, dword ptr [0x1005fa2c]
0x100192ef +4df   89 bd 44 f7 ff ff        mov      dword ptr [ebp - 0x8bc], edi
0x100192f5 +4e5   89 bd b4 f6 ff ff        mov      dword ptr [ebp - 0x94c], edi
0x100192fb +4eb   85 c9                    test     ecx, ecx
0x100192fd +4ed   0f 85 64 03 00 00        jne      0x10019667
0x10019303 +4f3   38 8d 53 f7 ff ff        cmp      byte ptr [ebp - 0x8ad], cl
0x10019309 +4f9   74 21                    je       0x1001932c
0x1001930b +4fb   8b 8d 30 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8d0]
0x10019311 +501   23 4f 10                 and      ecx, dword ptr [edi + 0x10]
0x10019314 +504   8b 47 14                 mov      eax, dword ptr [edi + 0x14]
0x10019317 +507   23 85 00 f7 ff ff        and      eax, dword ptr [ebp - 0x900]
0x1001931d +50d   0b c8                    or       ecx, eax
0x1001931f +50f   75 0b                    jne      0x1001932c
0x10019321 +511   ff 05 2c fb 05 10        inc      dword ptr [0x1005fb2c]
0x10019327 +517   e9 b9 00 00 00           jmp      0x100193e5
0x1001932c +51c   83 7f 30 ff              cmp      dword ptr [edi + 0x30], -1
0x10019330 +520   0f 84 ff 01 00 00        je       0x10019535
0x10019336 +526   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x1001933c +52c   8b 40 04                 mov      eax, dword ptr [eax + 4]
0x1001933f +52f   8b 88 fc 00 00 00        mov      ecx, dword ptr [eax + 0xfc]
0x10019345 +535   85 c9                    test     ecx, ecx
0x10019347 +537   74 12                    je       0x1001935b
0x10019349 +539   8b 01                    mov      eax, dword ptr [ecx]
0x1001934b +53b   ff 77 1c                 push     dword ptr [edi + 0x1c]
0x1001934e +53e   8b 40 0c                 mov      eax, dword ptr [eax + 0xc]
0x10019351 +541   ff d0                    call     eax
0x10019353 +543   85 c0                    test     eax, eax
0x10019355 +545   0f 85 da 01 00 00        jne      0x10019535
0x1001935b +54b   8a 4f 37                 mov      cl, byte ptr [edi + 0x37]
0x1001935e +54e   f6 c1 10                 test     cl, 0x10   ; PF: PF_Environment
0x10019361 +551   75 10                    jne      0x10019373
0x10019363 +553   8b c6                    mov      eax, esi
0x10019365 +555   33 05 24 fa 05 10        xor      eax, dword ptr [0x1005fa24]
0x1001936b +55b   a8 0f                    test     al, 0xf   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid
0x1001936d +55d   0f 85 c2 01 00 00        jne      0x10019535
0x10019373 +563   80 e1 ef                 and      cl, 0xef   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid|PF_Semisolid|PF_Modulated|PF_FakeBackdrop
0x10019376 +566   88 4f 37                 mov      byte ptr [edi + 0x37], cl
0x10019379 +569   8b 47 30                 mov      eax, dword ptr [edi + 0x30]
0x1001937c +56c   8d 0c c5 00 00 00 00     lea      ecx, [eax*8]
0x10019383 +573   2b c8                    sub      ecx, eax
0x10019385 +575   8b 85 20 f7 ff ff        mov      eax, dword ptr [ebp - 0x8e0]
0x1001938b +57b   8b 80 c0 00 00 00        mov      eax, dword ptr [eax + 0xc0]
0x10019391 +581   8d 0c 88                 lea      ecx, [eax + ecx*4]
0x10019394 +584   8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x1001939a +58a   8b 10                    mov      edx, dword ptr [eax]
0x1001939c +58c   8d 85 54 f7 ff ff        lea      eax, [ebp - 0x8ac]
0x100193a2 +592   50                       push     eax
0x100193a3 +593   8d 85 ac f7 ff ff        lea      eax, [ebp - 0x854]
0x100193a9 +599   c7 85 28 f7 ff ff 00 00 00 00 mov      dword ptr [ebp - 0x8d8], 0
0x100193b3 +5a3   80 bd 53 f7 ff ff 00     cmp      byte ptr [ebp - 0x8ad], 0
0x100193ba +5aa   0f 45 85 28 f7 ff ff     cmovne   eax, dword ptr [ebp - 0x8d8]
0x100193c1 +5b1   50                       push     eax
0x100193c2 +5b2   51                       push     ecx
0x100193c3 +5b3   ff b5 4c f7 ff ff        push     dword ptr [ebp - 0x8b4]
0x100193c9 +5b9   8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x100193cf +5bf   8b 82 80 00 00 00        mov      eax, dword ptr [edx + 0x80]
0x100193d5 +5c5   ff d0                    call     eax
0x100193d7 +5c7   85 c0                    test     eax, eax
0x100193d9 +5c9   75 6e                    jne      0x10019449
0x100193db +5cb   80 4f 37 10              or       byte ptr [edi + 0x37], 0x10   ; PF: PF_Environment
0x100193df +5cf   8b 95 1c f7 ff ff        mov      edx, dword ptr [ebp - 0x8e4]
0x100193e5 +5d5   8b 52 14                 mov      edx, dword ptr [edx + 0x14]
0x100193e8 +5d8   89 95 1c f7 ff ff        mov      dword ptr [ebp - 0x8e4], edx
0x100193ee +5de   85 d2                    test     edx, edx
0x100193f0 +5e0   0f 85 b2 15 00 00        jne      0x1001a9a8
0x100193f6 +5e6   8b 85 20 f7 ff ff        mov      eax, dword ptr [ebp - 0x8e0]
0x100193fc +5ec   8b 80 00 01 00 00        mov      eax, dword ptr [eax + 0x100]
0x10019402 +5f2   01 05 24 fb 05 10        add      dword ptr [0x1005fb24], eax
0x10019408 +5f8   8b 85 c0 f6 ff ff        mov      eax, dword ptr [ebp - 0x940]
0x1001940e +5fe   a3 20 fb 05 10           mov      dword ptr [0x1005fb20], eax
0x10019413 +603   33 c9                    xor      ecx, ecx
0x10019415 +605   89 8d 60 f6 ff ff        mov      dword ptr [ebp - 0x9a0], ecx
0x1001941b +60b   8b 15 28 fb 05 10        mov      edx, dword ptr [0x1005fb28]
0x10019421 +611   83 f9 40                 cmp      ecx, 0x40   ; PF: PF_Modulated
0x10019424 +614   0f 8d 61 15 00 00        jge      0x1001a98b
0x1001942a +61a   8b c1                    mov      eax, ecx
0x1001942c +61c   c1 e0 05                 shl      eax, 5
0x1001942f +61f   83 bc 05 b0 f7 ff ff 00  cmp      dword ptr [ebp + eax - 0x850], 0
0x10019437 +627   74 07                    je       0x10019440
0x10019439 +629   42                       inc      edx
0x1001943a +62a   89 15 28 fb 05 10        mov      dword ptr [0x1005fb28], edx
0x10019440 +630   41                       inc      ecx
0x10019441 +631   89 8d 60 f6 ff ff        mov      dword ptr [ebp - 0x9a0], ecx
0x10019447 +637   eb d8                    jmp      0x10019421
0x10019449 +639   80 bd 53 f7 ff ff 00     cmp      byte ptr [ebp - 0x8ad], 0
0x10019450 +640   0f 84 df 00 00 00        je       0x10019535
0x10019456 +646   33 ff                    xor      edi, edi
0x10019458 +648   89 bd 54 f6 ff ff        mov      dword ptr [ebp - 0x9ac], edi
0x1001945e +64e   8b 85 f4 f6 ff ff        mov      eax, dword ptr [ebp - 0x90c]
0x10019464 +654   3b f8                    cmp      edi, eax
0x10019466 +656   0f 8d ac 00 00 00        jge      0x10019518
0x1001946c +65c   0f b6 44 3d ac           movzx    eax, byte ptr [ebp + edi - 0x54]
0x10019471 +661   89 85 28 f7 ff ff        mov      dword ptr [ebp - 0x8d8], eax
0x10019477 +667   33 d2                    xor      edx, edx
0x10019479 +669   33 c9                    xor      ecx, ecx
0x1001947b +66b   0f ab c2                 bts      edx, eax
0x1001947e +66e   83 f8 20                 cmp      eax, 0x20   ; PF: PF_Semisolid
0x10019481 +671   0f 43 ca                 cmovae   ecx, edx
0x10019484 +674   33 d1                    xor      edx, ecx
0x10019486 +676   83 f8 40                 cmp      eax, 0x40   ; PF: PF_Modulated
0x10019489 +679   0f 43 ca                 cmovae   ecx, edx
0x1001948c +67c   8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x10019492 +682   23 50 10                 and      edx, dword ptr [eax + 0x10]
0x10019495 +685   23 48 14                 and      ecx, dword ptr [eax + 0x14]
0x10019498 +688   0b d1                    or       edx, ecx
0x1001949a +68a   74 6e                    je       0x1001950a
0x1001949c +68c   f3 0f 10 8d 60 f7 ff ff  movss    xmm1, dword ptr [ebp - 0x8a0]
0x100194a4 +694   f3 0f 11 8d ac f6 ff ff  movss    dword ptr [ebp - 0x954], xmm1
0x100194ac +69c   f3 0f 2d f1              cvtss2si esi, xmm1
0x100194b0 +6a0   f3 0f 10 8d 5c f7 ff ff  movss    xmm1, dword ptr [ebp - 0x8a4]
0x100194b8 +6a8   f3 0f 11 8d 14 f7 ff ff  movss    dword ptr [ebp - 0x8ec], xmm1
0x100194c0 +6b0   f3 0f 2d d1              cvtss2si edx, xmm1
0x100194c4 +6b4   f3 0f 10 8d 58 f7 ff ff  movss    xmm1, dword ptr [ebp - 0x8a8]
0x100194cc +6bc   f3 0f 11 8d dc f6 ff ff  movss    dword ptr [ebp - 0x924], xmm1
0x100194d4 +6c4   f3 0f 2d c9              cvtss2si ecx, xmm1
0x100194d8 +6c8   f3 0f 10 8d 54 f7 ff ff  movss    xmm1, dword ptr [ebp - 0x8ac]
0x100194e0 +6d0   f3 0f 11 8d e0 f6 ff ff  movss    dword ptr [ebp - 0x920], xmm1
0x100194e8 +6d8   f3 0f 2d c1              cvtss2si eax, xmm1
0x100194ec +6dc   56                       push     esi
0x100194ed +6dd   52                       push     edx
0x100194ee +6de   51                       push     ecx
0x100194ef +6df   50                       push     eax
0x100194f0 +6e0   8b 85 28 f7 ff ff        mov      eax, dword ptr [ebp - 0x8d8]
0x100194f6 +6e6   c1 e0 05                 shl      eax, 5
0x100194f9 +6e9   8d 8d ac f7 ff ff        lea      ecx, [ebp - 0x854]
0x100194ff +6ef   03 c8                    add      ecx, eax
0x10019501 +6f1   e8 0a 47 00 00           call     0x1001dc10   ; -> ?BoxIsVisible@FSpanBuffer@@QAEHHHHH@Z
0x10019506 +6f6   85 c0                    test     eax, eax
0x10019508 +6f8   75 06                    jne      0x10019510
0x1001950a +6fa   47                       inc      edi
0x1001950b +6fb   e9 48 ff ff ff           jmp      0x10019458
0x10019510 +700   8b 85 f4 f6 ff ff        mov      eax, dword ptr [ebp - 0x90c]
0x10019516 +706   3b f8                    cmp      edi, eax
0x10019518 +708   75 15                    jne      0x1001952f
0x1001951a +70a   ff 05 dc fa 05 10        inc      dword ptr [0x1005fadc]
0x10019520 +710   8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x10019526 +716   80 48 37 10              or       byte ptr [eax + 0x37], 0x10   ; PF: PF_Environment
0x1001952a +71a   e9 b0 fe ff ff           jmp      0x100193df
0x1001952f +71f   8b b5 34 f7 ff ff        mov      esi, dword ptr [ebp - 0x8cc]
0x10019535 +725   0f 31                    rdtsc    
0x10019537 +727   29 05 94 fa 05 10        sub      dword ptr [0x1005fa94], eax
0x1001953d +72d   a1 04 fa 05 10           mov      eax, dword ptr [0x1005fa04]   ; data ?DynamicsCache@URender@@2PAUFDynamicsCache@1@A
0x10019542 +732   8b 34 f0                 mov      esi, dword ptr [eax + esi*8]
0x10019545 +735   8b bd 34 f7 ff ff        mov      edi, dword ptr [ebp - 0x8cc]
0x1001954b +73b   0f 1f 44 00 00           nop      dword ptr [eax + eax]
0x10019550 +740   85 f6                    test     esi, esi
0x10019552 +742   74 1e                    je       0x10019572
0x10019554 +744   8b 06                    mov      eax, dword ptr [esi]
0x10019556 +746   ff b5 18 f7 ff ff        push     dword ptr [ebp - 0x8e8]
0x1001955c +74c   57                       push     edi
0x1001955d +74d   ff b5 4c f7 ff ff        push     dword ptr [ebp - 0x8b4]
0x10019563 +753   ff b5 d4 f6 ff ff        push     dword ptr [ebp - 0x92c]
0x10019569 +759   8b ce                    mov      ecx, esi
0x1001956b +75b   ff 10                    call     dword ptr [eax]
0x1001956d +75d   8b 76 04                 mov      esi, dword ptr [esi + 4]
0x10019570 +760   eb de                    jmp      0x10019550
0x10019572 +762   0f 31                    rdtsc    
0x10019574 +764   8b 0d 94 fa 05 10        mov      ecx, dword ptr [0x1005fa94]
0x1001957a +76a   83 c1 de                 add      ecx, -0x22
0x1001957d +76d   03 c1                    add      eax, ecx
0x1001957f +76f   a3 94 fa 05 10           mov      dword ptr [0x1005fa94], eax
0x10019584 +774   8d 85 98 f6 ff ff        lea      eax, [ebp - 0x968]
0x1001958a +77a   50                       push     eax
0x1001958b +77b   8b b5 44 f7 ff ff        mov      esi, dword ptr [ebp - 0x8bc]
0x10019591 +781   8b ce                    mov      ecx, esi
0x10019593 +783   ff 15 e4 40 03 10        call     dword ptr [0x100340e4]   ; -> Core.dll!?PlaneDot@FPlane@@QBEMABVFVector@@@Z
0x10019599 +789   d9 9d 28 f7 ff ff        fstp     dword ptr [ebp - 0x8d8]
0x1001959f +78f   f3 0f 10 85 28 f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8d8]
0x100195a7 +797   33 c9                    xor      ecx, ecx
0x100195a9 +799   0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x100195b0 +7a0   0f 97 c1                 seta     cl
0x100195b3 +7a3   89 8d 28 f7 ff ff        mov      dword ptr [ebp - 0x8d8], ecx
0x100195b9 +7a9   b8 09 00 00 00           mov      eax, 9   ; PF: PF_Invisible|PF_NotSolid
0x100195be +7ae   2b c1                    sub      eax, ecx
0x100195c0 +7b0   8b 04 86                 mov      eax, dword ptr [esi + eax*4]
0x100195c3 +7b3   8b 95 1c f7 ff ff        mov      edx, dword ptr [ebp - 0x8e4]
0x100195c9 +7b9   89 42 04                 mov      dword ptr [edx + 4], eax
0x100195cc +7bc   6a 00                    push     0
0x100195ce +7be   ff b5 18 f7 ff ff        push     dword ptr [ebp - 0x8e8]
0x100195d4 +7c4   b8 01 00 00 00           mov      eax, 1   ; PF: PF_Invisible
0x100195d9 +7c9   2b c1                    sub      eax, ecx
0x100195db +7cb   50                       push     eax
0x100195dc +7cc   8b ce                    mov      ecx, esi
0x100195de +7ce   e8 3d a5 ff ff           call     0x10013b20   ; -> sub_13b20
0x100195e3 +7d3   8b 95 1c f7 ff ff        mov      edx, dword ptr [ebp - 0x8e4]
0x100195e9 +7d9   89 42 08                 mov      dword ptr [edx + 8], eax
0x100195ec +7dc   8b bd 28 f7 ff ff        mov      edi, dword ptr [ebp - 0x8d8]
0x100195f2 +7e2   83 7c be 20 ff           cmp      dword ptr [esi + edi*4 + 0x20], -1
0x100195f7 +7e7   74 60                    je       0x10019659
0x100195f9 +7e9   8b 85 34 f7 ff ff        mov      eax, dword ptr [ebp - 0x8cc]
0x100195ff +7ef   89 02                    mov      dword ptr [edx], eax
0x10019601 +7f1   8b 85 18 f7 ff ff        mov      eax, dword ptr [ebp - 0x8e8]
0x10019607 +7f7   89 42 0c                 mov      dword ptr [edx + 0xc], eax
0x1001960a +7fa   c7 42 10 01 00 00 00     mov      dword ptr [edx + 0x10], 1   ; PF: PF_Invisible
0x10019611 +801   8b f2                    mov      esi, edx
0x10019613 +803   6a 10                    push     0x10   ; PF: PF_Environment
0x10019615 +805   6a 18                    push     0x18   ; PF: PF_NotSolid|PF_Environment
0x10019617 +807   8b 0d b8 41 03 10        mov      ecx, dword ptr [0x100341b8]
0x1001961d +80d   ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x10019623 +813   8b d0                    mov      edx, eax
0x10019625 +815   89 95 1c f7 ff ff        mov      dword ptr [ebp - 0x8e4], edx
0x1001962b +81b   89 72 14                 mov      dword ptr [edx + 0x14], esi
0x1001962e +81e   8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x10019634 +824   8b 74 b8 20              mov      esi, dword ptr [eax + edi*4 + 0x20]
0x10019638 +828   89 b5 34 f7 ff ff        mov      dword ptr [ebp - 0x8cc], esi
0x1001963e +82e   6a 00                    push     0
0x10019640 +830   ff b5 18 f7 ff ff        push     dword ptr [ebp - 0x8e8]
0x10019646 +836   57                       push     edi
0x10019647 +837   8b c8                    mov      ecx, eax
0x10019649 +839   e8 d2 a4 ff ff           call     0x10013b20   ; -> sub_13b20
0x1001964e +83e   8b 95 1c f7 ff ff        mov      edx, dword ptr [ebp - 0x8e4]
0x10019654 +844   e9 7d fc ff ff           jmp      0x100192d6
0x10019659 +849   8b b5 34 f7 ff ff        mov      esi, dword ptr [ebp - 0x8cc]
0x1001965f +84f   8b bd 44 f7 ff ff        mov      edi, dword ptr [ebp - 0x8bc]
0x10019665 +855   eb 09                    jmp      0x10019670
0x10019667 +857   83 f9 01                 cmp      ecx, 1   ; PF: PF_Invisible
0x1001966a +85a   0f 85 75 fd ff ff        jne      0x100193e5
0x10019670 +860   80 bd 53 f7 ff ff 00     cmp      byte ptr [ebp - 0x8ad], 0
0x10019677 +867   74 21                    je       0x1001969a
0x10019679 +869   8b 8d 30 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8d0]
0x1001967f +86f   23 4f 10                 and      ecx, dword ptr [edi + 0x10]
0x10019682 +872   8b 47 14                 mov      eax, dword ptr [edi + 0x14]
0x10019685 +875   23 85 00 f7 ff ff        and      eax, dword ptr [ebp - 0x900]
0x1001968b +87b   0b c8                    or       ecx, eax
0x1001968d +87d   75 0b                    jne      0x1001969a
0x1001968f +87f   ff 05 2c fb 05 10        inc      dword ptr [0x1005fb2c]
0x10019695 +885   e9 4b fd ff ff           jmp      0x100193e5
0x1001969a +88a   89 b5 28 f7 ff ff        mov      dword ptr [ebp - 0x8d8], esi
0x100196a0 +890   8d 85 98 f6 ff ff        lea      eax, [ebp - 0x968]
0x100196a6 +896   50                       push     eax
0x100196a7 +897   8b cf                    mov      ecx, edi
0x100196a9 +899   ff 15 e4 40 03 10        call     dword ptr [0x100340e4]   ; -> Core.dll!?PlaneDot@FPlane@@QBEMABVFVector@@@Z
0x100196af +89f   d9 9d 3c f7 ff ff        fstp     dword ptr [ebp - 0x8c4]
0x100196b5 +8a5   33 c9                    xor      ecx, ecx
0x100196b7 +8a7   f3 0f 10 85 3c f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8c4]
0x100196bf +8af   0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x100196c6 +8b6   0f 97 c1                 seta     cl
0x100196c9 +8b9   89 8d 24 f7 ff ff        mov      dword ptr [ebp - 0x8dc], ecx
0x100196cf +8bf   89 8d b0 f6 ff ff        mov      dword ptr [ebp - 0x950], ecx
0x100196d5 +8c5   0f b6 44 39 34           movzx    eax, byte ptr [ecx + edi + 0x34]
0x100196da +8ca   33 ff                    xor      edi, edi
0x100196dc +8cc   80 bd 53 f7 ff ff 00     cmp      byte ptr [ebp - 0x8ad], 0
0x100196e3 +8d3   0f 45 f8                 cmovne   edi, eax
0x100196e6 +8d6   8b 95 44 f7 ff ff        mov      edx, dword ptr [ebp - 0x8bc]
0x100196ec +8dc   83 bd c4 f6 ff ff 00     cmp      dword ptr [ebp - 0x93c], 0
0x100196f3 +8e3   74 2d                    je       0x10019722
0x100196f5 +8e5   8b 44 8a 38              mov      eax, dword ptr [edx + ecx*4 + 0x38]
0x100196f9 +8e9   83 f8 ff                 cmp      eax, -1
0x100196fc +8ec   74 24                    je       0x10019722
0x100196fe +8ee   50                       push     eax
0x100196ff +8ef   ff b5 20 f7 ff ff        push     dword ptr [ebp - 0x8e0]
0x10019705 +8f5   ff b5 4c f7 ff ff        push     dword ptr [ebp - 0x8b4]
0x1001970b +8fb   8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x10019711 +901   e8 da f4 ff ff           call     0x10018bf0   ; -> ?LeafVolumetricLighting@URender@@QAEXPAUFSceneNode@@PAVUModel@@H@Z
0x10019716 +906   8b 8d 24 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8dc]
0x1001971c +90c   8b 95 44 f7 ff ff        mov      edx, dword ptr [ebp - 0x8bc]
0x10019722 +912   c1 e7 05                 shl      edi, 5
0x10019725 +915   83 bc 3d b4 f7 ff ff 00  cmp      dword ptr [ebp + edi - 0x84c], 0
0x1001972d +91d   74 6c                    je       0x1001979b
0x1001972f +91f   6a 00                    push     0
0x10019731 +921   ff b5 18 f7 ff ff        push     dword ptr [ebp - 0x8e8]
0x10019737 +927   51                       push     ecx
0x10019738 +928   8b ca                    mov      ecx, edx
0x1001973a +92a   e8 e1 a3 ff ff           call     0x10013b20   ; -> sub_13b20
0x1001973f +92f   85 c0                    test     eax, eax
0x10019741 +931   75 0c                    jne      0x1001974f
0x10019743 +933   8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x10019749 +939   83 78 34 00              cmp      dword ptr [eax + 0x34], 0
0x1001974d +93d   74 4c                    je       0x1001979b
0x1001974f +93f   8d 0c 36                 lea      ecx, [esi + esi]
0x10019752 +942   2b 8d 24 f7 ff ff        sub      ecx, dword ptr [ebp - 0x8dc]
0x10019758 +948   a1 04 fa 05 10           mov      eax, dword ptr [0x1005fa04]   ; data ?DynamicsCache@URender@@2PAUFDynamicsCache@1@A
0x1001975d +94d   8b 74 88 04              mov      esi, dword ptr [eax + ecx*4 + 4]
0x10019761 +951   85 f6                    test     esi, esi
0x10019763 +953   74 30                    je       0x10019795
0x10019765 +955   8b 16                    mov      edx, dword ptr [esi]
0x10019767 +957   8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x1001976d +95d   ff 70 30                 push     dword ptr [eax + 0x30]
0x10019770 +960   ff b5 34 f7 ff ff        push     dword ptr [ebp - 0x8cc]
0x10019776 +966   8d 85 ac f7 ff ff        lea      eax, [ebp - 0x854]
0x1001977c +96c   03 c7                    add      eax, edi
0x1001977e +96e   50                       push     eax
0x1001977f +96f   ff b5 4c f7 ff ff        push     dword ptr [ebp - 0x8b4]
0x10019785 +975   ff b5 d4 f6 ff ff        push     dword ptr [ebp - 0x92c]
0x1001978b +97b   8b ce                    mov      ecx, esi
0x1001978d +97d   ff 52 04                 call     dword ptr [edx + 4]
0x10019790 +980   8b 76 04                 mov      esi, dword ptr [esi + 4]
0x10019793 +983   eb cc                    jmp      0x10019761
0x10019795 +985   8b b5 34 f7 ff ff        mov      esi, dword ptr [ebp - 0x8cc]
0x1001979b +98b   83 bd 24 f7 ff ff 00     cmp      dword ptr [ebp - 0x8dc], 0
0x100197a2 +992   c7 85 40 f7 ff ff 00 00 80 3f mov      dword ptr [ebp - 0x8c0], 0x3f800000
0x100197ac +99c   75 0a                    jne      0x100197b8
0x100197ae +99e   c7 85 40 f7 ff ff 00 00 80 bf mov      dword ptr [ebp - 0x8c0], 0xbf800000
0x100197b8 +9a8   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x100197be +9ae   05 fc 00 00 00           add      eax, 0xfc
0x100197c3 +9b3   50                       push     eax
0x100197c4 +9b4   8b bd 44 f7 ff ff        mov      edi, dword ptr [ebp - 0x8bc]
0x100197ca +9ba   8b cf                    mov      ecx, edi
0x100197cc +9bc   ff 15 d8 40 03 10        call     dword ptr [0x100340d8]   ; -> Core.dll!??UFPlane@@QBEMABVFVector@@@Z
0x100197d2 +9c2   d8 8d 40 f7 ff ff        fmul     dword ptr [ebp - 0x8c0]
0x100197d8 +9c8   d9 9d 14 f7 ff ff        fstp     dword ptr [ebp - 0x8ec]
0x100197de +9ce   f3 0f 10 85 14 f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8ec]
0x100197e6 +9d6   0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x100197ed +9dd   0f 86 97 00 00 00        jbe      0x1001988a
0x100197f3 +9e3   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x100197f9 +9e9   05 08 01 00 00           add      eax, 0x108
0x100197fe +9ee   50                       push     eax
0x100197ff +9ef   8b cf                    mov      ecx, edi
0x10019801 +9f1   ff 15 d8 40 03 10        call     dword ptr [0x100340d8]   ; -> Core.dll!??UFPlane@@QBEMABVFVector@@@Z
0x10019807 +9f7   d8 8d 40 f7 ff ff        fmul     dword ptr [ebp - 0x8c0]
0x1001980d +9fd   d9 9d 14 f7 ff ff        fstp     dword ptr [ebp - 0x8ec]
0x10019813 +a03   f3 0f 10 85 14 f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8ec]
0x1001981b +a0b   0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x10019822 +a12   76 66                    jbe      0x1001988a
0x10019824 +a14   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x1001982a +a1a   05 14 01 00 00           add      eax, 0x114
0x1001982f +a1f   50                       push     eax
0x10019830 +a20   8b cf                    mov      ecx, edi
0x10019832 +a22   ff 15 d8 40 03 10        call     dword ptr [0x100340d8]   ; -> Core.dll!??UFPlane@@QBEMABVFVector@@@Z
0x10019838 +a28   d8 8d 40 f7 ff ff        fmul     dword ptr [ebp - 0x8c0]
0x1001983e +a2e   d9 9d 14 f7 ff ff        fstp     dword ptr [ebp - 0x8ec]
0x10019844 +a34   f3 0f 10 85 14 f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8ec]
0x1001984c +a3c   0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x10019853 +a43   76 35                    jbe      0x1001988a
0x10019855 +a45   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x1001985b +a4b   05 20 01 00 00           add      eax, 0x120
0x10019860 +a50   50                       push     eax
0x10019861 +a51   8b cf                    mov      ecx, edi
0x10019863 +a53   ff 15 d8 40 03 10        call     dword ptr [0x100340d8]   ; -> Core.dll!??UFPlane@@QBEMABVFVector@@@Z
0x10019869 +a59   d8 8d 40 f7 ff ff        fmul     dword ptr [ebp - 0x8c0]
0x1001986f +a5f   d9 9d 14 f7 ff ff        fstp     dword ptr [ebp - 0x8ec]
0x10019875 +a65   f3 0f 10 85 14 f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8ec]
0x1001987d +a6d   0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x10019884 +a74   0f 87 55 fb ff ff        ja       0x100193df
0x1001988a +a7a   f3 0f 10 85 3c f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8c4]
0x10019892 +a82   8b 8d 24 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8dc]
0x10019898 +a88   0f 1f 84 00 00 00 00 00  nop      dword ptr [eax + eax]
0x100198a0 +a90   8b 47 1c                 mov      eax, dword ptr [edi + 0x1c]
0x100198a3 +a93   c1 e0 06                 shl      eax, 6
0x100198a6 +a96   03 05 30 fa 05 10        add      eax, dword ptr [0x1005fa30]
0x100198ac +a9c   89 85 e0 f6 ff ff        mov      dword ptr [ebp - 0x920], eax
0x100198b2 +aa2   8b 40 04                 mov      eax, dword ptr [eax + 4]
0x100198b5 +aa5   0b 85 50 f6 ff ff        or       eax, dword ptr [ebp - 0x9b0]
0x100198bb +aab   89 85 40 f7 ff ff        mov      dword ptr [ebp - 0x8c0], eax
0x100198c1 +ab1   89 85 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], eax
0x100198c7 +ab7   85 c9                    test     ecx, ecx
0x100198c9 +ab9   75 18                    jne      0x100198e3
0x100198cb +abb   f3 0f 10 0d d0 55 03 10  movss    xmm1, dword ptr [0x100355d0]   ; [0x100355d0] f32=-1.0
0x100198d3 +ac3   0f 2f c8                 comiss   xmm1, xmm0
0x100198d6 +ac6   76 0b                    jbe      0x100198e3
0x100198d8 +ac8   a9 00 01 00 04           test     eax, 0x4000100   ; PF: PF_TwoSided|PF_Portal
0x100198dd +acd   0f 84 08 0f 00 00        je       0x1001a7eb
0x100198e3 +ad3   a9 00 00 00 04           test     eax, 0x4000000   ; PF: PF_Portal
0x100198e8 +ad8   74 0d                    je       0x100198f7
0x100198ea +ada   80 bd 53 f7 ff ff 00     cmp      byte ptr [ebp - 0x8ad], 0
0x100198f1 +ae1   0f 84 f4 0e 00 00        je       0x1001a7eb
0x100198f7 +ae7   8b 85 d0 f6 ff ff        mov      eax, dword ptr [ebp - 0x930]
0x100198fd +aed   85 c0                    test     eax, eax
0x100198ff +aef   74 2b                    je       0x1001992c
0x10019901 +af1   8b 10                    mov      edx, dword ptr [eax]
0x10019903 +af3   ff b5 e0 f6 ff ff        push     dword ptr [ebp - 0x920]
0x10019909 +af9   0f b6 44 39 34           movzx    eax, byte ptr [ecx + edi + 0x34]
0x1001990e +afe   50                       push     eax
0x1001990f +aff   57                       push     edi
0x10019910 +b00   8b 8d d0 f6 ff ff        mov      ecx, dword ptr [ebp - 0x930]
0x10019916 +b06   8b 82 b8 00 00 00        mov      eax, dword ptr [edx + 0xb8]
0x1001991c +b0c   ff d0                    call     eax
0x1001991e +b0e   84 c0                    test     al, al
0x10019920 +b10   0f 84 c5 0e 00 00        je       0x1001a7eb
0x10019926 +b16   8b 8d 24 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8dc]
0x1001992c +b1c   33 d2                    xor      edx, edx
0x1001992e +b1e   0f b6 44 39 34           movzx    eax, byte ptr [ecx + edi + 0x34]
0x10019933 +b23   38 95 53 f7 ff ff        cmp      byte ptr [ebp - 0x8ad], dl
0x10019939 +b29   0f 45 d0                 cmovne   edx, eax
0x1001993c +b2c   89 95 ac f6 ff ff        mov      dword ptr [ebp - 0x954], edx
0x10019942 +b32   88 95 cf f6 ff ff        mov      byte ptr [ebp - 0x931], dl
0x10019948 +b38   0f b6 c2                 movzx    eax, dl
0x1001994b +b3b   89 85 dc f6 ff ff        mov      dword ptr [ebp - 0x924], eax
0x10019951 +b41   c1 e0 05                 shl      eax, 5
0x10019954 +b44   8d 84 05 ac f7 ff ff     lea      eax, [ebp + eax - 0x854]
0x1001995b +b4b   89 85 e4 f6 ff ff        mov      dword ptr [ebp - 0x91c], eax
0x10019961 +b51   83 78 08 00              cmp      dword ptr [eax + 8], 0
0x10019965 +b55   0f 8e 80 0e 00 00        jle      0x1001a7eb
0x1001996b +b5b   0f 31                    rdtsc    
0x1001996d +b5d   29 05 a4 fa 05 10        sub      dword ptr [0x1005faa4], eax
0x10019973 +b63   ff 05 b0 fa 05 10        inc      dword ptr [0x1005fab0]
0x10019979 +b69   8d 85 fc f6 ff ff        lea      eax, [ebp - 0x904]
0x1001997f +b6f   50                       push     eax
0x10019980 +b70   56                       push     esi
0x10019981 +b71   8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x10019987 +b77   e8 64 a3 ff ff           call     0x10013cf0   ; -> ?ClipBspSurf@URender@@QAEHHAAPAPAUFTransform@@@Z
0x1001998c +b7c   8b f0                    mov      esi, eax
0x1001998e +b7e   89 b5 3c f7 ff ff        mov      dword ptr [ebp - 0x8c4], esi
0x10019994 +b84   0f 31                    rdtsc    
0x10019996 +b86   8b 0d a4 fa 05 10        mov      ecx, dword ptr [0x1005faa4]
0x1001999c +b8c   83 c1 de                 add      ecx, -0x22
0x1001999f +b8f   03 c8                    add      ecx, eax
0x100199a1 +b91   89 0d a4 fa 05 10        mov      dword ptr [0x1005faa4], ecx
0x100199a7 +b97   85 f6                    test     esi, esi
0x100199a9 +b99   0f 84 3c 0e 00 00        je       0x1001a7eb
0x100199af +b9f   8b bd 24 f7 ff ff        mov      edi, dword ptr [ebp - 0x8dc]
0x100199b5 +ba5   85 ff                    test     edi, edi
0x100199b7 +ba7   75 11                    jne      0x100199ca
0x100199b9 +ba9   f7 85 40 f7 ff ff 00 01 00 04 test     dword ptr [ebp - 0x8c0], 0x4000100   ; PF: PF_TwoSided|PF_Portal
0x100199c3 +bb3   74 05                    je       0x100199ca
0x100199c5 +bb5   8d 4f 01                 lea      ecx, [edi + 1]
0x100199c8 +bb8   eb 02                    jmp      0x100199cc
0x100199ca +bba   33 c9                    xor      ecx, ecx
0x100199cc +bbc   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x100199d2 +bc2   f3 0f 10 40 20           movss    xmm0, dword ptr [eax + 0x20]
0x100199d7 +bc7   0f 2e 05 d0 55 03 10     ucomiss  xmm0, dword ptr [0x100355d0]   ; [0x100355d0] f32=-1.0
0x100199de +bce   9f                       lahf     
0x100199df +bcf   f6 c4 44                 test     ah, 0x44   ; PF: PF_Translucent|PF_Modulated
0x100199e2 +bd2   7a 07                    jp       0x100199eb
0x100199e4 +bd4   b8 01 00 00 00           mov      eax, 1   ; PF: PF_Invisible
0x100199e9 +bd9   eb 02                    jmp      0x100199ed
0x100199eb +bdb   33 c0                    xor      eax, eax
0x100199ed +bdd   3b c1                    cmp      eax, ecx
0x100199ef +bdf   74 3b                    je       0x10019a2c
0x100199f1 +be1   33 f6                    xor      esi, esi
0x100199f3 +be3   89 b5 4c f6 ff ff        mov      dword ptr [ebp - 0x9b4], esi
0x100199f9 +be9   8b bd fc f6 ff ff        mov      edi, dword ptr [ebp - 0x904]
0x100199ff +bef   90                       nop      
0x10019a00 +bf0   8b 8d 3c f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c4]
0x10019a06 +bf6   8b c1                    mov      eax, ecx
0x10019a08 +bf8   99                       cdq      
0x10019a09 +bf9   2b c2                    sub      eax, edx
0x10019a0b +bfb   d1 f8                    sar      eax, 1
0x10019a0d +bfd   3b f0                    cmp      esi, eax
0x10019a0f +bff   7d 23                    jge      0x10019a34
0x10019a11 +c01   8b d1                    mov      edx, ecx
0x10019a13 +c03   2b d6                    sub      edx, esi
0x10019a15 +c05   8b 0c b7                 mov      ecx, dword ptr [edi + esi*4]
0x10019a18 +c08   8b 44 97 fc              mov      eax, dword ptr [edi + edx*4 - 4]
0x10019a1c +c0c   89 04 b7                 mov      dword ptr [edi + esi*4], eax
0x10019a1f +c0f   89 4c 97 fc              mov      dword ptr [edi + edx*4 - 4], ecx
0x10019a23 +c13   46                       inc      esi
0x10019a24 +c14   89 b5 4c f6 ff ff        mov      dword ptr [ebp - 0x9b4], esi
0x10019a2a +c1a   eb d4                    jmp      0x10019a00
0x10019a2c +c1c   8b 8d 3c f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c4]
0x10019a32 +c22   eb 06                    jmp      0x10019a3a
0x10019a34 +c24   8b bd 24 f7 ff ff        mov      edi, dword ptr [ebp - 0x8dc]
0x10019a3a +c2a   0f 31                    rdtsc    
0x10019a3c +c2c   29 05 a8 fa 05 10        sub      dword ptr [0x1005faa8], eax
0x10019a42 +c32   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x10019a48 +c38   ff b0 ac 00 00 00        push     dword ptr [eax + 0xac]
0x10019a4e +c3e   8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x10019a54 +c44   f6 40 37 08              test     byte ptr [eax + 0x37], 8   ; PF: PF_NotSolid
0x10019a58 +c48   b8 00 00 00 00           mov      eax, 0
0x10019a5d +c4d   0f 45 85 e4 f6 ff ff     cmovne   eax, dword ptr [ebp - 0x91c]
0x10019a64 +c54   50                       push     eax
0x10019a65 +c55   51                       push     ecx
0x10019a66 +c56   ff b5 fc f6 ff ff        push     dword ptr [ebp - 0x904]
0x10019a6c +c5c   e8 ff 19 00 00           call     0x1001b470   ; -> sub_1b470
0x10019a71 +c61   83 c4 10                 add      esp, 0x10
0x10019a74 +c64   8b c8                    mov      ecx, eax
0x10019a76 +c66   0f 31                    rdtsc    
0x10019a78 +c68   8b f0                    mov      esi, eax
0x10019a7a +c6a   89 95 14 f7 ff ff        mov      dword ptr [ebp - 0x8ec], edx
0x10019a80 +c70   a1 a8 fa 05 10           mov      eax, dword ptr [0x1005faa8]
0x10019a85 +c75   83 c0 de                 add      eax, -0x22
0x10019a88 +c78   03 c6                    add      eax, esi
0x10019a8a +c7a   a3 a8 fa 05 10           mov      dword ptr [0x1005faa8], eax
0x10019a8f +c7f   85 c9                    test     ecx, ecx
0x10019a91 +c81   0f 84 54 0d 00 00        je       0x1001a7eb
0x10019a97 +c87   8b 85 e0 f6 ff ff        mov      eax, dword ptr [ebp - 0x920]
0x10019a9d +c8d   8b 08                    mov      ecx, dword ptr [eax]
0x10019a9f +c8f   8b 85 40 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c0]
0x10019aa5 +c95   85 c9                    test     ecx, ecx
0x10019aa7 +c97   74 0c                    je       0x10019ab5
0x10019aa9 +c99   0b 81 80 00 00 00        or       eax, dword ptr [ecx + 0x80]
0x10019aaf +c9f   89 85 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], eax
0x10019ab5 +ca5   23 85 48 f6 ff ff        and      eax, dword ptr [ebp - 0x9b8]
0x10019abb +cab   89 85 40 f7 ff ff        mov      dword ptr [ebp - 0x8c0], eax
0x10019ac1 +cb1   89 85 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], eax
0x10019ac7 +cb7   25 47 00 03 14           and      eax, 0x14030047
0x10019acc +cbc   b8 00 00 00 00           mov      eax, 0
0x10019ad1 +cc1   89 85 e8 f6 ff ff        mov      dword ptr [ebp - 0x918], eax
0x10019ad7 +cc7   75 3b                    jne      0x10019b14
0x10019ad9 +cc9   8b b5 44 f7 ff ff        mov      esi, dword ptr [ebp - 0x8bc]
0x10019adf +ccf   0f b6 44 37 34           movzx    eax, byte ptr [edi + esi + 0x34]
0x10019ae4 +cd4   50                       push     eax
0x10019ae5 +cd5   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x10019aeb +cdb   8b 48 04                 mov      ecx, dword ptr [eax + 4]
0x10019aee +cde   ff 15 8c 43 03 10        call     dword ptr [0x1003438c]   ; -> Engine.dll!?GetZoneActor@ULevel@@QAEPAVAZoneInfo@@H@Z
0x10019af4 +ce4   8b 4e 1c                 mov      ecx, dword ptr [esi + 0x1c]
0x10019af7 +ce7   8b 95 b8 f6 ff ff        mov      edx, dword ptr [ebp - 0x948]
0x10019afd +ced   8b 0c 8a                 mov      ecx, dword ptr [edx + ecx*4]
0x10019b00 +cf0   89 8d e8 f6 ff ff        mov      dword ptr [ebp - 0x918], ecx
0x10019b06 +cf6   85 c9                    test     ecx, ecx
0x10019b08 +cf8   74 0a                    je       0x10019b14
0x10019b0a +cfa   39 41 34                 cmp      dword ptr [ecx + 0x34], eax
0x10019b0d +cfd   74 16                    je       0x10019b25
0x10019b0f +cff   8b 49 3c                 mov      ecx, dword ptr [ecx + 0x3c]
0x10019b12 +d02   eb ec                    jmp      0x10019b00
0x10019b14 +d04   8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x10019b1a +d0a   83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x10019b1e +d0e   b8 f0 6b 04 10           mov      eax, 0x10046bf0
0x10019b23 +d13   75 05                    jne      0x10019b2a
0x10019b25 +d15   a1 b8 41 03 10           mov      eax, dword ptr [0x100341b8]
0x10019b2a +d1a   8b b5 38 f7 ff ff        mov      esi, dword ptr [ebp - 0x8c8]
0x10019b30 +d20   83 c6 14                 add      esi, 0x14
0x10019b33 +d23   50                       push     eax
0x10019b34 +d24   ff 35 40 fa 05 10        push     dword ptr [0x1005fa40]
0x10019b3a +d2a   ff 35 3c fa 05 10        push     dword ptr [0x1005fa3c]
0x10019b40 +d30   8b ce                    mov      ecx, esi
0x10019b42 +d32   e8 a9 39 00 00           call     0x1001d4f0   ; -> ?AllocIndex@FSpanBuffer@@QAEXHHPAVFMemStack@@@Z
0x10019b47 +d37   0f 31                    rdtsc    
0x10019b49 +d39   29 05 ac fa 05 10        sub      dword ptr [0x1005faac], eax
0x10019b4f +d3f   8b 95 40 f7 ff ff        mov      edx, dword ptr [ebp - 0x8c0]
0x10019b55 +d45   8b c2                    mov      eax, edx
0x10019b57 +d47   25 47 00 02 10           and      eax, 0x10020047
0x10019b5c +d4c   89 85 2c f7 ff ff        mov      dword ptr [ebp - 0x8d4], eax
0x10019b62 +d52   74 3f                    je       0x10019ba3
0x10019b64 +d54   8b c2                    mov      eax, edx
0x10019b66 +d56   25 01 00 00 04           and      eax, 0x4000001   ; PF: PF_Invisible|PF_Portal
0x10019b6b +d5b   3d 01 00 00 04           cmp      eax, 0x4000001   ; PF: PF_Invisible|PF_Portal
0x10019b70 +d60   0f 95 c1                 setne    cl
0x10019b73 +d63   0f ba e2 1b              bt       edx, 0x1b
0x10019b77 +d67   0f 93 c0                 setae    al
0x10019b7a +d6a   84 c8                    test     al, cl
0x10019b7c +d6c   74 25                    je       0x10019ba3
0x10019b7e +d6e   8b 0d 3c fa 05 10        mov      ecx, dword ptr [0x1005fa3c]
0x10019b84 +d74   a1 0c 08 06 10           mov      eax, dword ptr [0x1006080c]
0x10019b89 +d79   8d 04 c8                 lea      eax, [eax + ecx*8]
0x10019b8c +d7c   50                       push     eax
0x10019b8d +d7d   ff 35 40 fa 05 10        push     dword ptr [0x1005fa40]
0x10019b93 +d83   51                       push     ecx
0x10019b94 +d84   ff b5 e4 f6 ff ff        push     dword ptr [ebp - 0x91c]
0x10019b9a +d8a   8b ce                    mov      ecx, esi
0x10019b9c +d8c   e8 6f 41 00 00           call     0x1001dd10   ; -> ?CopyFromRaster@FSpanBuffer@@QAEHAAV1@HHPAUFRasterSpan@@@Z
0x10019ba1 +d91   eb 23                    jmp      0x10019bc6
0x10019ba3 +d93   8b 0d 3c fa 05 10        mov      ecx, dword ptr [0x1005fa3c]
0x10019ba9 +d99   a1 0c 08 06 10           mov      eax, dword ptr [0x1006080c]
0x10019bae +d9e   8d 04 c8                 lea      eax, [eax + ecx*8]
0x10019bb1 +da1   50                       push     eax
0x10019bb2 +da2   ff 35 40 fa 05 10        push     dword ptr [0x1005fa40]
0x10019bb8 +da8   51                       push     ecx
0x10019bb9 +da9   ff b5 e4 f6 ff ff        push     dword ptr [ebp - 0x91c]
0x10019bbf +daf   8b ce                    mov      ecx, esi
0x10019bc1 +db1   e8 aa 43 00 00           call     0x1001df70   ; -> ?CopyFromRasterUpdate@FSpanBuffer@@QAEHAAV1@HHPAUFRasterSpan@@@Z
0x10019bc6 +db6   8b f8                    mov      edi, eax
0x10019bc8 +db8   0f 31                    rdtsc    
0x10019bca +dba   8b 0d ac fa 05 10        mov      ecx, dword ptr [0x1005faac]
0x10019bd0 +dc0   83 c1 de                 add      ecx, -0x22
0x10019bd3 +dc3   03 c1                    add      eax, ecx
0x10019bd5 +dc5   a3 ac fa 05 10           mov      dword ptr [0x1005faac], eax
0x10019bda +dca   a1 c0 41 03 10           mov      eax, dword ptr [0x100341c0]
0x10019bdf +dcf   8b 08                    mov      ecx, dword ptr [eax]
0x10019be1 +dd1   85 c9                    test     ecx, ecx
0x10019be3 +dd3   74 13                    je       0x10019bf8
0x10019be5 +dd5   8b 85 d8 f6 ff ff        mov      eax, dword ptr [ebp - 0x928]
0x10019beb +ddb   85 c0                    test     eax, eax
0x10019bed +ddd   74 09                    je       0x10019bf8
0x10019bef +ddf   0f b6 b0 90 00 00 00     movzx    esi, byte ptr [eax + 0x90]
0x10019bf6 +de6   eb 06                    jmp      0x10019bfe
0x10019bf8 +de8   8b b5 dc f6 ff ff        mov      esi, dword ptr [ebp - 0x924]
0x10019bfe +dee   89 b5 44 f6 ff ff        mov      dword ptr [ebp - 0x9bc], esi
0x10019c04 +df4   33 c0                    xor      eax, eax
0x10019c06 +df6   39 85 2c f7 ff ff        cmp      dword ptr [ebp - 0x8d4], eax
0x10019c0c +dfc   0f 95 c0                 setne    al
0x10019c0f +dff   40                       inc      eax
0x10019c10 +e00   89 85 f0 f6 ff ff        mov      dword ptr [ebp - 0x910], eax
0x10019c16 +e06   89 85 bc f6 ff ff        mov      dword ptr [ebp - 0x944], eax
0x10019c1c +e0c   85 ff                    test     edi, edi
0x10019c1e +e0e   75 1d                    jne      0x10019c3d
0x10019c20 +e10   8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x10019c26 +e16   80 48 37 08              or       byte ptr [eax + 0x37], 8   ; PF: PF_NotSolid
0x10019c2a +e1a   8b 8d 38 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c8]
0x10019c30 +e20   8d 49 14                 lea      ecx, [ecx + 0x14]
0x10019c33 +e23   e8 28 4a 00 00           call     0x1001e660   ; -> ?Release@FSpanBuffer@@QAEXXZ
0x10019c38 +e28   e9 ae 0b 00 00           jmp      0x1001a7eb
0x10019c3d +e2d   8b 85 40 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c0]
0x10019c43 +e33   84 c0                    test     al, al
0x10019c45 +e35   79 33                    jns      0x10019c7a
0x10019c47 +e37   8b bd 4c f7 ff ff        mov      edi, dword ptr [ebp - 0x8b4]
0x10019c4d +e3d   85 c9                    test     ecx, ecx
0x10019c4f +e3f   0f 85 bb 00 00 00        jne      0x10019d10
0x10019c55 +e45   56                       push     esi
0x10019c56 +e46   8b 4f 04                 mov      ecx, dword ptr [edi + 4]
0x10019c59 +e49   ff 15 8c 43 03 10        call     dword ptr [0x1003438c]   ; -> Engine.dll!?GetZoneActor@ULevel@@QAEPAVAZoneInfo@@H@Z
0x10019c5f +e4f   83 b8 78 02 00 00 00     cmp      dword ptr [eax + 0x278], 0
0x10019c66 +e56   0f 85 9c 00 00 00        jne      0x10019d08
0x10019c6c +e5c   a1 c0 41 03 10           mov      eax, dword ptr [0x100341c0]
0x10019c71 +e61   83 38 00                 cmp      dword ptr [eax], 0
0x10019c74 +e64   0f 85 96 00 00 00        jne      0x10019d10
0x10019c7a +e6a   8b 95 f8 f6 ff ff        mov      edx, dword ptr [ebp - 0x908]
0x10019c80 +e70   8b 8d 40 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c0]
0x10019c86 +e76   f7 c1 00 00 00 08        test     ecx, 0x8000000   ; PF: PF_Mirror
0x10019c8c +e7c   0f 84 3c 03 00 00        je       0x10019fce
0x10019c92 +e82   8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x10019c98 +e88   83 78 1c 03              cmp      dword ptr [eax + 0x1c], 3   ; PF: PF_Invisible|PF_Masked
0x10019c9c +e8c   0f 8d 2c 03 00 00        jge      0x10019fce
0x10019ca2 +e92   8b 02                    mov      eax, dword ptr [edx]
0x10019ca4 +e94   f7 80 7c 04 00 00 00 08 00 00 test     dword ptr [eax + 0x47c], 0x800   ; PF: PF_NoSmooth
0x10019cae +e9e   0f 84 1a 03 00 00        je       0x10019fce
0x10019cb4 +ea4   c6 45 fc 05              mov      byte ptr [ebp - 4], 5   ; PF: PF_Invisible|PF_Translucent
0x10019cb8 +ea8   9b                       wait     
0x10019cb9 +ea9   f6 c1 04                 test     cl, 4   ; PF: PF_Translucent
0x10019cbc +eac   0f 84 ad 01 00 00        je       0x10019e6f
0x10019cc2 +eb2   8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x10019cc8 +eb8   83 78 5c 00              cmp      dword ptr [eax + 0x5c], 0
0x10019ccc +ebc   0f 85 9d 01 00 00        jne      0x10019e6f
0x10019cd2 +ec2   83 e1 fb                 and      ecx, 0xfffffffb
0x10019cd5 +ec5   89 8d 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], ecx
0x10019cdb +ecb   81 c9 00 00 00 80        or       ecx, 0x80000000
0x10019ce1 +ed1   89 8d 40 f7 ff ff        mov      dword ptr [ebp - 0x8c0], ecx
0x10019ce7 +ed7   89 8d 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], ecx
0x10019ced +edd   be 01 00 00 00           mov      esi, 1   ; PF: PF_Invisible
0x10019cf2 +ee2   89 b5 f0 f6 ff ff        mov      dword ptr [ebp - 0x910], esi
0x10019cf8 +ee8   89 b5 bc f6 ff ff        mov      dword ptr [ebp - 0x944], esi
0x10019cfe +eee   9b                       wait     
0x10019cff +eef   c6 45 fc 00              mov      byte ptr [ebp - 4], 0
0x10019d03 +ef3   e9 25 06 00 00           jmp      0x1001a32d
0x10019d08 +ef8   8b 8d d8 f6 ff ff        mov      ecx, dword ptr [ebp - 0x928]
0x10019d0e +efe   eb 0e                    jmp      0x10019d1e
0x10019d10 +f00   8b 8d d8 f6 ff ff        mov      ecx, dword ptr [ebp - 0x928]
0x10019d16 +f06   85 c9                    test     ecx, ecx
0x10019d18 +f08   0f 84 5c ff ff ff        je       0x10019c7a
0x10019d1e +f0e   8b 95 f8 f6 ff ff        mov      edx, dword ptr [ebp - 0x908]
0x10019d24 +f14   83 7f 1c 03              cmp      dword ptr [edi + 0x1c], 3   ; PF: PF_Invisible|PF_Masked
0x10019d28 +f18   0f 8d 52 ff ff ff        jge      0x10019c80
0x10019d2e +f1e   8b 02                    mov      eax, dword ptr [edx]
0x10019d30 +f20   f7 80 7c 04 00 00 00 08 00 00 test     dword ptr [eax + 0x47c], 0x800   ; PF: PF_NoSmooth
0x10019d3a +f2a   0f 84 40 ff ff ff        je       0x10019c80
0x10019d40 +f30   c6 45 fc 03              mov      byte ptr [ebp - 4], 3   ; PF: PF_Invisible|PF_Masked
0x10019d44 +f34   9b                       wait     
0x10019d45 +f35   a1 c0 41 03 10           mov      eax, dword ptr [0x100341c0]
0x10019d4a +f3a   83 38 00                 cmp      dword ptr [eax], 0
0x10019d4d +f3d   74 04                    je       0x10019d53
0x10019d4f +f3f   8b f1                    mov      esi, ecx
0x10019d51 +f41   eb 10                    jmp      0x10019d63
0x10019d53 +f43   56                       push     esi
0x10019d54 +f44   8b 4f 04                 mov      ecx, dword ptr [edi + 4]
0x10019d57 +f47   ff 15 8c 43 03 10        call     dword ptr [0x1003438c]   ; -> Engine.dll!?GetZoneActor@ULevel@@QAEPAVAZoneInfo@@H@Z
0x10019d5d +f4d   8b b0 78 02 00 00        mov      esi, dword ptr [eax + 0x278]
0x10019d63 +f53   8d 47 34                 lea      eax, [edi + 0x34]
0x10019d66 +f56   50                       push     eax
0x10019d67 +f57   8d 8d 7c f7 ff ff        lea      ecx, [ebp - 0x884]
0x10019d6d +f5d   ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x10019d73 +f63   8d 47 34                 lea      eax, [edi + 0x34]
0x10019d76 +f66   50                       push     eax
0x10019d77 +f67   8d 85 18 f6 ff ff        lea      eax, [ebp - 0x9e8]
0x10019d7d +f6d   50                       push     eax
0x10019d7e +f6e   8d 8d 7c f7 ff ff        lea      ecx, [ebp - 0x884]
0x10019d84 +f74   ff 15 64 42 03 10        call     dword ptr [0x10034264]   ; -> Core.dll!??ZFVector@@QAE?AV0@ABV0@@Z
0x10019d8a +f7a   8d 86 dc 00 00 00        lea      eax, [esi + 0xdc]
0x10019d90 +f80   50                       push     eax
0x10019d91 +f81   8d 8d 7c f7 ff ff        lea      ecx, [ebp - 0x884]
0x10019d97 +f87   ff 15 c8 40 03 10        call     dword ptr [0x100340c8]   ; -> Core.dll!??_0FCoords@@QAEAAV0@ABVFRotator@@@Z
0x10019d9d +f8d   8d 86 d0 00 00 00        lea      eax, [esi + 0xd0]
0x10019da3 +f93   50                       push     eax
0x10019da4 +f94   8d 85 0c f6 ff ff        lea      eax, [ebp - 0x9f4]
0x10019daa +f9a   50                       push     eax
0x10019dab +f9b   8d 8d 7c f7 ff ff        lea      ecx, [ebp - 0x884]
0x10019db1 +fa1   ff 15 ec 41 03 10        call     dword ptr [0x100341ec]   ; -> Core.dll!??YFVector@@QAE?AV0@ABV0@@Z
0x10019db7 +fa7   66 0f 6e 05 3c fa 05 10  movd     xmm0, dword ptr [0x1005fa3c]
0x10019dbf +faf   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019dc2 +fb2   f3 0f 11 85 6c f7 ff ff  movss    dword ptr [ebp - 0x894], xmm0
0x10019dca +fba   66 0f 6e 05 40 fa 05 10  movd     xmm0, dword ptr [0x1005fa40]
0x10019dd2 +fc2   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019dd5 +fc5   f3 0f 11 85 74 f7 ff ff  movss    dword ptr [ebp - 0x88c], xmm0
0x10019ddd +fcd   66 0f 6e 05 44 fa 05 10  movd     xmm0, dword ptr [0x1005fa44]
0x10019de5 +fd5   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019de8 +fd8   f3 0f 11 85 68 f7 ff ff  movss    dword ptr [ebp - 0x898], xmm0
0x10019df0 +fe0   66 0f 6e 05 48 fa 05 10  movd     xmm0, dword ptr [0x1005fa48]
0x10019df8 +fe8   0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019dfb +feb   f3 0f 11 85 70 f7 ff ff  movss    dword ptr [ebp - 0x890], xmm0
0x10019e03 +ff3   8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x10019e09 +ff9   8b 11                    mov      edx, dword ptr [ecx]
0x10019e0b +ffb   8d 85 68 f7 ff ff        lea      eax, [ebp - 0x898]
0x10019e11 +1001  c7 85 14 f7 ff ff 00 00 00 00 mov      dword ptr [ebp - 0x8ec], 0
0x10019e1b +100b  83 79 34 00              cmp      dword ptr [ecx + 0x34], 0
0x10019e1f +100f  0f 45 85 14 f7 ff ff     cmovne   eax, dword ptr [ebp - 0x8ec]
0x10019e26 +1016  50                       push     eax
0x10019e27 +1017  8d 85 7c f7 ff ff        lea      eax, [ebp - 0x884]
0x10019e2d +101d  50                       push     eax
0x10019e2e +101e  8d 47 24                 lea      eax, [edi + 0x24]
0x10019e31 +1021  50                       push     eax
0x10019e32 +1022  51                       push     ecx
0x10019e33 +1023  f3 0f 10 47 20           movss    xmm0, dword ptr [edi + 0x20]
0x10019e38 +1028  f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x10019e3d +102d  0f b6 86 90 00 00 00     movzx    eax, byte ptr [esi + 0x90]
0x10019e44 +1034  50                       push     eax
0x10019e45 +1035  6a 00                    push     0
0x10019e47 +1037  ff 77 04                 push     dword ptr [edi + 4]
0x10019e4a +103a  8b 85 38 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c8]
0x10019e50 +1040  83 c0 14                 add      eax, 0x14
0x10019e53 +1043  50                       push     eax
0x10019e54 +1044  57                       push     edi
0x10019e55 +1045  ff 52 68                 call     dword ptr [edx + 0x68]
0x10019e58 +1048  9b                       wait     
0x10019e59 +1049  c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x10019e60 +1050  e9 86 09 00 00           jmp      0x1001a7eb
0x10019e65 +1055  68 d4 6c 03 10           push     0x10036cd4
0x10019e6a +105a  e9 8f 0b 00 00           jmp      0x1001a9fe
0x10019e6f +105f  66 0f 6e 05 3c fa 05 10  movd     xmm0, dword ptr [0x1005fa3c]
0x10019e77 +1067  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019e7a +106a  f3 0f 11 85 9c f7 ff ff  movss    dword ptr [ebp - 0x864], xmm0
0x10019e82 +1072  66 0f 6e 05 40 fa 05 10  movd     xmm0, dword ptr [0x1005fa40]
0x10019e8a +107a  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019e8d +107d  f3 0f 11 85 a4 f7 ff ff  movss    dword ptr [ebp - 0x85c], xmm0
0x10019e95 +1085  66 0f 6e 05 44 fa 05 10  movd     xmm0, dword ptr [0x1005fa44]
0x10019e9d +108d  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019ea0 +1090  f3 0f 11 85 98 f7 ff ff  movss    dword ptr [ebp - 0x868], xmm0
0x10019ea8 +1098  66 0f 6e 05 48 fa 05 10  movd     xmm0, dword ptr [0x1005fa48]
0x10019eb0 +10a0  0f 5b c0                 cvtdq2ps xmm0, xmm0
0x10019eb3 +10a3  f3 0f 11 85 a0 f7 ff ff  movss    dword ptr [ebp - 0x860], xmm0
0x10019ebb +10ab  8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x10019ec1 +10b1  8b 31                    mov      esi, dword ptr [ecx]
0x10019ec3 +10b3  8d 85 98 f7 ff ff        lea      eax, [ebp - 0x868]
0x10019ec9 +10b9  33 d2                    xor      edx, edx
0x10019ecb +10bb  39 51 34                 cmp      dword ptr [ecx + 0x34], edx
0x10019ece +10be  0f 45 c2                 cmovne   eax, edx
0x10019ed1 +10c1  50                       push     eax
0x10019ed2 +10c2  8b bd 44 f7 ff ff        mov      edi, dword ptr [ebp - 0x8bc]
0x10019ed8 +10c8  57                       push     edi
0x10019ed9 +10c9  8d 85 54 f5 ff ff        lea      eax, [ebp - 0xaac]
0x10019edf +10cf  50                       push     eax
0x10019ee0 +10d0  8b 8d ec f6 ff ff        mov      ecx, dword ptr [ebp - 0x914]
0x10019ee6 +10d6  ff 15 cc 40 03 10        call     dword ptr [0x100340cc]   ; -> Core.dll!?MirrorByPlane@FCoords@@QBE?AV1@ABVFPlane@@@Z
0x10019eec +10dc  50                       push     eax
0x10019eed +10dd  8d 85 b4 f5 ff ff        lea      eax, [ebp - 0xa4c]
0x10019ef3 +10e3  50                       push     eax
0x10019ef4 +10e4  ff b5 ec f6 ff ff        push     dword ptr [ebp - 0x914]
0x10019efa +10ea  8d 85 a4 f5 ff ff        lea      eax, [ebp - 0xa5c]
0x10019f00 +10f0  50                       push     eax
0x10019f01 +10f1  8b cf                    mov      ecx, edi
0x10019f03 +10f3  ff 15 dc 40 03 10        call     dword ptr [0x100340dc]   ; -> Core.dll!?TransformPlaneByOrtho@FPlane@@QBE?AV1@ABVFCoords@@@Z
0x10019f09 +10f9  8b c8                    mov      ecx, eax
0x10019f0b +10fb  ff 15 e0 40 03 10        call     dword ptr [0x100340e0]   ; -> Core.dll!?Flip@FPlane@@QBE?AV1@XZ
0x10019f11 +1101  50                       push     eax
0x10019f12 +1102  8b 95 4c f7 ff ff        mov      edx, dword ptr [ebp - 0x8b4]
0x10019f18 +1108  f3 0f 10 42 20           movss    xmm0, dword ptr [edx + 0x20]
0x10019f1d +110d  0f 57 05 f0 52 03 10     xorps    xmm0, xmmword ptr [0x100352f0]   ; [0x100352f0] f32=-0.0
0x10019f24 +1114  51                       push     ecx
0x10019f25 +1115  f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x10019f2a +111a  ff b5 dc f6 ff ff        push     dword ptr [ebp - 0x924]
0x10019f30 +1120  6a 00                    push     0
0x10019f32 +1122  ff 72 04                 push     dword ptr [edx + 4]
0x10019f35 +1125  8b 85 38 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c8]
0x10019f3b +112b  83 c0 14                 add      eax, 0x14
0x10019f3e +112e  50                       push     eax
0x10019f3f +112f  52                       push     edx
0x10019f40 +1130  8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x10019f46 +1136  ff 56 68                 call     dword ptr [esi + 0x68]
0x10019f49 +1139  33 f6                    xor      esi, esi
0x10019f4b +113b  89 b5 f0 f6 ff ff        mov      dword ptr [ebp - 0x910], esi
0x10019f51 +1141  89 b5 bc f6 ff ff        mov      dword ptr [ebp - 0x944], esi
0x10019f57 +1147  39 b5 2c f7 ff ff        cmp      dword ptr [ebp - 0x8d4], esi
0x10019f5d +114d  75 26                    jne      0x10019f85
0x10019f5f +114f  8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x10019f65 +1155  39 70 48                 cmp      dword ptr [eax + 0x48], esi
0x10019f68 +1158  74 0a                    je       0x10019f74
0x10019f6a +115a  9b                       wait     
0x10019f6b +115b  c6 45 fc 00              mov      byte ptr [ebp - 4], 0
0x10019f6f +115f  e9 77 08 00 00           jmp      0x1001a7eb
0x10019f74 +1164  8b 95 40 f7 ff ff        mov      edx, dword ptr [ebp - 0x8c0]
0x10019f7a +116a  83 ca 01                 or       edx, 1   ; PF: PF_Invisible
0x10019f7d +116d  89 95 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], edx
0x10019f83 +1173  eb 06                    jmp      0x10019f8b
0x10019f85 +1175  8b 95 40 f7 ff ff        mov      edx, dword ptr [ebp - 0x8c0]
0x10019f8b +117b  81 ca 00 00 00 80        or       edx, 0x80000000
0x10019f91 +1181  89 95 40 f7 ff ff        mov      dword ptr [ebp - 0x8c0], edx
0x10019f97 +1187  89 95 04 f7 ff ff        mov      dword ptr [ebp - 0x8fc], edx
0x10019f9d +118d  9b                       wait     
0x10019f9e +118e  c6 45 fc 00              mov      byte ptr [ebp - 4], 0
0x10019fa2 +1192  e9 86 03 00 00           jmp      0x1001a32d
0x10019fa7 +1197  8b 85 30 f6 ff ff        mov      eax, dword ptr [ebp - 0x9d0]
0x10019fad +119d  89 85 94 f6 ff ff        mov      dword ptr [ebp - 0x96c], eax
0x10019fb3 +11a3  68 7c ea 03 10           push     0x1003ea7c
0x10019fb8 +11a8  8d 85 94 f6 ff ff        lea      eax, [ebp - 0x96c]
0x10019fbe +11ae  50                       push     eax
0x10019fbf +11af  e9 4c 0a 00 00           jmp      0x1001aa10
0x10019fc4 +11b4  68 f0 6c 03 10           push     0x10036cf0
0x10019fc9 +11b9  e9 30 0a 00 00           jmp      0x1001a9fe
0x10019fce +11be  f7 c1 00 00 00 04        test     ecx, 0x4000000   ; PF: PF_Portal
0x10019fd4 +11c4  0f 84 4a 03 00 00        je       0x1001a324
0x10019fda +11ca  8b 02                    mov      eax, dword ptr [edx]
0x10019fdc +11cc  8b 95 2c f7 ff ff        mov      edx, dword ptr [ebp - 0x8d4]
0x10019fe2 +11d2  83 b8 80 04 00 00 02     cmp      dword ptr [eax + 0x480], 2   ; PF: PF_Masked
0x10019fe9 +11d9  75 08                    jne      0x10019ff3
0x10019feb +11db  85 d2                    test     edx, edx
0x10019fed +11dd  0f 84 31 03 00 00        je       0x1001a324
0x10019ff3 +11e3  8b c1                    mov      eax, ecx
0x10019ff5 +11e5  f7 d0                    not      eax
0x10019ff7 +11e7  83 e0 01                 and      eax, 1   ; PF: PF_Invisible
0x10019ffa +11ea  89 85 14 f7 ff ff        mov      dword ptr [ebp - 0x8ec], eax
0x1001a000 +11f0  8a 8d 53 f7 ff ff        mov      cl, byte ptr [ebp - 0x8ad]
0x1001a006 +11f6  8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x1001a00c +11fc  8b b5 24 f7 ff ff        mov      esi, dword ptr [ebp - 0x8dc]
0x1001a012 +1202  2b c6                    sub      eax, esi
0x1001a014 +1204  f6 d9                    neg      cl
0x1001a016 +1206  1a c9                    sbb      cl, cl
0x1001a018 +1208  22 48 35                 and      cl, byte ptr [eax + 0x35]
0x1001a01b +120b  88 8d 0b f7 ff ff        mov      byte ptr [ebp - 0x8f5], cl
0x1001a021 +1211  0f 84 e6 02 00 00        je       0x1001a30d
0x1001a027 +1217  85 d2                    test     edx, edx
0x1001a029 +1219  0f 84 de 02 00 00        je       0x1001a30d
0x1001a02f +121f  0f b6 c1                 movzx    eax, cl
0x1001a032 +1222  89 85 2c f7 ff ff        mov      dword ptr [ebp - 0x8d4], eax
0x1001a038 +1228  8d 04 40                 lea      eax, [eax + eax*2]
0x1001a03b +122b  8b 8d 20 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8e0]
0x1001a041 +1231  8b bc c1 04 01 00 00     mov      edi, dword ptr [ecx + eax*8 + 0x104]
0x1001a048 +1238  89 bd 34 f6 ff ff        mov      dword ptr [ebp - 0x9cc], edi
0x1001a04e +123e  85 ff                    test     edi, edi
0x1001a050 +1240  0f 84 da 01 00 00        je       0x1001a230
0x1001a056 +1246  ff 15 34 43 03 10        call     dword ptr [0x10034334]   ; -> Engine.dll!?StaticClass@AWarpZoneInfo@@SAPAVUClass@@XZ
0x1001a05c +124c  8b d0                    mov      edx, eax
0x1001a05e +124e  8b 4f 24                 mov      ecx, dword ptr [edi + 0x24]
0x1001a061 +1251  85 c9                    test     ecx, ecx
0x1001a063 +1253  74 09                    je       0x1001a06e
0x1001a065 +1255  3b ca                    cmp      ecx, edx
0x1001a067 +1257  74 14                    je       0x1001a07d
0x1001a069 +1259  8b 49 28                 mov      ecx, dword ptr [ecx + 0x28]
0x1001a06c +125c  eb f3                    jmp      0x1001a061
0x1001a06e +125e  33 c0                    xor      eax, eax
0x1001a070 +1260  85 d2                    test     edx, edx
0x1001a072 +1262  0f 94 c0                 sete     al
0x1001a075 +1265  85 c0                    test     eax, eax
0x1001a077 +1267  0f 84 b3 01 00 00        je       0x1001a230
0x1001a07d +126d  8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x1001a083 +1273  83 78 1c 03              cmp      dword ptr [eax + 0x1c], 3   ; PF: PF_Invisible|PF_Masked
0x1001a087 +1277  0f 8d a3 01 00 00        jge      0x1001a230
0x1001a08d +127d  83 bf b4 03 00 00 00     cmp      dword ptr [edi + 0x3b4], 0
0x1001a094 +1284  74 09                    je       0x1001a09f
0x1001a096 +1286  83 bf b0 03 00 00 00     cmp      dword ptr [edi + 0x3b0], 0
0x1001a09d +128d  75 22                    jne      0x1001a0c1
0x1001a09f +128f  8b cf                    mov      ecx, edi
0x1001a0a1 +1291  ff 15 38 43 03 10        call     dword ptr [0x10034338]   ; -> Engine.dll!?eventGenerate@AWarpZoneInfo@@QAEXXZ
0x1001a0a7 +1297  83 bf b4 03 00 00 00     cmp      dword ptr [edi + 0x3b4], 0
0x1001a0ae +129e  0f 84 7c 01 00 00        je       0x1001a230
0x1001a0b4 +12a4  83 bf b0 03 00 00 00     cmp      dword ptr [edi + 0x3b0], 0
0x1001a0bb +12ab  0f 84 6f 01 00 00        je       0x1001a230
0x1001a0c1 +12b1  c6 45 fc 07              mov      byte ptr [ebp - 4], 7   ; PF: PF_Invisible|PF_Masked|PF_Translucent
0x1001a0c5 +12b5  9b                       wait     
0x1001a0c6 +12b6  85 f6                    test     esi, esi
0x1001a0c8 +12b8  74 15                    je       0x1001a0df
0x1001a0ca +12ba  8d 85 44 f5 ff ff        lea      eax, [ebp - 0xabc]
0x1001a0d0 +12c0  50                       push     eax
0x1001a0d1 +12c1  8b 8d 44 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8bc]
0x1001a0d7 +12c7  ff 15 e0 40 03 10        call     dword ptr [0x100340e0]   ; -> Core.dll!?Flip@FPlane@@QBE?AV1@XZ
0x1001a0dd +12cd  eb 12                    jmp      0x1001a0f1
0x1001a0df +12cf  ff b5 44 f7 ff ff        push     dword ptr [ebp - 0x8bc]
0x1001a0e5 +12d5  8d 8d 94 f5 ff ff        lea      ecx, [ebp - 0xa6c]
0x1001a0eb +12db  ff 15 04 42 03 10        call     dword ptr [0x10034204]   ; -> Core.dll!??0FPlane@@QAE@ABV0@@Z
0x1001a0f1 +12e1  89 85 2c f7 ff ff        mov      dword ptr [ebp - 0x8d4], eax
0x1001a0f7 +12e7  8d 87 80 03 00 00        lea      eax, [edi + 0x380]
0x1001a0fd +12ed  50                       push     eax
0x1001a0fe +12ee  ff b5 ec f6 ff ff        push     dword ptr [ebp - 0x914]
0x1001a104 +12f4  8d 8d 54 f5 ff ff        lea      ecx, [ebp - 0xaac]
0x1001a10a +12fa  ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x1001a110 +1300  8b c8                    mov      ecx, eax
0x1001a112 +1302  ff 15 70 42 03 10        call     dword ptr [0x10034270]   ; -> Core.dll!??XFCoords@@QAEAAV0@ABV0@@Z
0x1001a118 +1308  50                       push     eax
0x1001a119 +1309  8d 8d c4 f5 ff ff        lea      ecx, [ebp - 0xa3c]
0x1001a11f +130f  ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x1001a125 +1315  8d 85 e4 f4 ff ff        lea      eax, [ebp - 0xb1c]
0x1001a12b +131b  50                       push     eax
0x1001a12c +131c  8b 8f b0 03 00 00        mov      ecx, dword ptr [edi + 0x3b0]
0x1001a132 +1322  81 c1 80 03 00 00        add      ecx, 0x380
0x1001a138 +1328  ff 15 24 42 03 10        call     dword ptr [0x10034224]   ; -> Core.dll!?Transpose@FCoords@@QBE?AV1@XZ
0x1001a13e +132e  50                       push     eax
0x1001a13f +132f  8d 85 c4 f5 ff ff        lea      eax, [ebp - 0xa3c]
0x1001a145 +1335  50                       push     eax
0x1001a146 +1336  8d 8d 14 f5 ff ff        lea      ecx, [ebp - 0xaec]
0x1001a14c +133c  ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x1001a152 +1342  8b c8                    mov      ecx, eax
0x1001a154 +1344  ff 15 70 42 03 10        call     dword ptr [0x10034270]   ; -> Core.dll!??XFCoords@@QAEAAV0@ABV0@@Z
0x1001a15a +134a  50                       push     eax
0x1001a15b +134b  8d 8d 7c f7 ff ff        lea      ecx, [ebp - 0x884]
0x1001a161 +1351  ff 15 74 42 03 10        call     dword ptr [0x10034274]   ; -> Core.dll!??0FCoords@@QAE@ABV0@@Z
0x1001a167 +1357  8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x1001a16d +135d  8b 30                    mov      esi, dword ptr [eax]
0x1001a16f +135f  6a 00                    push     0
0x1001a171 +1361  8d 85 7c f7 ff ff        lea      eax, [ebp - 0x884]
0x1001a177 +1367  50                       push     eax
0x1001a178 +1368  ff b5 ec f6 ff ff        push     dword ptr [ebp - 0x914]
0x1001a17e +136e  8d 85 84 f5 ff ff        lea      eax, [ebp - 0xa7c]
0x1001a184 +1374  50                       push     eax
0x1001a185 +1375  8b 8d 2c f7 ff ff        mov      ecx, dword ptr [ebp - 0x8d4]
0x1001a18b +137b  ff 15 dc 40 03 10        call     dword ptr [0x100340dc]   ; -> Core.dll!?TransformPlaneByOrtho@FPlane@@QBE?AV1@ABVFCoords@@@Z
0x1001a191 +1381  50                       push     eax
0x1001a192 +1382  51                       push     ecx
0x1001a193 +1383  8b 95 4c f7 ff ff        mov      edx, dword ptr [ebp - 0x8b4]
0x1001a199 +1389  f3 0f 10 42 20           movss    xmm0, dword ptr [edx + 0x20]
0x1001a19e +138e  f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x1001a1a3 +1393  8b 87 b0 03 00 00        mov      eax, dword ptr [edi + 0x3b0]
0x1001a1a9 +1399  ff b0 7c 03 00 00        push     dword ptr [eax + 0x37c]
0x1001a1af +139f  8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x1001a1b5 +13a5  ff 70 1c                 push     dword ptr [eax + 0x1c]
0x1001a1b8 +13a8  ff b7 b4 03 00 00        push     dword ptr [edi + 0x3b4]
0x1001a1be +13ae  8b 85 38 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c8]
0x1001a1c4 +13b4  83 c0 14                 add      eax, 0x14
0x1001a1c7 +13b7  50                       push     eax
0x1001a1c8 +13b8  52                       push     edx
0x1001a1c9 +13b9  8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x1001a1cf +13bf  ff 56 68                 call     dword ptr [esi + 0x68]
0x1001a1d2 +13c2  33 c0                    xor      eax, eax
0x1001a1d4 +13c4  89 85 f0 f6 ff ff        mov      dword ptr [ebp - 0x910], eax
0x1001a1da +13ca  89 85 bc f6 ff ff        mov      dword ptr [ebp - 0x944], eax
0x1001a1e0 +13d0  8b 95 40 f7 ff ff        mov      edx, dword ptr [ebp - 0x8c0]
0x1001a1e6 +13d6  f6 c2 01                 test     dl, 1   ; PF: PF_Invisible
0x1001a1e9 +13d9  0f 84 9c fd ff ff        je       0x10019f8b
0x1001a1ef +13df  8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x1001a1f5 +13e5  83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x1001a1f9 +13e9  0f 84 8c fd ff ff        je       0x10019f8b
0x1001a1ff +13ef  9b                       wait     
0x1001a200 +13f0  c6 45 fc 00              mov      byte ptr [ebp - 4], 0
0x1001a204 +13f4  e9 e2 05 00 00           jmp      0x1001a7eb
0x1001a209 +13f9  8b 85 28 f6 ff ff        mov      eax, dword ptr [ebp - 0x9d8]
0x1001a20f +13ff  89 85 90 f6 ff ff        mov      dword ptr [ebp - 0x970], eax
0x1001a215 +1405  68 7c ea 03 10           push     0x1003ea7c
0x1001a21a +140a  8d 85 90 f6 ff ff        lea      eax, [ebp - 0x970]
0x1001a220 +1410  50                       push     eax
0x1001a221 +1411  e9 ea 07 00 00           jmp      0x1001aa10
0x1001a226 +1416  68 14 6d 03 10           push     0x10036d14
0x1001a22b +141b  e9 ce 07 00 00           jmp      0x1001a9fe
0x1001a230 +1420  8b b5 30 f7 ff ff        mov      esi, dword ptr [ebp - 0x8d0]
0x1001a236 +1426  8b bd 00 f7 ff ff        mov      edi, dword ptr [ebp - 0x900]
0x1001a23c +142c  8b 85 2c f7 ff ff        mov      eax, dword ptr [ebp - 0x8d4]
0x1001a242 +1432  33 c9                    xor      ecx, ecx
0x1001a244 +1434  33 d2                    xor      edx, edx
0x1001a246 +1436  0f ab c1                 bts      ecx, eax
0x1001a249 +1439  83 f8 20                 cmp      eax, 0x20   ; PF: PF_Semisolid
0x1001a24c +143c  0f 43 d1                 cmovae   edx, ecx
0x1001a24f +143f  33 ca                    xor      ecx, edx
0x1001a251 +1441  83 f8 40                 cmp      eax, 0x40   ; PF: PF_Modulated
0x1001a254 +1444  0f 43 d1                 cmovae   edx, ecx
0x1001a257 +1447  8b c6                    mov      eax, esi
0x1001a259 +1449  0b c1                    or       eax, ecx
0x1001a25b +144b  89 85 30 f7 ff ff        mov      dword ptr [ebp - 0x8d0], eax
0x1001a261 +1451  89 85 a4 f6 ff ff        mov      dword ptr [ebp - 0x95c], eax
0x1001a267 +1457  8b c7                    mov      eax, edi
0x1001a269 +1459  0b c2                    or       eax, edx
0x1001a26b +145b  89 85 00 f7 ff ff        mov      dword ptr [ebp - 0x900], eax
0x1001a271 +1461  89 85 a8 f6 ff ff        mov      dword ptr [ebp - 0x958], eax
0x1001a277 +1467  39 b5 30 f7 ff ff        cmp      dword ptr [ebp - 0x8d0], esi
0x1001a27d +146d  75 04                    jne      0x1001a283
0x1001a27f +146f  3b c7                    cmp      eax, edi
0x1001a281 +1471  74 17                    je       0x1001a29a
0x1001a283 +1473  8a 85 0b f7 ff ff        mov      al, byte ptr [ebp - 0x8f5]
0x1001a289 +1479  8b 8d f4 f6 ff ff        mov      ecx, dword ptr [ebp - 0x90c]
0x1001a28f +147f  88 44 0d ac              mov      byte ptr [ebp + ecx - 0x54], al
0x1001a293 +1483  41                       inc      ecx
0x1001a294 +1484  89 8d f4 f6 ff ff        mov      dword ptr [ebp - 0x90c], ecx
0x1001a29a +148a  0f 31                    rdtsc    
0x1001a29c +148c  29 05 ac fa 05 10        sub      dword ptr [0x1005faac], eax
0x1001a2a2 +1492  8b 95 38 f7 ff ff        mov      edx, dword ptr [ebp - 0x8c8]
0x1001a2a8 +1498  83 c2 14                 add      edx, 0x14
0x1001a2ab +149b  8b bd 2c f7 ff ff        mov      edi, dword ptr [ebp - 0x8d4]
0x1001a2b1 +14a1  8b c7                    mov      eax, edi
0x1001a2b3 +14a3  c1 e0 05                 shl      eax, 5
0x1001a2b6 +14a6  8d b5 ac f7 ff ff        lea      esi, [ebp - 0x854]
0x1001a2bc +14ac  03 f0                    add      esi, eax
0x1001a2be +14ae  83 bd 14 f7 ff ff 00     cmp      dword ptr [ebp - 0x8ec], 0
0x1001a2c5 +14b5  74 14                    je       0x1001a2db
0x1001a2c7 +14b7  68 f0 6b 04 10           push     0x10046bf0
0x1001a2cc +14bc  52                       push     edx
0x1001a2cd +14bd  8d 8d 8c f7 ff ff        lea      ecx, [ebp - 0x874]
0x1001a2d3 +14c3  e8 88 75 fe ff           call     0x10001860   ; -> ??0FSpanBuffer@@QAE@ABV0@AAVFMemStack@@@Z
0x1001a2d8 +14c8  50                       push     eax
0x1001a2d9 +14c9  eb 01                    jmp      0x1001a2dc
0x1001a2db +14cb  52                       push     edx
0x1001a2dc +14cc  8b ce                    mov      ecx, esi
0x1001a2de +14ce  e8 cd 40 00 00           call     0x1001e3b0   ; -> ?MergeWith@FSpanBuffer@@QAEXABV1@@Z
0x1001a2e3 +14d3  8d 04 7f                 lea      eax, [edi + edi*2]
0x1001a2e6 +14d6  f3 0f 10 85 8c f6 ff ff  movss    xmm0, dword ptr [ebp - 0x974]
0x1001a2ee +14de  8b 8d 20 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8e0]
0x1001a2f4 +14e4  f3 0f 11 84 c1 08 01 00 00 movss    dword ptr [ecx + eax*8 + 0x108], xmm0
0x1001a2fd +14ed  0f 31                    rdtsc    
0x1001a2ff +14ef  83 c0 de                 add      eax, -0x22
0x1001a302 +14f2  03 05 ac fa 05 10        add      eax, dword ptr [0x1005faac]
0x1001a308 +14f8  a3 ac fa 05 10           mov      dword ptr [0x1005faac], eax
0x1001a30d +14fd  83 bd 14 f7 ff ff 00     cmp      dword ptr [ebp - 0x8ec], 0
0x1001a314 +1504  0f 84 d1 04 00 00        je       0x1001a7eb
0x1001a31a +150a  33 c0                    xor      eax, eax
0x1001a31c +150c  89 85 e8 f6 ff ff        mov      dword ptr [ebp - 0x918], eax
0x1001a322 +1512  eb 09                    jmp      0x1001a32d
0x1001a324 +1514  f6 c1 01                 test     cl, 1   ; PF: PF_Invisible
0x1001a327 +1517  0f 85 be 04 00 00        jne      0x1001a7eb
0x1001a32d +151d  a1 cc 15 06 10           mov      eax, dword ptr [0x100615cc]
0x1001a332 +1522  64 8b 0d 2c 00 00 00     mov      ecx, dword ptr fs:[0x2c]
0x1001a339 +1529  8b 0c 81                 mov      ecx, dword ptr [ecx + eax*4]
0x1001a33c +152c  a1 70 15 06 10           mov      eax, dword ptr [0x10061570]
0x1001a341 +1531  3b 81 04 00 00 00        cmp      eax, dword ptr [ecx + 4]
0x1001a347 +1537  0f 8f e5 06 00 00        jg       0x1001aa32
0x1001a34d +153d  33 ff                    xor      edi, edi
0x1001a34f +153f  89 bd c8 f6 ff ff        mov      dword ptr [ebp - 0x938], edi
0x1001a355 +1545  8b b5 48 f7 ff ff        mov      esi, dword ptr [ebp - 0x8b8]
0x1001a35b +154b  39 7e 30                 cmp      dword ptr [esi + 0x30], edi
0x1001a35e +154e  0f 84 be 00 00 00        je       0x1001a422
0x1001a364 +1554  8b 85 fc f6 ff ff        mov      eax, dword ptr [ebp - 0x904]
0x1001a36a +155a  8b f0                    mov      esi, eax
0x1001a36c +155c  89 b5 80 f6 ff ff        mov      dword ptr [ebp - 0x980], esi
0x1001a372 +1562  8b 95 3c f7 ff ff        mov      edx, dword ptr [ebp - 0x8c4]
0x1001a378 +1568  8d 4a ff                 lea      ecx, [edx - 1]
0x1001a37b +156b  8d 0c 88                 lea      ecx, [eax + ecx*4]
0x1001a37e +156e  66 90                    nop      
0x1001a380 +1570  8d 04 90                 lea      eax, [eax + edx*4]
0x1001a383 +1573  3b f0                    cmp      esi, eax
0x1001a385 +1575  0f 83 9f 00 00 00        jae      0x1001a42a
0x1001a38b +157b  8b 01                    mov      eax, dword ptr [ecx]
0x1001a38d +157d  83 78 18 ff              cmp      dword ptr [eax + 0x18], -1
0x1001a391 +1581  74 79                    je       0x1001a40c
0x1001a393 +1583  50                       push     eax
0x1001a394 +1584  8d 85 00 f6 ff ff        lea      eax, [ebp - 0xa00]
0x1001a39a +158a  50                       push     eax
0x1001a39b +158b  8b 0e                    mov      ecx, dword ptr [esi]
0x1001a39d +158d  ff 15 60 42 03 10        call     dword ptr [0x10034260]   ; -> Core.dll!??TFVector@@QBE?AV0@ABV0@@Z
0x1001a3a3 +1593  8d 0c 7f                 lea      ecx, [edi + edi*2]
0x1001a3a6 +1596  8d 0c 8d f0 13 06 10     lea      ecx, [ecx*4 + 0x100613f0]
0x1001a3ad +159d  f3 0f 10 08              movss    xmm1, dword ptr [eax]
0x1001a3b1 +15a1  f3 0f 11 09              movss    dword ptr [ecx], xmm1
0x1001a3b5 +15a5  f3 0f 10 50 04           movss    xmm2, dword ptr [eax + 4]
0x1001a3ba +15aa  f3 0f 11 51 04           movss    dword ptr [ecx + 4], xmm2
0x1001a3bf +15af  f3 0f 10 40 08           movss    xmm0, dword ptr [eax + 8]
0x1001a3c4 +15b4  f3 0f 11 41 08           movss    dword ptr [ecx + 8], xmm0
0x1001a3c9 +15b9  f3 0f 59 d2              mulss    xmm2, xmm2
0x1001a3cd +15bd  f3 0f 59 c9              mulss    xmm1, xmm1
0x1001a3d1 +15c1  f3 0f 58 d1              addss    xmm2, xmm1
0x1001a3d5 +15c5  f3 0f 59 c0              mulss    xmm0, xmm0
0x1001a3d9 +15c9  f3 0f 58 d0              addss    xmm2, xmm0
0x1001a3dd +15cd  f3 0f 11 95 2c f7 ff ff  movss    dword ptr [ebp - 0x8d4], xmm2
0x1001a3e5 +15d5  0f 28 c2                 movaps   xmm0, xmm2
0x1001a3e8 +15d8  f3 0f 52 c0              rsqrtss  xmm0, xmm0
0x1001a3ec +15dc  51                       push     ecx
0x1001a3ed +15dd  f3 0f 11 04 24           movss    dword ptr [esp], xmm0
0x1001a3f2 +15e2  8d 85 f4 f5 ff ff        lea      eax, [ebp - 0xa0c]
0x1001a3f8 +15e8  50                       push     eax
0x1001a3f9 +15e9  ff 15 68 42 03 10        call     dword ptr [0x10034268]   ; -> Core.dll!??XFVector@@QAE?AV0@M@Z
0x1001a3ff +15ef  47                       inc      edi
0x1001a400 +15f0  89 bd c8 f6 ff ff        mov      dword ptr [ebp - 0x938], edi
0x1001a406 +15f6  8b 95 3c f7 ff ff        mov      edx, dword ptr [ebp - 0x8c4]
0x1001a40c +15fc  8b ce                    mov      ecx, esi
0x1001a40e +15fe  83 c6 04                 add      esi, 4
0x1001a411 +1601  89 b5 80 f6 ff ff        mov      dword ptr [ebp - 0x980], esi
0x1001a417 +1607  8b 85 fc f6 ff ff        mov      eax, dword ptr [ebp - 0x904]
0x1001a41d +160d  e9 5e ff ff ff           jmp      0x1001a380
0x1001a422 +1612  8b 95 3c f7 ff ff        mov      edx, dword ptr [ebp - 0x8c4]
0x1001a428 +1618  eb 06                    jmp      0x1001a430
0x1001a42a +161a  8b b5 48 f7 ff ff        mov      esi, dword ptr [ebp - 0x8b8]
0x1001a430 +1620  8b bd e8 f6 ff ff        mov      edi, dword ptr [ebp - 0x918]
0x1001a436 +1626  85 ff                    test     edi, edi
0x1001a438 +1628  0f 85 e3 01 00 00        jne      0x1001a621
0x1001a43e +162e  8b 85 34 f7 ff ff        mov      eax, dword ptr [ebp - 0x8cc]
0x1001a444 +1634  8b bd 38 f7 ff ff        mov      edi, dword ptr [ebp - 0x8c8]
0x1001a44a +163a  89 07                    mov      dword ptr [edi], eax
0x1001a44c +163c  8b 85 24 f7 ff ff        mov      eax, dword ptr [ebp - 0x8dc]
0x1001a452 +1642  8b b5 44 f7 ff ff        mov      esi, dword ptr [ebp - 0x8bc]
0x1001a458 +1648  0f b6 44 30 34           movzx    eax, byte ptr [eax + esi + 0x34]
0x1001a45d +164d  89 47 08                 mov      dword ptr [edi + 8], eax
0x1001a460 +1650  50                       push     eax
0x1001a461 +1651  8b 85 4c f7 ff ff        mov      eax, dword ptr [ebp - 0x8b4]
0x1001a467 +1657  8b 48 04                 mov      ecx, dword ptr [eax + 4]
0x1001a46a +165a  ff 15 8c 43 03 10        call     dword ptr [0x1003438c]   ; -> Engine.dll!?GetZoneActor@ULevel@@QAEPAVAZoneInfo@@H@Z
0x1001a470 +1660  89 47 34                 mov      dword ptr [edi + 0x34], eax
0x1001a473 +1663  8b 46 1c                 mov      eax, dword ptr [esi + 0x1c]
0x1001a476 +1666  89 47 04                 mov      dword ptr [edi + 4], eax
0x1001a479 +1669  8b 85 40 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c0]
0x1001a47f +166f  89 47 10                 mov      dword ptr [edi + 0x10], eax
0x1001a482 +1672  8b 85 f0 f6 ff ff        mov      eax, dword ptr [ebp - 0x910]
0x1001a488 +1678  8b 8d 4c f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b4]
0x1001a48e +167e  8b 84 81 98 00 00 00     mov      eax, dword ptr [ecx + eax*4 + 0x98]
0x1001a495 +1685  89 47 38                 mov      dword ptr [edi + 0x38], eax
0x1001a498 +1688  8b 46 1c                 mov      eax, dword ptr [esi + 0x1c]
0x1001a49b +168b  8b 8d b8 f6 ff ff        mov      ecx, dword ptr [ebp - 0x948]
0x1001a4a1 +1691  8b 04 81                 mov      eax, dword ptr [ecx + eax*4]
0x1001a4a4 +1694  89 47 3c                 mov      dword ptr [edi + 0x3c], eax
0x1001a4a7 +1697  8b 46 1c                 mov      eax, dword ptr [esi + 0x1c]
0x1001a4aa +169a  89 3c 81                 mov      dword ptr [ecx + eax*4], edi
0x1001a4ad +169d  c7 47 40 00 00 00 00     mov      dword ptr [edi + 0x40], 0
0x1001a4b4 +16a4  8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x1001a4ba +16aa  8b 70 30                 mov      esi, dword ptr [eax + 0x30]
0x1001a4bd +16ad  8b bd c8 f6 ff ff        mov      edi, dword ptr [ebp - 0x938]
0x1001a4c3 +16b3  85 f6                    test     esi, esi
0x1001a4c5 +16b5  74 55                    je       0x1001a51c
0x1001a4c7 +16b7  57                       push     edi
0x1001a4c8 +16b8  68 f0 13 06 10           push     0x100613f0
0x1001a4cd +16bd  56                       push     esi
0x1001a4ce +16be  e8 3d 18 00 00           call     0x1001bd10   ; -> sub_1bd10
0x1001a4d3 +16c3  83 c4 0c                 add      esp, 0xc
0x1001a4d6 +16c6  85 c0                    test     eax, eax
0x1001a4d8 +16c8  74 3d                    je       0x1001a517
0x1001a4da +16ca  6a 10                    push     0x10   ; PF: PF_Environment
0x1001a4dc +16cc  6a 08                    push     8   ; PF: PF_NotSolid
0x1001a4de +16ce  b9 f0 6b 04 10           mov      ecx, 0x10046bf0
0x1001a4e3 +16d3  ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x1001a4e9 +16d9  85 c0                    test     eax, eax
0x1001a4eb +16db  74 1f                    je       0x1001a50c
0x1001a4ed +16dd  8b 8d 38 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c8]
0x1001a4f3 +16e3  8b 51 40                 mov      edx, dword ptr [ecx + 0x40]
0x1001a4f6 +16e6  8b 4e 0c                 mov      ecx, dword ptr [esi + 0xc]
0x1001a4f9 +16e9  89 08                    mov      dword ptr [eax], ecx
0x1001a4fb +16eb  89 50 04                 mov      dword ptr [eax + 4], edx
0x1001a4fe +16ee  8b 8d 38 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c8]
0x1001a504 +16f4  89 41 40                 mov      dword ptr [ecx + 0x40], eax
0x1001a507 +16f7  8b 76 10                 mov      esi, dword ptr [esi + 0x10]
0x1001a50a +16fa  eb b7                    jmp      0x1001a4c3
0x1001a50c +16fc  33 c0                    xor      eax, eax
0x1001a50e +16fe  8b 8d 38 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c8]
0x1001a514 +1704  89 41 40                 mov      dword ptr [ecx + 0x40], eax
0x1001a517 +1707  8b 76 10                 mov      esi, dword ptr [esi + 0x10]
0x1001a51a +170a  eb a7                    jmp      0x1001a4c3
0x1001a51c +170c  8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x1001a522 +1712  83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x1001a526 +1716  75 5e                    jne      0x1001a586
0x1001a528 +1718  6a 10                    push     0x10   ; PF: PF_Environment
0x1001a52a +171a  8b b5 3c f7 ff ff        mov      esi, dword ptr [ebp - 0x8c4]
0x1001a530 +1720  8d 04 b5 10 00 00 00     lea      eax, [esi*4 + 0x10]
0x1001a537 +1727  50                       push     eax
0x1001a538 +1728  b9 f0 6b 04 10           mov      ecx, 0x10046bf0
0x1001a53d +172d  ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x1001a543 +1733  8b d0                    mov      edx, eax
0x1001a545 +1735  c7 02 00 00 00 00        mov      dword ptr [edx], 0
0x1001a54b +173b  8b 85 34 f7 ff ff        mov      eax, dword ptr [ebp - 0x8cc]
0x1001a551 +1741  89 42 04                 mov      dword ptr [edx + 4], eax
0x1001a554 +1744  8b bd 38 f7 ff ff        mov      edi, dword ptr [ebp - 0x8c8]
0x1001a55a +174a  89 57 44                 mov      dword ptr [edi + 0x44], edx
0x1001a55d +174d  89 72 0c                 mov      dword ptr [edx + 0xc], esi
0x1001a560 +1750  33 c9                    xor      ecx, ecx
0x1001a562 +1752  89 8d 7c f6 ff ff        mov      dword ptr [ebp - 0x984], ecx
0x1001a568 +1758  3b ce                    cmp      ecx, esi
0x1001a56a +175a  7d 10                    jge      0x1001a57c
0x1001a56c +175c  8b 85 fc f6 ff ff        mov      eax, dword ptr [ebp - 0x904]
0x1001a572 +1762  8b 04 88                 mov      eax, dword ptr [eax + ecx*4]
0x1001a575 +1765  89 44 8a 10              mov      dword ptr [edx + ecx*4 + 0x10], eax
0x1001a579 +1769  41                       inc      ecx
0x1001a57a +176a  eb e6                    jmp      0x1001a562
0x1001a57c +176c  8d 4f 14                 lea      ecx, [edi + 0x14]
0x1001a57f +176f  e8 dc 40 00 00           call     0x1001e660   ; -> ?Release@FSpanBuffer@@QAEXXZ
0x1001a584 +1774  eb 06                    jmp      0x1001a58c
0x1001a586 +1776  8b bd 38 f7 ff ff        mov      edi, dword ptr [ebp - 0x8c8]
0x1001a58c +177c  8b 47 34                 mov      eax, dword ptr [edi + 0x34]
0x1001a58f +177f  0f b6 88 90 00 00 00     movzx    ecx, byte ptr [eax + 0x90]
0x1001a596 +1786  c1 e1 1a                 shl      ecx, 0x1a
0x1001a599 +1789  89 4f 0c                 mov      dword ptr [edi + 0xc], ecx
0x1001a59c +178c  8b b5 e0 f6 ff ff        mov      esi, dword ptr [ebp - 0x920]
0x1001a5a2 +1792  8b 06                    mov      eax, dword ptr [esi]
0x1001a5a4 +1794  85 c0                    test     eax, eax
0x1001a5a6 +1796  74 3f                    je       0x1001a5e7
0x1001a5a8 +1798  8b 50 04                 mov      edx, dword ptr [eax + 4]
0x1001a5ab +179b  03 d1                    add      edx, ecx
0x1001a5ad +179d  89 57 0c                 mov      dword ptr [edi + 0xc], edx
0x1001a5b0 +17a0  8b 06                    mov      eax, dword ptr [esi]
0x1001a5b2 +17a2  8b 8d 0c f7 ff ff        mov      ecx, dword ptr [ebp - 0x8f4]
0x1001a5b8 +17a8  83 79 68 00              cmp      dword ptr [ecx + 0x68], 0
0x1001a5bc +17ac  74 17                    je       0x1001a5d5
0x1001a5be +17ae  0f b6 48 31              movzx    ecx, byte ptr [eax + 0x31]
0x1001a5c2 +17b2  c1 e1 05                 shl      ecx, 5
0x1001a5c5 +17b5  0f b6 40 30              movzx    eax, byte ptr [eax + 0x30]
0x1001a5c9 +17b9  0b c8                    or       ecx, eax
0x1001a5cb +17bb  c1 e1 0c                 shl      ecx, 0xc
0x1001a5ce +17be  03 ca                    add      ecx, edx
0x1001a5d0 +17c0  89 4f 0c                 mov      dword ptr [edi + 0xc], ecx
0x1001a5d3 +17c3  eb 12                    jmp      0x1001a5e7
0x1001a5d5 +17c5  8b 40 2c                 mov      eax, dword ptr [eax + 0x2c]
0x1001a5d8 +17c8  85 c0                    test     eax, eax
0x1001a5da +17ca  74 0b                    je       0x1001a5e7
0x1001a5dc +17cc  8b 40 04                 mov      eax, dword ptr [eax + 4]
0x1001a5df +17cf  c1 e0 0c                 shl      eax, 0xc
0x1001a5e2 +17d2  03 c2                    add      eax, edx
0x1001a5e4 +17d4  89 47 0c                 mov      dword ptr [edi + 0xc], eax
0x1001a5e7 +17d7  8b 85 f0 f6 ff ff        mov      eax, dword ptr [ebp - 0x910]
0x1001a5ed +17dd  8b 8d 4c f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b4]
0x1001a5f3 +17e3  89 bc 81 98 00 00 00     mov      dword ptr [ecx + eax*4 + 0x98], edi
0x1001a5fa +17ea  6a 10                    push     0x10   ; PF: PF_Environment
0x1001a5fc +17ec  6a 4c                    push     0x4c   ; PF: PF_Translucent|PF_NotSolid|PF_Modulated
0x1001a5fe +17ee  b9 f0 6b 04 10           mov      ecx, 0x10046bf0
0x1001a603 +17f3  ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x1001a609 +17f9  89 85 38 f7 ff ff        mov      dword ptr [ebp - 0x8c8], eax
0x1001a60f +17ff  8b 95 48 f7 ff ff        mov      edx, dword ptr [ebp - 0x8b8]
0x1001a615 +1805  8b 4a 78                 mov      ecx, dword ptr [edx + 0x78]
0x1001a618 +1808  41                       inc      ecx
0x1001a619 +1809  89 4a 78                 mov      dword ptr [edx + 0x78], ecx
0x1001a61c +180c  e9 05 01 00 00           jmp      0x1001a726
0x1001a621 +1811  8b 85 0c f7 ff ff        mov      eax, dword ptr [ebp - 0x8f4]
0x1001a627 +1817  83 78 48 00              cmp      dword ptr [eax + 0x48], 0
0x1001a62b +181b  75 59                    jne      0x1001a686
0x1001a62d +181d  6a 10                    push     0x10   ; PF: PF_Environment
0x1001a62f +181f  8d 04 95 10 00 00 00     lea      eax, [edx*4 + 0x10]
0x1001a636 +1826  50                       push     eax
0x1001a637 +1827  b9 f0 6b 04 10           mov      ecx, 0x10046bf0
0x1001a63c +182c  ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x1001a642 +1832  8b d0                    mov      edx, eax
0x1001a644 +1834  8b 4f 44                 mov      ecx, dword ptr [edi + 0x44]
0x1001a647 +1837  89 0a                    mov      dword ptr [edx], ecx
0x1001a649 +1839  8b 85 34 f7 ff ff        mov      eax, dword ptr [ebp - 0x8cc]
0x1001a64f +183f  89 42 04                 mov      dword ptr [edx + 4], eax
0x1001a652 +1842  89 57 44                 mov      dword ptr [edi + 0x44], edx
0x1001a655 +1845  8b 85 3c f7 ff ff        mov      eax, dword ptr [ebp - 0x8c4]
0x1001a65b +184b  89 42 0c                 mov      dword ptr [edx + 0xc], eax
0x1001a65e +184e  33 c9                    xor      ecx, ecx
0x1001a660 +1850  89 8d 78 f6 ff ff        mov      dword ptr [ebp - 0x988], ecx
0x1001a666 +1856  3b c8                    cmp      ecx, eax
0x1001a668 +1858  7d 46                    jge      0x1001a6b0
0x1001a66a +185a  8b 85 fc f6 ff ff        mov      eax, dword ptr [ebp - 0x904]
0x1001a670 +1860  8b 04 88                 mov      eax, dword ptr [eax + ecx*4]
0x1001a673 +1863  89 44 8a 10              mov      dword ptr [edx + ecx*4 + 0x10], eax
0x1001a677 +1867  41                       inc      ecx
0x1001a678 +1868  89 8d 78 f6 ff ff        mov      dword ptr [ebp - 0x988], ecx
0x1001a67e +186e  8b 85 3c f7 ff ff        mov      eax, dword ptr [ebp - 0x8c4]
0x1001a684 +1874  eb e0                    jmp      0x1001a666
0x1001a686 +1876  0f 31                    rdtsc    
0x1001a688 +1878  29 05 ac fa 05 10        sub      dword ptr [0x1005faac], eax
0x1001a68e +187e  8b 85 38 f7 ff ff        mov      eax, dword ptr [ebp - 0x8c8]
0x1001a694 +1884  83 c0 14                 add      eax, 0x14
0x1001a697 +1887  50                       push     eax
0x1001a698 +1888  8d 4f 14                 lea      ecx, [edi + 0x14]
0x1001a69b +188b  e8 10 3d 00 00           call     0x1001e3b0   ; -> ?MergeWith@FSpanBuffer@@QAEXABV1@@Z
0x1001a6a0 +1890  0f 31                    rdtsc    
0x1001a6a2 +1892  83 c0 de                 add      eax, -0x22
0x1001a6a5 +1895  03 05 ac fa 05 10        add      eax, dword ptr [0x1005faac]
0x1001a6ab +189b  a3 ac fa 05 10           mov      dword ptr [0x1005faac], eax
0x1001a6b0 +18a0  8b 8d 38 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8c8]
0x1001a6b6 +18a6  8d 49 14                 lea      ecx, [ecx + 0x14]
0x1001a6b9 +18a9  e8 a2 3f 00 00           call     0x1001e660   ; -> ?Release@FSpanBuffer@@QAEXXZ
0x1001a6be +18ae  8b 76 30                 mov      esi, dword ptr [esi + 0x30]
0x1001a6c1 +18b1  85 f6                    test     esi, esi
0x1001a6c3 +18b3  74 5b                    je       0x1001a720
0x1001a6c5 +18b5  8b 4f 40                 mov      ecx, dword ptr [edi + 0x40]
0x1001a6c8 +18b8  85 c9                    test     ecx, ecx
0x1001a6ca +18ba  74 0c                    je       0x1001a6d8
0x1001a6cc +18bc  8b 01                    mov      eax, dword ptr [ecx]
0x1001a6ce +18be  3b 46 0c                 cmp      eax, dword ptr [esi + 0xc]
0x1001a6d1 +18c1  74 48                    je       0x1001a71b
0x1001a6d3 +18c3  8b 49 04                 mov      ecx, dword ptr [ecx + 4]
0x1001a6d6 +18c6  eb f0                    jmp      0x1001a6c8
0x1001a6d8 +18c8  ff b5 c8 f6 ff ff        push     dword ptr [ebp - 0x938]
0x1001a6de +18ce  68 f0 13 06 10           push     0x100613f0
0x1001a6e3 +18d3  56                       push     esi
0x1001a6e4 +18d4  e8 27 16 00 00           call     0x1001bd10   ; -> sub_1bd10
0x1001a6e9 +18d9  83 c4 0c                 add      esp, 0xc
0x1001a6ec +18dc  85 c0                    test     eax, eax
0x1001a6ee +18de  74 2b                    je       0x1001a71b
0x1001a6f0 +18e0  6a 10                    push     0x10   ; PF: PF_Environment
0x1001a6f2 +18e2  6a 08                    push     8   ; PF: PF_NotSolid
0x1001a6f4 +18e4  b9 f0 6b 04 10           mov      ecx, 0x10046bf0
0x1001a6f9 +18e9  ff 15 20 41 03 10        call     dword ptr [0x10034120]   ; -> Core.dll!?PushBytes@FMemStack@@QAEPAEHH@Z
0x1001a6ff +18ef  85 c0                    test     eax, eax
0x1001a701 +18f1  74 13                    je       0x1001a716
0x1001a703 +18f3  8b 57 40                 mov      edx, dword ptr [edi + 0x40]
0x1001a706 +18f6  8b 4e 0c                 mov      ecx, dword ptr [esi + 0xc]
0x1001a709 +18f9  89 08                    mov      dword ptr [eax], ecx
0x1001a70b +18fb  89 50 04                 mov      dword ptr [eax + 4], edx
0x1001a70e +18fe  89 47 40                 mov      dword ptr [edi + 0x40], eax
0x1001a711 +1901  8b 76 10                 mov      esi, dword ptr [esi + 0x10]
0x1001a714 +1904  eb ab                    jmp      0x1001a6c1
0x1001a716 +1906  33 c0                    xor      eax, eax
0x1001a718 +1908  89 47 40                 mov      dword ptr [edi + 0x40], eax
0x1001a71b +190b  8b 76 10                 mov      esi, dword ptr [esi + 0x10]
0x1001a71e +190e  eb a1                    jmp      0x1001a6c1
0x1001a720 +1910  8b 95 48 f7 ff ff        mov      edx, dword ptr [ebp - 0x8b8]
0x1001a726 +1916  8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x1001a72c +191c  80 60 37 f7              and      byte ptr [eax + 0x37], 0xf7   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_Environment|PF_Semisolid|PF_Modulated|PF_FakeBackdrop
0x1001a730 +1920  8b 42 74                 mov      eax, dword ptr [edx + 0x74]
0x1001a733 +1923  40                       inc      eax
0x1001a734 +1924  89 42 74                 mov      dword ptr [edx + 0x74], eax
0x1001a737 +1927  8b 85 e4 f6 ff ff        mov      eax, dword ptr [ebp - 0x91c]
0x1001a73d +192d  83 78 08 00              cmp      dword ptr [eax + 8], 0
0x1001a741 +1931  0f 8f a4 00 00 00        jg       0x1001a7eb
0x1001a747 +1937  33 d2                    xor      edx, edx
0x1001a749 +1939  89 95 6c f6 ff ff        mov      dword ptr [ebp - 0x994], edx
0x1001a74f +193f  33 c9                    xor      ecx, ecx
0x1001a751 +1941  89 8d 74 f6 ff ff        mov      dword ptr [ebp - 0x98c], ecx
0x1001a757 +1947  3b 8d f4 f6 ff ff        cmp      ecx, dword ptr [ebp - 0x90c]
0x1001a75d +194d  7d 37                    jge      0x1001a796
0x1001a75f +194f  8d 75 ac                 lea      esi, [ebp - 0x54]
0x1001a762 +1952  03 f1                    add      esi, ecx
0x1001a764 +1954  8a 06                    mov      al, byte ptr [esi]
0x1001a766 +1956  88 44 15 ac              mov      byte ptr [ebp + edx - 0x54], al
0x1001a76a +195a  41                       inc      ecx
0x1001a76b +195b  89 8d 74 f6 ff ff        mov      dword ptr [ebp - 0x98c], ecx
0x1001a771 +1961  8b 85 ac f6 ff ff        mov      eax, dword ptr [ebp - 0x954]
0x1001a777 +1967  38 06                    cmp      byte ptr [esi], al
0x1001a779 +1969  74 0f                    je       0x1001a78a
0x1001a77b +196b  b8 01 00 00 00           mov      eax, 1   ; PF: PF_Invisible
0x1001a780 +1970  03 d0                    add      edx, eax
0x1001a782 +1972  89 95 6c f6 ff ff        mov      dword ptr [ebp - 0x994], edx
0x1001a788 +1978  eb cd                    jmp      0x1001a757
0x1001a78a +197a  33 c0                    xor      eax, eax
0x1001a78c +197c  03 d0                    add      edx, eax
0x1001a78e +197e  89 95 6c f6 ff ff        mov      dword ptr [ebp - 0x994], edx
0x1001a794 +1984  eb c1                    jmp      0x1001a757
0x1001a796 +1986  89 95 f4 f6 ff ff        mov      dword ptr [ebp - 0x90c], edx
0x1001a79c +198c  8b b5 dc f6 ff ff        mov      esi, dword ptr [ebp - 0x924]
0x1001a7a2 +1992  33 c0                    xor      eax, eax
0x1001a7a4 +1994  33 c9                    xor      ecx, ecx
0x1001a7a6 +1996  0f ab f0                 bts      eax, esi
0x1001a7a9 +1999  83 fe 20                 cmp      esi, 0x20   ; PF: PF_Semisolid
0x1001a7ac +199c  0f 43 c8                 cmovae   ecx, eax
0x1001a7af +199f  33 c1                    xor      eax, ecx
0x1001a7b1 +19a1  83 fe 40                 cmp      esi, 0x40   ; PF: PF_Modulated
0x1001a7b4 +19a4  0f 43 c8                 cmovae   ecx, eax
0x1001a7b7 +19a7  f7 d0                    not      eax
0x1001a7b9 +19a9  f7 d1                    not      ecx
0x1001a7bb +19ab  8b b5 30 f7 ff ff        mov      esi, dword ptr [ebp - 0x8d0]
0x1001a7c1 +19b1  23 f0                    and      esi, eax
0x1001a7c3 +19b3  89 b5 30 f7 ff ff        mov      dword ptr [ebp - 0x8d0], esi
0x1001a7c9 +19b9  89 b5 a4 f6 ff ff        mov      dword ptr [ebp - 0x95c], esi
0x1001a7cf +19bf  8b 85 00 f7 ff ff        mov      eax, dword ptr [ebp - 0x900]
0x1001a7d5 +19c5  23 c1                    and      eax, ecx
0x1001a7d7 +19c7  89 85 00 f7 ff ff        mov      dword ptr [ebp - 0x900], eax
0x1001a7dd +19cd  89 85 a8 f6 ff ff        mov      dword ptr [ebp - 0x958], eax
0x1001a7e3 +19d3  85 d2                    test     edx, edx
0x1001a7e5 +19d5  0f 84 0b ec ff ff        je       0x100193f6
0x1001a7eb +19db  8b 85 44 f7 ff ff        mov      eax, dword ptr [ebp - 0x8bc]
0x1001a7f1 +19e1  8b 70 28                 mov      esi, dword ptr [eax + 0x28]
0x1001a7f4 +19e4  89 b5 34 f7 ff ff        mov      dword ptr [ebp - 0x8cc], esi
0x1001a7fa +19ea  83 fe ff                 cmp      esi, -1
0x1001a7fd +19ed  0f 85 31 01 00 00        jne      0x1001a934
0x1001a803 +19f3  8b b5 68 f6 ff ff        mov      esi, dword ptr [ebp - 0x998]
0x1001a809 +19f9  03 35 2c fa 05 10        add      esi, dword ptr [0x1005fa2c]
0x1001a80f +19ff  89 b5 b4 f6 ff ff        mov      dword ptr [ebp - 0x94c], esi
0x1001a815 +1a05  8d 85 98 f6 ff ff        lea      eax, [ebp - 0x968]
0x1001a81b +1a0b  50                       push     eax
0x1001a81c +1a0c  8b ce                    mov      ecx, esi
0x1001a81e +1a0e  ff 15 e4 40 03 10        call     dword ptr [0x100340e4]   ; -> Core.dll!?PlaneDot@FPlane@@QBEMABVFVector@@@Z
0x1001a824 +1a14  d9 9d 3c f7 ff ff        fstp     dword ptr [ebp - 0x8c4]
0x1001a82a +1a1a  f3 0f 10 85 3c f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8c4]
0x1001a832 +1a22  33 c9                    xor      ecx, ecx
0x1001a834 +1a24  0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x1001a83b +1a2b  0f 97 c1                 seta     cl
0x1001a83e +1a2e  89 8d 14 f7 ff ff        mov      dword ptr [ebp - 0x8ec], ecx
0x1001a844 +1a34  89 8d b0 f6 ff ff        mov      dword ptr [ebp - 0x950], ecx
0x1001a84a +1a3a  8b c6                    mov      eax, esi
0x1001a84c +1a3c  2b c1                    sub      eax, ecx
0x1001a84e +1a3e  0f b6 40 35              movzx    eax, byte ptr [eax + 0x35]
0x1001a852 +1a42  33 ff                    xor      edi, edi
0x1001a854 +1a44  80 bd 53 f7 ff ff 00     cmp      byte ptr [ebp - 0x8ad], 0
0x1001a85b +1a4b  0f 45 f8                 cmovne   edi, eax
0x1001a85e +1a4e  83 bd c4 f6 ff ff 00     cmp      dword ptr [ebp - 0x93c], 0
0x1001a865 +1a55  74 2d                    je       0x1001a894
0x1001a867 +1a57  b8 0f 00 00 00           mov      eax, 0xf   ; PF: PF_Invisible|PF_Masked|PF_Translucent|PF_NotSolid
0x1001a86c +1a5c  2b c1                    sub      eax, ecx
0x1001a86e +1a5e  8b 04 86                 mov      eax, dword ptr [esi + eax*4]
0x1001a871 +1a61  83 f8 ff                 cmp      eax, -1
0x1001a874 +1a64  74 1e                    je       0x1001a894
0x1001a876 +1a66  50                       push     eax
0x1001a877 +1a67  ff b5 20 f7 ff ff        push     dword ptr [ebp - 0x8e0]
0x1001a87d +1a6d  ff b5 4c f7 ff ff        push     dword ptr [ebp - 0x8b4]
0x1001a883 +1a73  8b 8d 48 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8b8]
0x1001a889 +1a79  e8 62 e3 ff ff           call     0x10018bf0   ; -> ?LeafVolumetricLighting@URender@@QAEXPAUFSceneNode@@PAVUModel@@H@Z
0x1001a88e +1a7e  8b 8d 14 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8ec]
0x1001a894 +1a84  c1 e7 05                 shl      edi, 5
0x1001a897 +1a87  83 bc 3d b4 f7 ff ff 00  cmp      dword ptr [ebp + edi - 0x84c], 0
0x1001a89f +1a8f  74 73                    je       0x1001a914
0x1001a8a1 +1a91  6a 00                    push     0
0x1001a8a3 +1a93  ff b5 18 f7 ff ff        push     dword ptr [ebp - 0x8e8]
0x1001a8a9 +1a99  b8 01 00 00 00           mov      eax, 1   ; PF: PF_Invisible
0x1001a8ae +1a9e  2b c1                    sub      eax, ecx
0x1001a8b0 +1aa0  50                       push     eax
0x1001a8b1 +1aa1  8b ce                    mov      ecx, esi
0x1001a8b3 +1aa3  e8 68 92 ff ff           call     0x10013b20   ; -> sub_13b20
0x1001a8b8 +1aa8  85 c0                    test     eax, eax
0x1001a8ba +1aaa  75 0c                    jne      0x1001a8c8
0x1001a8bc +1aac  8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x1001a8c2 +1ab2  83 78 34 00              cmp      dword ptr [eax + 0x34], 0
0x1001a8c6 +1ab6  74 4c                    je       0x1001a914
0x1001a8c8 +1ab8  8b 85 14 f7 ff ff        mov      eax, dword ptr [ebp - 0x8ec]
0x1001a8ce +1abe  8b 8d 28 f7 ff ff        mov      ecx, dword ptr [ebp - 0x8d8]
0x1001a8d4 +1ac4  8d 0c 48                 lea      ecx, [eax + ecx*2]
0x1001a8d7 +1ac7  a1 04 fa 05 10           mov      eax, dword ptr [0x1005fa04]   ; data ?DynamicsCache@URender@@2PAUFDynamicsCache@1@A
0x1001a8dc +1acc  8b 34 88                 mov      esi, dword ptr [eax + ecx*4]
0x1001a8df +1acf  90                       nop      
0x1001a8e0 +1ad0  85 f6                    test     esi, esi
0x1001a8e2 +1ad2  74 30                    je       0x1001a914
0x1001a8e4 +1ad4  8b 16                    mov      edx, dword ptr [esi]
0x1001a8e6 +1ad6  8b 85 48 f7 ff ff        mov      eax, dword ptr [ebp - 0x8b8]
0x1001a8ec +1adc  ff 70 30                 push     dword ptr [eax + 0x30]
0x1001a8ef +1adf  ff b5 28 f7 ff ff        push     dword ptr [ebp - 0x8d8]
0x1001a8f5 +1ae5  8d 85 ac f7 ff ff        lea      eax, [ebp - 0x854]
0x1001a8fb +1aeb  03 c7                    add      eax, edi
0x1001a8fd +1aed  50                       push     eax
0x1001a8fe +1aee  ff b5 4c f7 ff ff        push     dword ptr [ebp - 0x8b4]
0x1001a904 +1af4  ff b5 d4 f6 ff ff        push     dword ptr [ebp - 0x92c]
0x1001a90a +1afa  8b ce                    mov      ecx, esi
0x1001a90c +1afc  ff 52 04                 call     dword ptr [edx + 4]
0x1001a90f +1aff  8b 76 04                 mov      esi, dword ptr [esi + 4]
0x1001a912 +1b02  eb cc                    jmp      0x1001a8e0
0x1001a914 +1b04  8b 95 1c f7 ff ff        mov      edx, dword ptr [ebp - 0x8e4]
0x1001a91a +1b0a  8b 72 04                 mov      esi, dword ptr [edx + 4]
0x1001a91d +1b0d  89 b5 34 f7 ff ff        mov      dword ptr [ebp - 0x8cc], esi
0x1001a923 +1b13  83 fe ff                 cmp      esi, -1
0x1001a926 +1b16  0f 84 b9 ea ff ff        je       0x100193e5
0x1001a92c +1b1c  8b 42 08                 mov      eax, dword ptr [edx + 8]
0x1001a92f +1b1f  e9 a2 e9 ff ff           jmp      0x100192d6
0x1001a934 +1b24  8b c6                    mov      eax, esi
0x1001a936 +1b26  c1 e0 06                 shl      eax, 6
0x1001a939 +1b29  03 05 2c fa 05 10        add      eax, dword ptr [0x1005fa2c]
0x1001a93f +1b2f  89 85 44 f7 ff ff        mov      dword ptr [ebp - 0x8bc], eax
0x1001a945 +1b35  89 85 b4 f6 ff ff        mov      dword ptr [ebp - 0x94c], eax
0x1001a94b +1b3b  8d 8d 98 f6 ff ff        lea      ecx, [ebp - 0x968]
0x1001a951 +1b41  51                       push     ecx
0x1001a952 +1b42  8b c8                    mov      ecx, eax
0x1001a954 +1b44  ff 15 e4 40 03 10        call     dword ptr [0x100340e4]   ; -> Core.dll!?PlaneDot@FPlane@@QBEMABVFVector@@@Z
0x1001a95a +1b4a  d9 9d 3c f7 ff ff        fstp     dword ptr [ebp - 0x8c4]
0x1001a960 +1b50  33 c9                    xor      ecx, ecx
0x1001a962 +1b52  f3 0f 10 85 3c f7 ff ff  movss    xmm0, dword ptr [ebp - 0x8c4]
0x1001a96a +1b5a  0f 2f 05 3c 51 03 10     comiss   xmm0, dword ptr [0x1003513c]   ; [0x1003513c] f32=0.0
0x1001a971 +1b61  0f 97 c1                 seta     cl
0x1001a974 +1b64  89 8d 24 f7 ff ff        mov      dword ptr [ebp - 0x8dc], ecx
0x1001a97a +1b6a  89 8d b0 f6 ff ff        mov      dword ptr [ebp - 0x950], ecx
0x1001a980 +1b70  8b bd 44 f7 ff ff        mov      edi, dword ptr [ebp - 0x8bc]
0x1001a986 +1b76  e9 15 ef ff ff           jmp      0x100198a0
0x1001a98b +1b7b  0f 31                    rdtsc    
0x1001a98d +1b7d  83 c0 de                 add      eax, -0x22
0x1001a990 +1b80  03 05 a0 fa 05 10        add      eax, dword ptr [0x1005faa0]
0x1001a996 +1b86  a3 a0 fa 05 10           mov      dword ptr [0x1005faa0], eax
0x1001a99b +1b8b  9b                       wait     
0x1001a99c +1b8c  c7 45 fc ff ff ff ff     mov      dword ptr [ebp - 4], 0xffffffff
0x1001a9a3 +1b93  e9 8c e8 ff ff           jmp      0x10019234
0x1001a9a8 +1b98  8b 32                    mov      esi, dword ptr [edx]
0x1001a9aa +1b9a  89 b5 34 f7 ff ff        mov      dword ptr [ebp - 0x8cc], esi
0x1001a9b0 +1ba0  8b 42 0c                 mov      eax, dword ptr [edx + 0xc]
0x1001a9b3 +1ba3  8b 4a 10                 mov      ecx, dword ptr [edx + 0x10]
0x1001a9b6 +1ba6  e9 1d e9 ff ff           jmp      0x100192d8
0x1001a9bb +1bab  8b 85 24 f6 ff ff        mov      eax, dword ptr [ebp - 0x9dc]
0x1001a9c1 +1bb1  89 85 5c f6 ff ff        mov      dword ptr [ebp - 0x9a4], eax
0x1001a9c7 +1bb7  68 7c ea 03 10           push     0x1003ea7c
0x1001a9cc +1bbc  8d 85 5c f6 ff ff        lea      eax, [ebp - 0x9a4]
0x1001a9d2 +1bc2  50                       push     eax
0x1001a9d3 +1bc3  eb 3b                    jmp      0x1001aa10
0x1001a9d5 +1bc5  68 90 6c 03 10           push     0x10036c90
0x1001a9da +1bca  eb 22                    jmp      0x1001a9fe
0x1001a9dc +1bcc  8b 85 3c f6 ff ff        mov      eax, dword ptr [ebp - 0x9c4]
0x1001a9e2 +1bd2  89 85 70 f6 ff ff        mov      dword ptr [ebp - 0x990], eax
0x1001a9e8 +1bd8  68 7c ea 03 10           push     0x1003ea7c
0x1001a9ed +1bdd  8d 85 70 f6 ff ff        lea      eax, [ebp - 0x990]
0x1001a9f3 +1be3  50                       push     eax
0x1001a9f4 +1be4  e8 2b 8a 00 00           call     0x10023424   ; -> sub_23424
0x1001a9f9 +1be9  68 b8 6c 03 10           push     0x10036cb8
0x1001a9fe +1bee  68 88 46 03 10           push     0x10034688
0x1001aa03 +1bf3  ff 15 88 41 03 10        call     dword ptr [0x10034188]   ; -> Core.dll!?appUnwindf@@YAXPBGZZ
0x1001aa09 +1bf9  83 c4 08                 add      esp, 8
0x1001aa0c +1bfc  6a 00                    push     0
0x1001aa0e +1bfe  6a 00                    push     0
0x1001aa10 +1c00  e8 0f 8a 00 00           call     0x10023424   ; -> sub_23424
0x1001aa15 +1c05  8b 85 38 f6 ff ff        mov      eax, dword ptr [ebp - 0x9c8]
0x1001aa1b +1c0b  89 85 40 f6 ff ff        mov      dword ptr [ebp - 0x9c0], eax
0x1001aa21 +1c11  68 7c ea 03 10           push     0x1003ea7c
0x1001aa26 +1c16  8d 85 40 f6 ff ff        lea      eax, [ebp - 0x9c0]
0x1001aa2c +1c1c  50                       push     eax
0x1001aa2d +1c1d  e8 f2 89 00 00           call     0x10023424   ; -> sub_23424
0x1001aa32 +1c22  68 70 15 06 10           push     0x10061570
0x1001aa37 +1c27  e8 88 76 00 00           call     0x100220c4   ; -> sub_220c4
0x1001aa3c +1c2c  83 c4 04                 add      esp, 4
0x1001aa3f +1c2f  83 3d 70 15 06 10 ff     cmp      dword ptr [0x10061570], -1
0x1001aa46 +1c36  0f 85 01 f9 ff ff        jne      0x1001a34d
0x1001aa4c +1c3c  c6 45 fc 09              mov      byte ptr [ebp - 4], 9   ; PF: PF_Invisible|PF_NotSolid
0x1001aa50 +1c40  be 20 00 00 00           mov      esi, 0x20   ; PF: PF_Semisolid
0x1001aa55 +1c45  89 b5 88 f6 ff ff        mov      dword ptr [ebp - 0x978], esi
0x1001aa5b +1c4b  bf f0 13 06 10           mov      edi, 0x100613f0
0x1001aa60 +1c50  eb 00                    jmp      0x1001aa62
0x1001aa62 +1c52  89 bd 84 f6 ff ff        mov      dword ptr [ebp - 0x97c], edi
0x1001aa68 +1c58  8b c6                    mov      eax, esi
0x1001aa6a +1c5a  4e                       dec      esi
0x1001aa6b +1c5b  89 b5 88 f6 ff ff        mov      dword ptr [ebp - 0x978], esi
0x1001aa71 +1c61  85 c0                    test     eax, eax
0x1001aa73 +1c63  74 0d                    je       0x1001aa82
0x1001aa75 +1c65  8b cf                    mov      ecx, edi
0x1001aa77 +1c67  ff 15 f0 40 03 10        call     dword ptr [0x100340f0]   ; -> Core.dll!??0FVector@@QAE@XZ
0x1001aa7d +1c6d  83 c7 0c                 add      edi, 0xc
0x1001aa80 +1c70  eb e0                    jmp      0x1001aa62
0x1001aa82 +1c72  c6 45 fc 00              mov      byte ptr [ebp - 4], 0
0x1001aa86 +1c76  68 70 15 06 10           push     0x10061570
0x1001aa8b +1c7b  e8 ea 75 00 00           call     0x1002207a   ; -> sub_2207a
0x1001aa90 +1c80  83 c4 04                 add      esp, 4
0x1001aa93 +1c83  e9 b5 f8 ff ff           jmp      0x1001a34d
0x1001aa98 +1c88  cc                       int3     
0x1001aa99 +1c89  cc                       int3     
0x1001aa9a +1c8a  cc                       int3     
0x1001aa9b +1c8b  cc                       int3     
0x1001aa9c +1c8c  cc                       int3     
0x1001aa9d +1c8d  cc                       int3     
0x1001aa9e +1c8e  cc                       int3     
0x1001aa9f +1c8f  cc                       int3     

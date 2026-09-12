0x1001aaa0 +0     55                       push     ebp
0x1001aaa1 +1     8b ec                    mov      ebp, esp
0x1001aaa3 +3     6a ff                    push     -1
0x1001aaa5 +5     68 50 36 03 10           push     0x10033650
0x1001aaaa +a     64 a1 00 00 00 00        mov      eax, dword ptr fs:[0]
0x1001aab0 +10    50                       push     eax
0x1001aab1 +11    83 ec 1c                 sub      esp, 0x1c
0x1001aab4 +14    53                       push     ebx
0x1001aab5 +15    56                       push     esi
0x1001aab6 +16    57                       push     edi
0x1001aab7 +17    a1 3c 60 04 10           mov      eax, dword ptr [0x1004603c]   ; [0x1004603c] f32=-0.002943414729088545
0x1001aabc +1c    33 c5                    xor      eax, ebp
0x1001aabe +1e    50                       push     eax
0x1001aabf +1f    8d 45 f4                 lea      eax, [ebp - 0xc]
0x1001aac2 +22    64 a3 00 00 00 00        mov      dword ptr fs:[0], eax
0x1001aac8 +28    89 65 f0                 mov      dword ptr [ebp - 0x10], esp
0x1001aacb +2b    8b d9                    mov      ebx, ecx
0x1001aacd +2d    c7 45 fc 00 00 00 00     mov      dword ptr [ebp - 4], 0
0x1001aad4 +34    8b 7d 08                 mov      edi, dword ptr [ebp + 8]
0x1001aad7 +37    8b 37                    mov      esi, dword ptr [edi]
0x1001aad9 +39    8b 47 04                 mov      eax, dword ptr [edi + 4]
0x1001aadc +3c    89 45 08                 mov      dword ptr [ebp + 8], eax
0x1001aadf +3f    8b 88 98 00 00 00        mov      ecx, dword ptr [eax + 0x98]
0x1001aae5 +45    83 79 5c 00              cmp      dword ptr [ecx + 0x5c], 0
0x1001aae9 +49    7f 21                    jg       0x1001ab0c
0x1001aaeb +4b    68 46 09 00 00           push     0x946   ; PF: PF_Masked|PF_Translucent|PF_Modulated|PF_TwoSided|PF_NoSmooth
0x1001aaf0 +50    68 a0 6b 03 10           push     0x10036ba0
0x1001aaf5 +55    68 e8 6d 03 10           push     0x10036de8
0x1001aafa +5a    ff 15 84 41 03 10        call     dword ptr [0x10034184]   ; -> Core.dll!?appFailAssert@@YAXPBD0H@Z
0x1001ab00 +60    83 c4 0c                 add      esp, 0xc
0x1001ab03 +63    8b 4d 08                 mov      ecx, dword ptr [ebp + 8]
0x1001ab06 +66    8b 89 98 00 00 00        mov      ecx, dword ptr [ecx + 0x98]
0x1001ab0c +6c    83 3d fc f9 05 10 00     cmp      dword ptr [0x1005f9fc], 0   ; data ?SurfLights@URender@@2PAPAUFActorLink@@A
0x1001ab13 +73    74 0e                    je       0x1001ab23
0x1001ab15 +75    8b 81 9c 00 00 00        mov      eax, dword ptr [ecx + 0x9c]
0x1001ab1b +7b    3b 05 f4 f9 05 10        cmp      eax, dword ptr [0x1005f9f4]   ; data ?MaxSurfLights@URender@@2HA
0x1001ab21 +81    7e 50                    jle      0x1001ab73
0x1001ab23 +83    8b 81 9c 00 00 00        mov      eax, dword ptr [ecx + 0x9c]
0x1001ab29 +89    a3 f4 f9 05 10           mov      dword ptr [0x1005f9f4], eax   ; data ?MaxSurfLights@URender@@2HA
0x1001ab2e +8e    50                       push     eax
0x1001ab2f +8f    b9 00 08 06 10           mov      ecx, 0x10060800
0x1001ab34 +94    e8 57 08 00 00           call     0x1001b390   ; -> sub_1b390
0x1001ab39 +99    a1 78 41 03 10           mov      eax, dword ptr [0x10034178]
0x1001ab3e +9e    8b 08                    mov      ecx, dword ptr [eax]
0x1001ab40 +a0    8b 11                    mov      edx, dword ptr [ecx]
0x1001ab42 +a2    68 00 6e 03 10           push     0x10036e00
0x1001ab47 +a7    a1 f4 f9 05 10           mov      eax, dword ptr [0x1005f9f4]   ; data ?MaxSurfLights@URender@@2HA
0x1001ab4c +ac    c1 e0 02                 shl      eax, 2
0x1001ab4f +af    50                       push     eax
0x1001ab50 +b0    ff 35 fc f9 05 10        push     dword ptr [0x1005f9fc]   ; data ?SurfLights@URender@@2PAPAUFActorLink@@A
0x1001ab56 +b6    ff 52 04                 call     dword ptr [edx + 4]
0x1001ab59 +b9    a3 fc f9 05 10           mov      dword ptr [0x1005f9fc], eax   ; data ?SurfLights@URender@@2PAPAUFActorLink@@A
0x1001ab5e +be    8b 0d f4 f9 05 10        mov      ecx, dword ptr [0x1005f9f4]   ; data ?MaxSurfLights@URender@@2HA
0x1001ab64 +c4    c1 e1 02                 shl      ecx, 2
0x1001ab67 +c7    51                       push     ecx
0x1001ab68 +c8    6a 00                    push     0
0x1001ab6a +ca    50                       push     eax
0x1001ab6b +cb    e8 20 89 00 00           call     0x10023490   ; -> sub_23490
0x1001ab70 +d0    83 c4 0c                 add      esp, 0xc
0x1001ab73 +d3    8b 45 08                 mov      eax, dword ptr [ebp + 8]
0x1001ab76 +d6    8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x1001ab7c +dc    8b 80 dc 00 00 00        mov      eax, dword ptr [eax + 0xdc]
0x1001ab82 +e2    85 c0                    test     eax, eax
0x1001ab84 +e4    74 5b                    je       0x1001abe1
0x1001ab86 +e6    83 3d 00 fa 05 10 00     cmp      dword ptr [0x1005fa00], 0   ; data ?LeafLights@URender@@2PAPAUFVolActorLink@@A
0x1001ab8d +ed    74 08                    je       0x1001ab97
0x1001ab8f +ef    3b 05 f8 f9 05 10        cmp      eax, dword ptr [0x1005f9f8]   ; data ?MaxLeafLights@URender@@2HA
0x1001ab95 +f5    7e 4a                    jle      0x1001abe1
0x1001ab97 +f7    a3 f8 f9 05 10           mov      dword ptr [0x1005f9f8], eax   ; data ?MaxLeafLights@URender@@2HA
0x1001ab9c +fc    50                       push     eax
0x1001ab9d +fd    b9 58 10 06 10           mov      ecx, 0x10061058
0x1001aba2 +102   e8 e9 07 00 00           call     0x1001b390   ; -> sub_1b390
0x1001aba7 +107   a1 78 41 03 10           mov      eax, dword ptr [0x10034178]
0x1001abac +10c   8b 08                    mov      ecx, dword ptr [eax]
0x1001abae +10e   8b 11                    mov      edx, dword ptr [ecx]
0x1001abb0 +110   68 18 6e 03 10           push     0x10036e18
0x1001abb5 +115   a1 f8 f9 05 10           mov      eax, dword ptr [0x1005f9f8]   ; data ?MaxLeafLights@URender@@2HA
0x1001abba +11a   c1 e0 02                 shl      eax, 2
0x1001abbd +11d   50                       push     eax
0x1001abbe +11e   ff 35 00 fa 05 10        push     dword ptr [0x1005fa00]   ; data ?LeafLights@URender@@2PAPAUFVolActorLink@@A
0x1001abc4 +124   ff 52 04                 call     dword ptr [edx + 4]
0x1001abc7 +127   a3 00 fa 05 10           mov      dword ptr [0x1005fa00], eax   ; data ?LeafLights@URender@@2PAPAUFVolActorLink@@A
0x1001abcc +12c   8b 0d f8 f9 05 10        mov      ecx, dword ptr [0x1005f9f8]   ; data ?MaxLeafLights@URender@@2HA
0x1001abd2 +132   c1 e1 02                 shl      ecx, 2
0x1001abd5 +135   51                       push     ecx
0x1001abd6 +136   6a 00                    push     0
0x1001abd8 +138   50                       push     eax
0x1001abd9 +139   e8 b2 88 00 00           call     0x10023490   ; -> sub_23490
0x1001abde +13e   83 c4 0c                 add      esp, 0xc
0x1001abe1 +141   8b 4e 30                 mov      ecx, dword ptr [esi + 0x30]
0x1001abe4 +144   f6 81 0c 02 00 00 01     test     byte ptr [ecx + 0x20c], 1   ; PF: PF_Invisible
0x1001abeb +14b   75 13                    jne      0x1001ac00
0x1001abed +14d   83 7f 08 00              cmp      dword ptr [edi + 8], 0
0x1001abf1 +151   75 0d                    jne      0x1001ac00
0x1001abf3 +153   8b 81 8c 04 00 00        mov      eax, dword ptr [ecx + 0x48c]
0x1001abf9 +159   85 c0                    test     eax, eax
0x1001abfb +15b   0f 45 c8                 cmovne   ecx, eax
0x1001abfe +15e   eb 02                    jmp      0x1001ac02
0x1001ac00 +160   33 c9                    xor      ecx, ecx
0x1001ac02 +162   51                       push     ecx
0x1001ac03 +163   57                       push     edi
0x1001ac04 +164   8b cb                    mov      ecx, ebx
0x1001ac06 +166   e8 b5 64 00 00           call     0x100210c0   ; -> ?SetupDynamics@URender@@QAEXPAUFSceneNode@@PAVAActor@@@Z
0x1001ac0b +16b   57                       push     edi
0x1001ac0c +16c   8b cb                    mov      ecx, ebx
0x1001ac0e +16e   e8 fd e1 ff ff           call     0x10018e10   ; -> ?OccludeBsp@URender@@QAEXPAUFSceneNode@@@Z
0x1001ac13 +173   33 f6                    xor      esi, esi
0x1001ac15 +175   89 75 ec                 mov      dword ptr [ebp - 0x14], esi
0x1001ac18 +178   83 fe 03                 cmp      esi, 3   ; PF: PF_Invisible|PF_Masked
0x1001ac1b +17b   7d 21                    jge      0x1001ac3e
0x1001ac1d +17d   8b 94 b7 98 00 00 00     mov      edx, dword ptr [edi + esi*4 + 0x98]
0x1001ac24 +184   85 d2                    test     edx, edx
0x1001ac26 +186   74 13                    je       0x1001ac3b
0x1001ac28 +188   8b 4a 04                 mov      ecx, dword ptr [edx + 4]
0x1001ac2b +18b   a1 fc f9 05 10           mov      eax, dword ptr [0x1005f9fc]   ; data ?SurfLights@URender@@2PAPAUFActorLink@@A
0x1001ac30 +190   8b 04 88                 mov      eax, dword ptr [eax + ecx*4]
0x1001ac33 +193   89 42 48                 mov      dword ptr [edx + 0x48], eax
0x1001ac36 +196   8b 52 38                 mov      edx, dword ptr [edx + 0x38]
0x1001ac39 +199   eb e9                    jmp      0x1001ac24
0x1001ac3b +19b   46                       inc      esi
0x1001ac3c +19c   eb d7                    jmp      0x1001ac15
0x1001ac3e +19e   8b 45 08                 mov      eax, dword ptr [ebp + 8]
0x1001ac41 +1a1   8b 80 98 00 00 00        mov      eax, dword ptr [eax + 0x98]
0x1001ac47 +1a7   83 b8 dc 00 00 00 00     cmp      dword ptr [eax + 0xdc], 0
0x1001ac4e +1ae   74 2e                    je       0x1001ac7e
0x1001ac50 +1b0   8b 8f a4 00 00 00        mov      ecx, dword ptr [edi + 0xa4]
0x1001ac56 +1b6   85 c9                    test     ecx, ecx
0x1001ac58 +1b8   74 24                    je       0x1001ac7e
0x1001ac5a +1ba   8b 81 94 00 00 00        mov      eax, dword ptr [ecx + 0x94]
0x1001ac60 +1c0   8b 90 8c 00 00 00        mov      edx, dword ptr [eax + 0x8c]
0x1001ac66 +1c6   83 fa ff                 cmp      edx, -1
0x1001ac69 +1c9   74 0e                    je       0x1001ac79
0x1001ac6b +1cb   a1 00 fa 05 10           mov      eax, dword ptr [0x1005fa00]   ; data ?LeafLights@URender@@2PAPAUFVolActorLink@@A
0x1001ac70 +1d0   8b 04 90                 mov      eax, dword ptr [eax + edx*4]
0x1001ac73 +1d3   89 81 b8 00 00 00        mov      dword ptr [ecx + 0xb8], eax
0x1001ac79 +1d9   8b 49 10                 mov      ecx, dword ptr [ecx + 0x10]
0x1001ac7c +1dc   eb d8                    jmp      0x1001ac56
0x1001ac7e +1de   8b 35 c0 00 06 10        mov      esi, dword ptr [0x100600c0]
0x1001ac84 +1e4   33 d2                    xor      edx, edx
0x1001ac86 +1e6   89 55 e8                 mov      dword ptr [ebp - 0x18], edx
0x1001ac89 +1e9   3b d6                    cmp      edx, esi
0x1001ac8b +1eb   7d 2b                    jge      0x1001acb8
0x1001ac8d +1ed   a1 bc 00 06 10           mov      eax, dword ptr [0x100600bc]   ; data ?PostDynamics@URender@@2V?$TArray@H@@A
0x1001ac92 +1f2   8b 04 90                 mov      eax, dword ptr [eax + edx*4]
0x1001ac95 +1f5   8d 0c c5 00 00 00 00     lea      ecx, [eax*8]
0x1001ac9c +1fc   a1 04 fa 05 10           mov      eax, dword ptr [0x1005fa04]   ; data ?DynamicsCache@URender@@2PAUFDynamicsCache@1@A
0x1001aca1 +201   c7 04 01 00 00 00 00     mov      dword ptr [ecx + eax], 0
0x1001aca8 +208   a1 04 fa 05 10           mov      eax, dword ptr [0x1005fa04]   ; data ?DynamicsCache@URender@@2PAUFDynamicsCache@1@A
0x1001acad +20d   c7 44 01 04 00 00 00 00  mov      dword ptr [ecx + eax + 4], 0
0x1001acb5 +215   42                       inc      edx
0x1001acb6 +216   eb ce                    jmp      0x1001ac86
0x1001acb8 +218   c7 05 c0 00 06 10 00 00 00 00 mov      dword ptr [0x100600c0], 0
0x1001acc2 +222   8b 15 fc f9 05 10        mov      edx, dword ptr [0x1005f9fc]   ; data ?SurfLights@URender@@2PAPAUFActorLink@@A
0x1001acc8 +228   85 d2                    test     edx, edx
0x1001acca +22a   74 34                    je       0x1001ad00
0x1001accc +22c   8b 35 04 08 06 10        mov      esi, dword ptr [0x10060804]
0x1001acd2 +232   33 c9                    xor      ecx, ecx
0x1001acd4 +234   89 4d e4                 mov      dword ptr [ebp - 0x1c], ecx
0x1001acd7 +237   3b ce                    cmp      ecx, esi
0x1001acd9 +239   7d 1b                    jge      0x1001acf6
0x1001acdb +23b   a1 00 08 06 10           mov      eax, dword ptr [0x10060800]   ; data ?DynLightSurfs@URender@@2V?$TArray@H@@A
0x1001ace0 +240   8b 04 88                 mov      eax, dword ptr [eax + ecx*4]
0x1001ace3 +243   c7 04 82 00 00 00 00     mov      dword ptr [edx + eax*4], 0
0x1001acea +24a   41                       inc      ecx
0x1001aceb +24b   89 4d e4                 mov      dword ptr [ebp - 0x1c], ecx
0x1001acee +24e   8b 15 fc f9 05 10        mov      edx, dword ptr [0x1005f9fc]   ; data ?SurfLights@URender@@2PAPAUFActorLink@@A
0x1001acf4 +254   eb e1                    jmp      0x1001acd7
0x1001acf6 +256   c7 05 04 08 06 10 00 00 00 00 mov      dword ptr [0x10060804], 0
0x1001ad00 +260   8b 15 00 fa 05 10        mov      edx, dword ptr [0x1005fa00]   ; data ?LeafLights@URender@@2PAPAUFVolActorLink@@A
0x1001ad06 +266   85 d2                    test     edx, edx
0x1001ad08 +268   74 34                    je       0x1001ad3e
0x1001ad0a +26a   8b 35 5c 10 06 10        mov      esi, dword ptr [0x1006105c]
0x1001ad10 +270   33 c9                    xor      ecx, ecx
0x1001ad12 +272   89 4d e0                 mov      dword ptr [ebp - 0x20], ecx
0x1001ad15 +275   3b ce                    cmp      ecx, esi
0x1001ad17 +277   7d 1b                    jge      0x1001ad34
0x1001ad19 +279   a1 58 10 06 10           mov      eax, dword ptr [0x10061058]   ; data ?DynLightLeaves@URender@@2V?$TArray@H@@A
0x1001ad1e +27e   8b 04 88                 mov      eax, dword ptr [eax + ecx*4]
0x1001ad21 +281   c7 04 82 00 00 00 00     mov      dword ptr [edx + eax*4], 0
0x1001ad28 +288   41                       inc      ecx
0x1001ad29 +289   89 4d e0                 mov      dword ptr [ebp - 0x20], ecx
0x1001ad2c +28c   8b 15 00 fa 05 10        mov      edx, dword ptr [0x1005fa00]   ; data ?LeafLights@URender@@2PAPAUFVolActorLink@@A
0x1001ad32 +292   eb e1                    jmp      0x1001ad15
0x1001ad34 +294   c7 05 5c 10 06 10 00 00 00 00 mov      dword ptr [0x1006105c], 0
0x1001ad3e +29e   8b 77 10                 mov      esi, dword ptr [edi + 0x10]
0x1001ad41 +2a1   85 f6                    test     esi, esi
0x1001ad43 +2a3   74 0d                    je       0x1001ad52
0x1001ad45 +2a5   56                       push     esi
0x1001ad46 +2a6   8b cb                    mov      ecx, ebx
0x1001ad48 +2a8   e8 53 fd ff ff           call     0x1001aaa0   ; -> ?OccludeFrame@URender@@QAEXPAUFSceneNode@@@Z
0x1001ad4d +2ad   8b 76 0c                 mov      esi, dword ptr [esi + 0xc]
0x1001ad50 +2b0   eb ef                    jmp      0x1001ad41
0x1001ad52 +2b2   c7 45 fc ff ff ff ff     mov      dword ptr [ebp - 4], 0xffffffff
0x1001ad59 +2b9   8b 4d f4                 mov      ecx, dword ptr [ebp - 0xc]
0x1001ad5c +2bc   64 89 0d 00 00 00 00     mov      dword ptr fs:[0], ecx
0x1001ad63 +2c3   59                       pop      ecx
0x1001ad64 +2c4   5f                       pop      edi
0x1001ad65 +2c5   5e                       pop      esi
0x1001ad66 +2c6   5b                       pop      ebx
0x1001ad67 +2c7   8b e5                    mov      esp, ebp
0x1001ad69 +2c9   5d                       pop      ebp
0x1001ad6a +2ca   c2 04 00                 ret      4
0x1001ad6d +2cd   68 bc 6d 03 10           push     0x10036dbc
0x1001ad72 +2d2   68 88 46 03 10           push     0x10034688
0x1001ad77 +2d7   ff 15 88 41 03 10        call     dword ptr [0x10034188]   ; -> Core.dll!?appUnwindf@@YAXPBGZZ
0x1001ad7d +2dd   83 c4 08                 add      esp, 8
0x1001ad80 +2e0   6a 00                    push     0
0x1001ad82 +2e2   6a 00                    push     0
0x1001ad84 +2e4   e8 9b 86 00 00           call     0x10023424   ; -> sub_23424
0x1001ad89 +2e9   8b 45 d8                 mov      eax, dword ptr [ebp - 0x28]
0x1001ad8c +2ec   89 45 dc                 mov      dword ptr [ebp - 0x24], eax
0x1001ad8f +2ef   68 7c ea 03 10           push     0x1003ea7c
0x1001ad94 +2f4   8d 45 dc                 lea      eax, [ebp - 0x24]
0x1001ad97 +2f7   50                       push     eax
0x1001ad98 +2f8   e8 87 86 00 00           call     0x10023424   ; -> sub_23424
0x1001ad9d +2fd   cc                       int3     
0x1001ad9e +2fe   cc                       int3     
0x1001ad9f +2ff   cc                       int3     
0x1001ada0 +300   cc                       int3     
0x1001ada1 +301   cc                       int3     
0x1001ada2 +302   cc                       int3     
0x1001ada3 +303   cc                       int3     
0x1001ada4 +304   cc                       int3     
0x1001ada5 +305   cc                       int3     
0x1001ada6 +306   cc                       int3     
0x1001ada7 +307   cc                       int3     
0x1001ada8 +308   cc                       int3     
0x1001ada9 +309   cc                       int3     
0x1001adaa +30a   cc                       int3     
0x1001adab +30b   cc                       int3     
0x1001adac +30c   cc                       int3     
0x1001adad +30d   cc                       int3     
0x1001adae +30e   cc                       int3     
0x1001adaf +30f   cc                       int3     
0x1001adb0 +310   55                       push     ebp
0x1001adb1 +311   8b ec                    mov      ebp, esp
0x1001adb3 +313   8b 4d 10                 mov      ecx, dword ptr [ebp + 0x10]
0x1001adb6 +316   83 ec 0c                 sub      esp, 0xc
0x1001adb9 +319   56                       push     esi
0x1001adba +31a   8b 75 0c                 mov      esi, dword ptr [ebp + 0xc]
0x1001adbd +31d   8d 46 34                 lea      eax, [esi + 0x34]
0x1001adc0 +320   50                       push     eax
0x1001adc1 +321   8d 45 f4                 lea      eax, [ebp - 0xc]
0x1001adc4 +324   50                       push     eax
0x1001adc5 +325   ff 15 f8 41 03 10        call     dword ptr [0x100341f8]   ; -> Core.dll!?TransformPointBy@FVector@@QBE?AV1@ABVFCoords@@@Z
0x1001adcb +32b   8b 55 08                 mov      edx, dword ptr [ebp + 8]
0x1001adce +32e   33 c9                    xor      ecx, ecx
0x1001add0 +330   0f 57 c9                 xorps    xmm1, xmm1
0x1001add3 +333   f3 0f 10 30              movss    xmm6, dword ptr [eax]
0x1001add7 +337   f3 0f 11 32              movss    dword ptr [edx], xmm6
0x1001addb +33b   f3 0f 10 78 04           movss    xmm7, dword ptr [eax + 4]
0x1001ade0 +340   f3 0f 11 7a 04           movss    dword ptr [edx + 4], xmm7
0x1001ade5 +345   f3 0f 10 68 08           movss    xmm5, dword ptr [eax + 8]
0x1001adea +34a   f3 0f 11 6a 08           movss    dword ptr [edx + 8], xmm5
0x1001adef +34f   0f 28 c5                 movaps   xmm0, xmm5
0x1001adf2 +352   f3 0f 59 86 f8 00 00 00  mulss    xmm0, dword ptr [esi + 0xf8]
0x1001adfa +35a   0f 28 d5                 movaps   xmm2, xmm5
0x1001adfd +35d   f3 0f 59 96 f0 00 00 00  mulss    xmm2, dword ptr [esi + 0xf0]
0x1001ae05 +365   0f 28 dd                 movaps   xmm3, xmm5
0x1001ae08 +368   f3 0f 59 9e f4 00 00 00  mulss    xmm3, dword ptr [esi + 0xf4]
0x1001ae10 +370   f3 0f 5c c7              subss    xmm0, xmm7
0x1001ae14 +374   f3 0f 58 d7              addss    xmm2, xmm7
0x1001ae18 +378   0f 28 e5                 movaps   xmm4, xmm5
0x1001ae1b +37b   f3 0f 59 a6 ec 00 00 00  mulss    xmm4, dword ptr [esi + 0xec]
0x1001ae23 +383   0f 2f c8                 comiss   xmm1, xmm0
0x1001ae26 +386   f3 0f 5c de              subss    xmm3, xmm6
0x1001ae2a +38a   f3 0f 11 05 ac 11 06 10  movss    dword ptr [0x100611ac], xmm0
0x1001ae32 +392   f3 0f 58 e6              addss    xmm4, xmm6
0x1001ae36 +396   f3 0f 11 15 a8 11 06 10  movss    dword ptr [0x100611a8], xmm2
0x1001ae3e +39e   0f 97 c1                 seta     cl
0x1001ae41 +3a1   33 c0                    xor      eax, eax
0x1001ae43 +3a3   0f 2f ca                 comiss   xmm1, xmm2
0x1001ae46 +3a6   8a 89 00 6b 03 10        mov      cl, byte ptr [ecx + 0x10036b00]
0x1001ae4c +3ac   f3 0f 11 25 a0 11 06 10  movss    dword ptr [0x100611a0], xmm4
0x1001ae54 +3b4   f3 0f 11 1d a4 11 06 10  movss    dword ptr [0x100611a4], xmm3
0x1001ae5c +3bc   0f 97 c0                 seta     al
0x1001ae5f +3bf   02 88 fc 6a 03 10        add      cl, byte ptr [eax + 0x10036afc]
0x1001ae65 +3c5   33 c0                    xor      eax, eax
0x1001ae67 +3c7   0f 2f cb                 comiss   xmm1, xmm3
0x1001ae6a +3ca   0f 97 c0                 seta     al
0x1001ae6d +3cd   02 88 f8 6a 03 10        add      cl, byte ptr [eax + 0x10036af8]
0x1001ae73 +3d3   33 c0                    xor      eax, eax
0x1001ae75 +3d5   0f 2f cc                 comiss   xmm1, xmm4
0x1001ae78 +3d8   0f 97 c0                 seta     al
0x1001ae7b +3db   02 88 f4 6a 03 10        add      cl, byte ptr [eax + 0x10036af4]
0x1001ae81 +3e1   88 4a 0c                 mov      byte ptr [edx + 0xc], cl
0x1001ae84 +3e4   75 45                    jne      0x1001aecb
0x1001ae86 +3e6   f3 0f 10 8e dc 00 00 00  movss    xmm1, dword ptr [esi + 0xdc]
0x1001ae8e +3ee   f3 0f 5e cd              divss    xmm1, xmm5
0x1001ae92 +3f2   0f 28 c1                 movaps   xmm0, xmm1
0x1001ae95 +3f5   f3 0f 11 4a 1c           movss    dword ptr [edx + 0x1c], xmm1
0x1001ae9a +3fa   f3 0f 59 c6              mulss    xmm0, xmm6
0x1001ae9e +3fe   f3 0f 59 cf              mulss    xmm1, xmm7
0x1001aea2 +402   f3 0f 58 86 c0 00 00 00  addss    xmm0, dword ptr [esi + 0xc0]
0x1001aeaa +40a   f3 0f 11 42 10           movss    dword ptr [edx + 0x10], xmm0
0x1001aeaf +40f   f3 0f 58 8e c4 00 00 00  addss    xmm1, dword ptr [esi + 0xc4]
0x1001aeb7 +417   f3 0f 11 4a 14           movss    dword ptr [edx + 0x14], xmm1
0x1001aebc +41c   f3 0f 5c 0d 6c 4b 03 10  subss    xmm1, dword ptr [0x10034b6c]   ; [0x10034b6c] f32=0.5
0x1001aec4 +424   f3 0f 2d c1              cvtss2si eax, xmm1
0x1001aec8 +428   89 42 18                 mov      dword ptr [edx + 0x18], eax
0x1001aecb +42b   5e                       pop      esi
0x1001aecc +42c   8b e5                    mov      esp, ebp
0x1001aece +42e   5d                       pop      ebp
0x1001aecf +42f   c3                       ret      

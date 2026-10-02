// FindBestSplit @ 0x100335d0  size=819
typedef struct struct_0 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    char field_c;
    char padding_d[419];
    unsigned int field_1b0;
} struct_0;

extern unsigned int g_10140164;
extern char GNull;

struct_0 * sub_100335d0(int a0, struct_0 **a1, unsigned int a2, int a3)
{
    unsigned long v33;  // ldt
    unsigned long v34;  // gdt
    int v44;  // xmm0
    int v45;  // xmm0
    int v46;  // xmm0
    int i;  // ebx
    int v48;  // ecx
    int v49;  // edx
    struct_0 **v50;  // edi
    int v51;  // esi
    int index;  // esi
    unsigned short v35;  // fs
    struct_0 *v53;  // ebx
    int iter;  // edi
    int v55;  // xmm1
    int v57;  // xmm1
    int v58;  // xmm1
    int v59;  // xmm1
    int v61;  // xmm2
    int v62;  // xmm2
    unsigned long long v36;  // 4186
    int v63;  // xmm0
    int v65;  // xmm0
    int v66;  // xmm0
    int v67;  // xmm0
    int v68;  // xmm2
    int v69;  // xmm0
    int v71;  // xmm0
    int v72;  // xmm0
    unsigned int v37;  // ebx
    int v73;  // xmm0
    uint128_t v74;  // xmm0
    unsigned long long v75;  // 4120
    unsigned int v76;  // eax
    unsigned long long v77;  // 4125
    unsigned int v38;  // esi
    unsigned int v39;  // edi
    unsigned long long v40;  // 4190
    int v41;  // esi
    uint128_t v42;  // xmm0
    unsigned int v0;  // [bp-0xbc]
    char v1;  // [bp-0xac]
    unsigned int v2;  // [bp-0x9c]
    unsigned int v3;  // [bp-0x98]
    unsigned int v4;  // [bp-0x84]
    unsigned long v5;  // [bp-0x80]
    unsigned int v6;  // [bp-0x78]
    unsigned int v7;  // [bp-0x74]
    unsigned int v8;  // [bp-0x70]
    unsigned int v9;  // [bp-0x6c]
    unsigned int v10;  // [bp-0x5c]
    unsigned int v11;  // [bp-0x58]
    unsigned int v12;  // [bp-0x54]
    unsigned int v13;  // [bp-0x50]
    unsigned int j;  // [bp-0x4c], Other Possible Types: int
    unsigned int v15;  // [bp-0x48]
    unsigned int v16;  // [bp-0x44]
    int v17;  // [bp-0x40]
    unsigned int v18;  // [bp-0x3c]
    struct_0 *v19;  // [bp-0x38]
    unsigned int v20;  // [bp-0x34]
    struct_0 *v21;  // [bp-0x30]
    unsigned int v22;  // [bp-0x2c], Other Possible Types: int
    int v23;  // [bp-0x28]
    unsigned int v24;  // [bp-0x24]
    unsigned int v25;  // [bp-0x20]
    int v26;  // [bp-0x1c]
    unsigned int node;  // [bp-0x18]
    char *v28;  // [bp-0x14]
    unsigned int v29;  // [bp-0x10]
    unsigned int v30;  // [bp-0xc]
    unsigned int v31;  // [bp-0x8]
    char v32;  // [bp-0x4]

    v31 = 0xffffffff;
    v30 = sub_100c4990;
    v36 = _ccall(v33, v34, (unsigned int)v35, 0);
    v29 = *((int *)(unsigned int)v36);
    v9 = v37;
    v8 = v38;
    v7 = v39;
    v6 = g_10140164 ^ &v32;
    v40 = _ccall(v33, v34, (unsigned int)v35, 0);
    *((unsigned int **)(unsigned int)v40) = &v29;
    v28 = &v6;
    v31 = 0;
    v41 = a0;
    if (v41 <= 0)
    {
        appFailAssert("NumPolys>0", "C:\\GameDev\\UnrealTournament\\Editor\\Src\\UnBsp.cpp", 376);
    }
    else if (v41 == 1)
    {
        v76 = *(a1);
        v77 = _ccall(v33, v34, (unsigned int)v35, 0);
        *((unsigned int *)(unsigned int)v77) = v29;
        return v76;
    }
    v21 = NULL;
    v42 = (char)(a3 >> 8);
    v44 = (int)_INSERT(_INSERT(v42, 12, v42 >> 96), 8, v42 >> 64);
    v45 = (int)_INSERT(v44, 4, (unsigned long long)v42 >> 32);
    v46 = (int)_INSERT(v45, 0, v42);
    v12 = (unsigned int)(DivV(v46, 0x42c80000));
    v13 = (char)a3;
    v5 = v12;
    v4 = v13;
    FOutputDevice::Logf(*((int *)&GNull), L"Balance=%d PortalBias=%f");
    if (a2 == 2)
    {
        i = 1;
    }
    else
    {
        i = (a2 == 1 ? ((int)(1717986919 * v41 >> 35) >> 31) + (int)(1717986919 * v41 >> 35) : (int)((v41 >> 31 & 3) + v41) >> 2);
        if (i <= 1)
            i = 1;
    }
    v26 = i;
    v48 = 0;
    v49 = v41;
    v50 = a1;
    while (1)
    {
        v22 = v48;
        if (v48 >= v49 || !((char)v50[v48]->field_1b0 & 40))
            break;
        v48 += 1;
    }
    v16 = v48 >= v49;
    v18 = 0;
    v10 = 0;
    v51 = 0;
    v23 = 0;
    for (v22 = 0; v51 < v49; i = v26)
    {
        v20 = 0;
        v24 = 0;
        v25 = 0;
        v15 = 0;
        node = 0;
        index = v51 - 1;
        v17 = index;
        v23 += i;
        while (1)
        {
            index += 1;
            v17 = index;
            v53 = v50[index];
            if (index >= v23 || index >= v49)
                break;
            if ((!((char)v53->field_1b0 & 40) || v53->field_1b0 & 0x4000000 || v16) && index < v49)
            {
                iter = 0;
                j = 0;
                for (node = node; iter < v49; j = iter + v26)
                {
                    if (iter != index)
                    {
                        v19 = a1[iter];
                        v3 = 0;
                        v2 = 0;
                        v0 = v53->field_0;
                        FPlane::FPlane(&v1, v53->field_4);
                        FPoly::SplitWithPlaneFast(v19, v53->field_8, &v53->field_c);
                        switch (FPoly::SplitWithPlaneFast(v19, v53->field_8, &v53->field_c))
                        {
                        case 0:
                            v20 += 1;
                            goto LABEL_100337d1;
                        case 1:
                            v25 += 1;
                            v15 = v25;
                            v49 = a0;
                            j = iter + v26;
                            break;
                        case 2:
                            v24 += 1;
                            v49 = a0;
                            j = iter + v26;
                            break;
                        case 3:
                            if (!(v19->field_1b0 & 0x4000000))
                            {
                                node += 1;
                                j = iter + v26;
                                v49 = a0;
                                break;
                            }
                            else
                            {
                                node += 16;
                                j = iter + v26;
                                v49 = a0;
                                break;
                            }
                        default:
LABEL_100337d1:
                            v49 = a0;
                            goto LABEL_100337d7;
                        }
                    }
LABEL_100337d7:
                }
                v55 = (int)v13;
                v57 = (int)_INSERT(_INSERT(v55, 12, (unsigned int)(v55 >> 96)), 8, (unsigned int)(v55 >> 64));
                v58 = (int)_INSERT(v57, 4, (unsigned long long)v55 >> 32);
                v59 = (int)_INSERT(v58, 0, (unsigned int)v55);
                v61 = (int)_INSERT(_INSERT(0, 8, 0), 4, 0);
                v62 = (int)_INSERT(v61, 0, 0x42c80000);
                v63 = (int)node;
                v65 = (int)_INSERT(_INSERT(v63, 12, (unsigned int)(v63 >> 96)), 8, (unsigned int)(v63 >> 64));
                v66 = (int)_INSERT(v65, 4, (unsigned long long)v63 >> 32);
                v67 = (int)_INSERT(v66, 0, (unsigned int)v63);
                v68 = MulV(SubV(v62, v59), v67);
                v69 = (int)((v25 - v24 ^ (int)(v25 - v24) >> 31) - ((int)(v25 - v24) >> 31));
                v71 = (int)_INSERT(_INSERT(v69, 12, (unsigned int)(v69 >> 96)), 8, (unsigned int)(v69 >> 64));
                v72 = (int)_INSERT(v71, 4, (unsigned long long)v69 >> 32);
                v73 = (int)_INSERT(v72, 0, (unsigned int)v69);
                v74 = (uint128_t)(AddV(MulV(v73, v59), v68));
                v11 = v74;
                if (v53->field_1b0 & 0x4000000)
                {
                    v74 = (uint128_t)(SubV(v74, MulV(v68, v12)));
                    v11 = v74;
                }
                if (((CmpF(v18, (unsigned int)v74) & 69 | (char)((CmpF(v18, (unsigned int)v74) & 69) >> 6)) & 1) != 1 || !v21)
                {
                    v21 = v53;
                    v18 = v74;
                    v10 = v18;
                }
                v49 = a0;
                v50 = a1;
                break;
            }
        }
        v22 = v23;
    }
    if (!v21)
        appFailAssert("Best", "C:\\GameDev\\UnrealTournament\\Editor\\Src\\UnBsp.cpp", 476);
    v75 = _ccall(v33, v34, (unsigned int)v35, 0);
    *((unsigned int *)(unsigned int)v75) = v29;
    return v21;
}

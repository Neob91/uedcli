typedef struct struct_1 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    unsigned int field_c;
    unsigned int field_10;
    unsigned int field_14;
    unsigned int field_18;
    unsigned int field_1c;
    unsigned short field_20;
    unsigned short field_22;
    unsigned int field_24;
} struct_1;

class class FVector {
} class FVector;

class class UModel {
} class UModel;

class enum ENodePlace {
} enum ENodePlace;

typedef struct struct_6 {
    char padding_0[448];
    char field_1c0;
} struct_6;

typedef struct struct_2 {
    char padding_0[448];
    unsigned int field_1c0;
} struct_2;

typedef struct struct_5 {
    unsigned int field_0;
    class FVector field_4;
    unsigned int field_8;
    char padding_c[440];
    unsigned int field_1c4;
} struct_5;

typedef struct struct_0 {
    char padding_0[432];
    unsigned int field_1b0;
    unsigned int field_1b4;
    unsigned int field_1b8;
    char padding_1bc[4];
    unsigned int field_1c0;
    char padding_1c4[4];
    unsigned int field_1c8;
    unsigned short field_1cc;
    unsigned short field_1ce;
} struct_0;

typedef struct struct_4 {
    uint128_t field_0;
    unsigned int field_10;
    unsigned int field_14;
    unsigned int field_18;
    unsigned int field_1c;
    char padding_20[12];
    unsigned int field_2c;
    unsigned int field_30;
    char field_34;
    char field_35;
    char field_36;
    char field_37;
    unsigned int field_38;
    unsigned int field_3c;
} struct_4;

extern char g_10020000;
extern unsigned int g_10140164;
extern unsigned int g_101491b4;
extern char GMem;
extern char FPlane::PlaneDot;
extern char GLog;

int UEditorEngine::bspAddNode(void* this, class UModel *arg_0, int idx, enum ENodePlace arg_2, unsigned long arg_3)
{
    unsigned long v23;  // ldt
    unsigned long v24;  // gdt
    struct_0 *idx1;  // esi
    unsigned int *idx2;  // ecx
    unsigned int v35;  // eax
    struct_1 *index;  // edx
    unsigned int v37;  // edx
    enum ENodePlace v38;  // eax
    void* v39;  // eax
    void* v41;  // eax
    unsigned short v25;  // fs
    class UModel *v43;  // edi
    unsigned int v44;  // esi
    unsigned int v45;  // eax
    unsigned int *v46;  // esi
    struct_4 *v47;  // esi
    unsigned int *v48;  // edi
    struct_5 *v49;  // edx
    unsigned int v50;  // eax
    unsigned int v51;  // ecx
    unsigned int v52;  // edx
    unsigned long long v26;  // 4193
    unsigned int v53;  // ecx
    unsigned int v54;  // ecx
    struct_6 *v55;  // edi
    char i;  // dh
    char v57;  // al
    char v58;  // dl
    char v59;  // 4106
    unsigned int v60;  // ecx
    char v61;  // dh
    char v62;  // dh
    unsigned int v27;  // ebx
    unsigned long long v63;  // 4119
    unsigned int v28;  // esi
    unsigned int v29;  // edi
    unsigned long long v30;  // 4197
    int v31;  // edi
    unsigned int v32;  // ecx
    unsigned int v0;  // [bp-0xbc]
    unsigned int v1;  // [bp-0xb4]
    unsigned int v2;  // [bp-0xb0]
    unsigned int v3;  // [bp-0xa0]
    unsigned int v4;  // [bp-0x98]
    struct_5 *v5;  // [bp-0x94]
    unsigned int v6;  // [bp-0x54]
    unsigned int v7;  // [bp-0x50]
    unsigned int v8;  // [bp-0x4c]
    unsigned int v9;  // [bp-0x48]
    char v10;  // [bp-0x44]
    unsigned int v11;  // [bp-0x34]
    unsigned int v12;  // [bp-0x30]
    unsigned int v13;  // [bp-0x2c]
    class UModel *v14;  // [bp-0x20], Other Possible Types: unsigned int *, unsigned int
    char v15;  // [bp-0x15]
    char *v16;  // [bp-0x14]
    unsigned int v17;  // [bp-0x10]
    unsigned int v18;  // [bp-0xc]
    unsigned int v19;  // [bp-0x8]
    char v20;  // [bp-0x4]
    unsigned int *v21;  // [bp+0xc], Other Possible Types: unsigned int
    char v22;  // [bp+0x13]

    v19 = 0xffffffff;
    v18 = sub_100c4b90;
    v26 = _ccall(v23, v24, (unsigned int)v25, 0);
    v17 = *((int *)(unsigned int)v26);
    v9 = v27;
    v8 = v28;
    v7 = v29;
    v6 = g_10140164 ^ &v20;
    v30 = _ccall(v23, v24, (unsigned int)v25, 0);
    *((unsigned int **)(unsigned int)v30) = &v17;
    v16 = &v6;
    v19 = 0;
    v31 = idx;
    if (v21 == 2)
    {
        while (1)
        {
            v32 = v31 * 64;
            if (*((int *)((int)arg_0[22] + v32 + 40)) == -0x1)
                break;
            v31 = *((int *)((int)arg_0[22] + v32 + 40));
        }
    }
    idx1 = arg_3;
    idx2 = arg_0;
    if (idx1->padding_1c4 == idx2[39])
    {
        v35 = sub_10031d10(1);
        idx = v35 * 64 + idx2[38];
        idx1 = arg_3;
        idx->field_8 = (*((int *)(*((int *)this) + 500)))(arg_0, idx1, 1);
        idx->field_c = (*((int *)(*((int *)this) + 496)))(arg_0, &idx1->padding_0[12], 1);
        idx->field_10 = (*((int *)(*((int *)this) + 496)))(arg_0, &idx1->padding_0[24], 0);
        index = idx;
        index->field_14 = (*((int *)(*((int *)this) + 496)))(arg_0, &idx1->padding_0[36], 0);
        index->field_0 = idx1->field_1b8;
        index->field_18 = 0xffffffff;
        index->field_24 = 0;
        index->field_20 = idx1->field_1cc;
        index->field_22 = idx1->field_1ce;
        index->field_4 = idx1->field_1b0 & 0x3cffffff;
        index->field_24 = idx1->field_1b4;
        index->field_1c = idx1->field_1c8;
        idx2 = arg_0;
    }
    else
    {
        if (idx1->padding_1c4 == -0x1)
        {
            appFailAssert("EdPoly->iLink!=INDEX_NONE", "C:\\GameDev\\UnrealTournament\\Editor\\Src\\UnBsp.cpp", 233);
            idx2 = arg_0;
        }
        if (idx1->padding_1c4 >= idx2[39])
        {
            appFailAssert("EdPoly->iLink<Model->Surfs.Num()", "C:\\GameDev\\UnrealTournament\\Editor\\Src\\UnBsp.cpp", 234);
            idx2 = arg_0;
        }
        index = (struct_1 *)(idx1->padding_1c4 * 64 + idx2[38]);
    }
    v37 = index->field_4;
    v38 = arg_2;
    if ((char)v37 & 8)
    {
        v38 |= 1;
        arg_2 = v38;
    }
    if (v37 & 67108865)
    {
        v38 |= 4;
        arg_2 = v38;
    }
    if ((char)v37 & 2)
    {
        v38 |= 2;
        arg_2 = v38;
    }
    if (v37 & &g_10020000)
        arg_2 = v38 | 2;
    if (idx1->field_1c0 > 16)
    {
        v11 = &GMem;
        v12 = *((int *)&GMem);
        v13 = *((int *)&FPlane::PlaneDot);
        v39 = FMemStack::PushBytes(&GMem, 472, 16);
        arg_3 = (!v39 ? NULL : (unsigned int)FPoly::FPoly(v39));
        FPoly::operator=(arg_3, idx1);
        arg_3->field_1c0 = 16;
        v41 = FMemStack::PushBytes(&GMem, 472, 16);
        idx = (!v41 ? NULL : (unsigned int)FPoly::FPoly(v41));
        FPoly::operator=(idx, idx1);
        idx->field_1c0 = idx1->field_1c0 - 14;
        appMemmove(&idx->padding_0[60], &idx1->padding_0[228], (idx1->field_1c0 - 15) * 12);
        v43 = arg_0;
        v44 = (*((int *)(*((int *)this) + 548)))(v43, v31, v21, arg_2, arg_3);
        (*((int *)(*((int *)this) + 548)))(v43, v44, 2, arg_2, idx);
        FMemMark::Pop(&v11);
        v45 = v44;
    }
    else
    {
        v46 = idx2 + 22;
        v14 = v46;
        if (v21 != 3)
        {
            sub_10034020(v31);
            idx = sub_10031cb0(1);
            v47 = idx * 64 + *(v46);
            v48 = v31 * 64 + *(v46);
        }
        else
        {
            idx = sub_10031cb0(1);
            v47 = idx * 64 + *(v14);
            v48 = NULL;
        }
        v49 = arg_3;
        v47->field_1c = v49->field_1c4;
        v47->field_37 = *((char *)&arg_2);
        v47->field_30 = 0xffffffff;
        v47->field_2c = 0xffffffff;
        if (v48)
        {
            v50 = v48[4];
            v51 = v48[5];
        }
        else
        {
            v50 = 0xffffffff;
            v51 = 0xffffffff;
        }
        v47->field_10 = v50;
        v47->field_14 = v51;
        v5 = v49->padding_c;
        v3 = v49->field_0;
        v4 = v49->field_8;
        v47->field_0 = *((int128_t *)(unsigned int)FPlane::FPlane(&v10, (int)v49->field_4));
        v14 = arg_0 + 26;
        v47->field_18 = sub_10031680(*((int *)(arg_3 + 448)));
        memset(v47->padding_20, -0x1, 12);
        v52 = v21;
        if (v52 == 3)
        {
            v47->field_38 = 0xffffffff;
            v47->field_3c = 0xffffffff;
            v47->field_34 = 0;
            v47->field_35 = 0;
        }
        else if (v52 != 1 && v52)
        {
            FPlane::operator|(v47, v48);
            if (/* unsupported instruction */)
            {
                arg_2 = /* unsupported instruction */;
                /* unsupported instruction */
            }
            else
            {
                arg_2 = nan;
                /* unsupported instruction */
            }
            v53 = !((CmpF(0, arg_2) & 69 | (CmpF(0, arg_2) & 69) >> 6) & 1);
            v47->field_38 = v48[14 + v53];
            v47->field_3c = v48[15 + -1 * v53];
            v47->field_34 = *(v53 + (char *)v48 + 52);
            v47->field_35 = *((char *)v48 - v53 + 53);
            v52 = v21;
LABEL_100352bd:
            if (v52 == 2)
                v48[10] = idx;
        }
        else
        {
            v54 = v52 == 1;
            v47->field_38 = v48[14 + v54];
            v47->field_3c = v48[14 + v54];
            v47->field_34 = *(v54 + (char *)v48 + 52);
            v47->field_35 = *(v54 + (char *)v48 + 52);
            if (v52 == 1)
            {
                v48[9] = idx;
            }
            else
            {
                if (v52)
                    goto LABEL_100352bd;
                v48[8] = idx;
            }
        }
        v55 = arg_3;
        i = v55->field_1c0;
        v22 = v55->field_1c0;
        v47->field_36 = 0;
        v21 = *((int *)v14) + v47->field_18 * 8;
        v57 = 0;
        v15 = 0;
        for (v58 = 0; v57 < i; i = v22)
        {
            v14 = (*((int *)(*((int *)this) + 500)))(arg_0, &v55->padding_0[48 + 12 * v57], 0);
            v59 = v47->field_36;
            v58 = v59;
            v60 = v59;
            if (!v59 || (v55 = (struct_6 *)arg_3, *((int *)((char *)v21 + 8 * v60 - 8)) != v14))
            {
                v21[1 + 2 * v60] = 0xffffffff;
                v21[2 * v47->field_36] = v14;
                v47->field_36 = v47->field_36 + 1;
                v58 = v47->field_36;
            }
            v57 = v15 + 1;
            v15 += 1;
        }
        v61 = v58;
        if (v58 >= 2 && *(v21) == *((int *)((char *)&v21[2 * v58] - 8)))
        {
            v62 = v61 - 1;
            v47->field_36 = v61 - 1;
            v61 = v62;
        }
        if (v61 < 3)
        {
            g_101491b4 = g_101491b4 + 1;
            v2 = v22;
            v1 = v47->field_36;
            v0 = 0x2ff;
            FOutputDevice::Logf(*((int *)&GLog), L"bspAddNode: Infinitesimal polygon %i (%i)");
            v47->field_36 = 0;
        }
        v45 = idx;
    }
    v63 = _ccall(v23, v24, (unsigned int)v25, 0);
    *((unsigned int *)(unsigned int)v63) = v17;
    return v45;
}

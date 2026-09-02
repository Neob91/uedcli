// FilterWorldThroughBrush @ 0x10033250  size=823
typedef struct struct_5 {
    char padding_0[12];
    unsigned int field_c;
} struct_5;

typedef struct struct_0 {
    char padding_0[28];
    unsigned int field_1c;
    char padding_20[23];
    char field_37;
} struct_0;

typedef struct struct_3 {
    unsigned int field_0;
} struct_3;

typedef struct struct_2 {
    char padding_0[504];
    struct struct_3 *field_1f8;
} struct_2;

typedef struct struct_4 {
    struct struct_2 *field_0;
} struct_4;

typedef struct struct_1 {
    char padding_0[88];
    unsigned int field_58;
} struct_1;

extern unsigned int g_101491b8;
extern int g_101491bc;
extern unsigned int g_101491c0;
extern int g_101491c4;
extern struct_1 *g_101491c8;
extern struct_4 *GEditor;

int sub_10033250(unsigned int *a0, void* a1, unsigned int *a2, unsigned int a3, struct_5 *a4)
{
    unsigned long v15;  // ldt
    unsigned long v16;  // gdt
    uint128_t v25;  // xmm2
    unsigned int *v26;  // edi
    struct_0 *v27;  // ecx
    int v29;  // xmm2
    unsigned int v30;  // xmm1
    unsigned int *idx;  // edx
    unsigned int *v32;  // ecx
    unsigned int v33;  // esi
    unsigned short v17;  // fs
    unsigned int *v35;  // eax
    unsigned int v36;  // esi
    unsigned long long v37;  // 4120
    unsigned int v38;  // eax
    unsigned long long v18;  // 4151
    unsigned int v19;  // ebx
    unsigned int v20;  // esi
    unsigned int v21;  // edi
    unsigned long long v22;  // 4174
    unsigned int *v23;  // ecx
    unsigned int v24;  // esi
    unsigned int v0;  // [bp-0x224]
    unsigned int v1;  // [bp-0x220]
    unsigned int v2;  // [bp-0x21c]
    unsigned int v3;  // [bp-0x210]
    unsigned int v4;  // [bp-0x20c]
    unsigned int v5;  // [bp-0x208]
    unsigned int v6;  // [bp-0x204]
    unsigned int *v7;  // [bp-0x1f4]
    char v8;  // [bp-0x1f0]
    unsigned int v9;  // [bp-0x3c]
    unsigned int v10;  // [bp-0x28]
    unsigned int v11;  // [bp-0x14]
    unsigned int v12;  // [bp-0x10]
    unsigned int v13;  // [bp-0xc]
    unsigned int v14;  // [bp-0x8]

    v14 = 0xffffffff;
    v13 = sub_100c4960;
    v18 = _ccall(v15, v16, (unsigned int)v17, 0);
    v12 = *((int *)(unsigned int)v18);
    v2 = v19;
    v1 = v20;
    v0 = v21;
    v22 = _ccall(v15, v16, (unsigned int)v17, 0);
    *((unsigned int **)(unsigned int)v22) = &v12;
    v11 = &/* unsupported instruction */;
    v23 = a0;
    v7 = v23;
    v24 = a3;
    v14 = 0;
    while (1)
    {
        if (v24 == 0xffffffff)
        {
            v14 = 0xffffffff;
            break;
        }
        v3 = v24 * 64;
        v26 = v23 + 22;
        v27 = *(v26) + v3;
        v5 = v27->field_1c;
        if (v27->field_37 & 32)
            break;
        v6 = 1;
        v4 = 1;
        if (a4)
        {
            FPlane::PlaneDot(v27, a4);
            if (/* unsupported instruction */)
            {
                v6 = /* unsupported instruction */;
                /* unsupported instruction */
            }
            else
            {
                v6 = nan;
                /* unsupported instruction */
            }
            v29 = (int)_INSERT(_INSERT(v25, 8, 0), 4, 0);
            v25 = _INSERT(v29, 0, a4->field_c);
            v30 = v6;
            v6 = !(CmpF(v30, (unsigned int)(v25 ^ 0x80000000800000008000000080000000)) & 69 & 1);
            v4 = !(CmpF((unsigned int)v25, v30) & 69 & 1);
        }
        FPoly::FPoly(&v8);
        if (v6)
        {
            if (v4)
            {
                idx = v7;
                if (GEditor->field_0->field_1f8(v7, v24, &v8) <= 0)
                    goto LABEL_100334fd;
                v5 *= 64;
                v9 = *((int *)(idx[38] + v5 + 36));
                v10 = *((int *)(idx[38] + v5 + 28));
                v32 = a2;
                if (!(v32 != 0x1 && v32 != 0x2))
                {
                    g_101491bc = v24;
                    g_101491c8 = idx;
                    g_101491b8 = 0;
                    g_101491c4 = idx[23];
                    do
                    {
                        v33 = v24;
                        g_101491c0 = v33;
                        v24 = *((int *)(v33 * 64 + *(v26) + 40));
                    } while (*((int *)(v33 * 64 + *(v26) + 40)) != 0xffffffff);
                    v35 = sub_10034980;
                    if (v32 == 0x1)
                        v35 = sub_10031b90;
                    sub_10031f50(v35, a1, &v8);
                    if (!g_101491b8)
                    {
                        *((unsigned int *)(g_101491c0 * 64 + *(v26) + 40)) = 0xffffffff;
                        sub_10034050(g_101491c4, v7[23] - g_101491c4);
                    }
                    else
                    {
                        if (*((char *)(g_101491bc * 64 + g_101491c8->field_58 + 54)))
                        {
                            sub_10034020(g_101491bc);
                            *((char *)(g_101491c8->field_58 + g_101491bc * 64 + 54)) = 0;
                        }
                    }
                }
                else if (v32 == 0x3)
                {
                    sub_10031f50(sub_10033ab0, a1, &v8);
                }
                else
                {
                    if (v32 != 0x4)
                        goto LABEL_10033503;
                    sub_10031f50(sub_10032460, a1, &v8);
                }
            }
            idx = v7;
LABEL_100334fd:
            v32 = a2;
LABEL_10033503:
            v36 = v3;
            if (*((int *)(v36 + *(v26) + 36)) != 0xffffffff)
            {
                sub_10033250(idx, a1, v32, *((int *)(v36 + *(v26) + 36)), a4);
                goto LABEL_10033533;
            }
        }
        else
        {
            v36 = v3;
LABEL_10033533:
            if (v4 && *((int *)(v36 + *(v26) + 32)) != 0xffffffff)
                sub_10033250(v7, a1, a2, *((int *)(v36 + *(v26) + 32)), a4);
            v24 = *((int *)(v36 + *(v26) + 40));
            v23 = v7;
        }
    }
    v37 = _ccall(v15, v16, (unsigned int)v17, 0);
    *((unsigned int *)(unsigned int)v37) = v12;
    return v38;
}

// SplitPolyList @ 0x10034530  size=827
typedef struct struct_0 {
    char padding_0[156];
    unsigned int field_9c;
} struct_0;

typedef struct struct_4 {
    char padding_0[448];
    int field_1c0;
} struct_4;

typedef struct struct_6 {
    char padding_0[452];
    unsigned int field_1c4;
} struct_6;

typedef struct struct_2 {
    unsigned int field_0;
} struct_2;

typedef struct struct_1 {
    char padding_0[548];
    struct struct_2 *field_224;
} struct_1;

typedef struct struct_3 {
    struct struct_1 *field_0;
} struct_3;

extern unsigned int g_10140164;
extern struct_3 *GEditor;
extern char GMem;
extern char FPlane::PlaneDot;

void sub_10034530(struct_0 *a0, unsigned int a1, unsigned int a2, int a3, int a4, int a5, int a6, int a7)
{
    unsigned long v25;  // ldt
    unsigned long v26;  // gdt
    struct_0 *v35;  // edi
    void* v36;  // eax
    void* v38;  // eax
    struct_4 *v40;  // eax
    int iter;  // esi
    struct_6 *v42;  // edi
    int idx;  // edi
    int idx1;  // edi
    unsigned short v27;  // fs
    void* v45;  // eax
    struct_4 *v47;  // edi
    void* v48;  // eax
    void* v50;  // eax
    void* v52;  // eax
    int v53;  // edx
    struct_0 *v54;  // edi
    unsigned long long v28;  // 4176
    unsigned long long v55;  // 4122
    unsigned int v29;  // ebx
    unsigned int v30;  // esi
    unsigned int v31;  // edi
    unsigned long long v32;  // 4196
    int v33;  // esi
    int node;  // ebx
    unsigned int v0;  // [bp-0x6c]
    unsigned int v1;  // [bp-0x68]
    unsigned int v2;  // [bp-0x64]
    unsigned int v3;  // [bp-0x60]
    unsigned int v4;  // [bp-0x5c]
    unsigned int v5;  // [bp-0x58]
    unsigned int v6;  // [bp-0x54]
    int v7;  // [bp-0x48]
    struct_4 *v8;  // [bp-0x44], Other Possible Types: unsigned int
    struct_4 *v9;  // [bp-0x40]
    struct_6 *v10;  // [bp-0x3c]
    void* v11;  // [bp-0x38]
    unsigned int v12;  // [bp-0x34]
    void* v13;  // [bp-0x30]
    unsigned int v14;  // [bp-0x2c], Other Possible Types: int
    unsigned int v15;  // [bp-0x28]
    unsigned int v16;  // [bp-0x24]
    int idx2;  // [bp-0x20]
    struct_4 *v18;  // [bp-0x1c]
    struct_4 *v19;  // [bp-0x18]
    char *v20;  // [bp-0x14]
    unsigned int v21;  // [bp-0x10]
    unsigned int v22;  // [bp-0xc]
    unsigned int v23;  // [bp-0x8]
    char v24;  // [bp-0x4]

    v23 = 0xffffffff;
    v22 = sub_100c4b00;
    v28 = _ccall(v25, v26, (unsigned int)v27, 0);
    v21 = *((int *)(unsigned int)v28);
    v3 = v29;
    v2 = v30;
    v1 = v31;
    v0 = g_10140164 ^ &v24;
    v32 = _ccall(v25, v26, (unsigned int)v27, 0);
    *((unsigned int **)(unsigned int)v32) = &v21;
    v20 = &v0;
    v23 = 0;
    v4 = &GMem;
    v5 = *((int *)&GMem);
    v6 = *((int *)&FPlane::PlaneDot);
    idx2 = 0;
    v33 = (((int)(a3 + (a3 >> 31 & 3)) >> 2) + a3) * 4 + 32;
    v16 = FMemStack::PushBytes(&GMem, v33, 16);
    node = 0;
    v14 = 0;
    v15 = FMemStack::PushBytes(&GMem, v33, 16);
    v10 = sub_100335d0(a3, a4, a5, a6);
    v35 = a0;
    if (a7)
        v10->field_1c4 = v35->field_9c;
    v11 = GEditor->field_0->field_224(v35, a1, a2, 0, v10);
    v13 = v11;
    v36 = FMemStack::PushBytes(&GMem, 472, 16);
    v18 = (!v36 ? NULL : (unsigned int)FPoly::FPoly(v36));
    v9 = v18;
    v38 = FMemStack::PushBytes(&GMem, 472, 16);
    v40 = (!v38 ? NULL : (unsigned int)FPoly::FPoly(v38));
    v19 = v40;
    v8 = v40;
    iter = 0;
    while (1)
    {
        v7 = iter;
        if (iter >= a3)
            break;
        v42 = *((int *)(a4 + iter * 4));
        if (v42 != v10)
        {
            FPoly::SplitWithPlane(v42, v10, (struct struct_6 *)&v10->padding_0[12], v18, v40, 0);
            switch (FPoly::SplitWithPlane(v42, v10, (struct struct_6 *)&v10->padding_0[12], v18, v40, 0))
            {
            case 0:
                if (a7)
                    v42->field_1c4 = a0->field_9c - 1;
                v13 = GEditor->field_0->field_224(a0, v13, 2, 0, v42);
                goto LABEL_100346be;
            case 1:
                idx = idx2;
                *((int *)(v16 + idx * 4)) = *((int *)(a4 + iter * 4));
                idx2 = idx + 1;
                v40 = v19;
                iter += 1;
                break;
            case 2:
                *((int *)(v15 + node * 4)) = *((int *)(a4 + iter * 4));
                node += 1;
                v14 = node;
                v40 = v19;
                iter += 1;
                break;
            case 3:
                idx1 = idx2;
                *((struct_4 **)(v16 + idx1 * 4)) = v18;
                idx2 = idx1 + 1;
                *((struct_4 **)(v15 + node * 4)) = v19;
                node += 1;
                v14 = node;
                if (v18->field_1c0 >= 14)
                {
                    v45 = FMemStack::PushBytes(&GMem, 472, 16);
                    v12 = (!v45 ? 0 : (unsigned int)FPoly::FPoly(v45));
                    FPoly::SplitInHalf(v18, v12);
                    *((unsigned int *)(v16 + idx2 * 4)) = v12;
                    idx2 += 1;
                }
                v47 = v19;
                if (v47->field_1c0 >= 14)
                {
                    v48 = FMemStack::PushBytes(&GMem, 472, 16);
                    v12 = (!v48 ? 0 : (unsigned int)FPoly::FPoly(v48));
                    FPoly::SplitInHalf(v47, v12);
                    *((unsigned int *)(v15 + node * 4)) = v12;
                    node += 1;
                    v14 = node;
                }
                v50 = FMemStack::PushBytes(&GMem, 472, 16);
                v18 = (!v50 ? NULL : (unsigned int)FPoly::FPoly(v50));
                v9 = v18;
                v52 = FMemStack::PushBytes(&GMem, 472, 16);
                if (v52)
                {
                    v40 = (unsigned int)FPoly::FPoly(v52);
                    v19 = v40;
                    v8 = v40;
                    iter += 1;
                    break;
                }
                else
                {
                    v40 = NULL;
                    v19 = NULL;
                    v8 = 0;
                    iter += 1;
                    break;
                }
            default:
LABEL_100346be:
                v40 = v19;
                goto LABEL_100346c1;
            }
        }
LABEL_100346c1:
        iter += 1;
    }
    v53 = idx2;
    v54 = a0;
    if (v53 > 0)
        sub_10034530(v54, v11, 1, v53, v16, a5, a6, a7);
    if (node > 0)
        sub_10034530(v54, v11, 0, node, v15, a5, a6, a7);
    FMemMark::Pop(&v4);
    v55 = _ccall(v25, v26, (unsigned int)v27, 0);
    *((unsigned int *)(unsigned int)v55) = v21;
    return;
}

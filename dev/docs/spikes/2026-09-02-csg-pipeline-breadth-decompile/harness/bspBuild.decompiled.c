// bspBuild @ 0x10035ef0  size=347
class class UModel {
} class UModel;

class enum EBspOptimization {
} enum EBspOptimization;

typedef struct struct_0 {
    char padding_0[448];
    unsigned int field_1c0;
} struct_0;

extern unsigned int g_10140164;
extern char GMem;
extern char FPlane::PlaneDot;
extern char GNull;

void UEditorEngine::bspBuild(void* this, class UModel *idx, enum EBspOptimization arg_1, int arg_2, int arg_3)
{
    unsigned long v22;  // ldt
    unsigned long v23;  // gdt
    int index;  // edx
    struct_0 *v33;  // eax
    unsigned long long v34;  // 4125
    unsigned short v24;  // fs
    unsigned long long v25;  // 4203
    unsigned int v26;  // ebx
    unsigned int v27;  // esi
    unsigned int v28;  // edi
    unsigned long long v29;  // 4207
    int v30;  // edx
    unsigned int v31;  // edi
    unsigned int v0;  // [bp-0x64]
    int v1;  // [bp-0x5c]
    int v2;  // [bp-0x58]
    int v3;  // [bp-0x50]
    int v4;  // [bp-0x4c]
    unsigned int v5;  // [bp-0x48]
    unsigned int v6;  // [bp-0x44]
    unsigned int v7;  // [bp-0x40]
    unsigned int v8;  // [bp-0x3c]
    unsigned int v9;  // [bp-0x38]
    unsigned int v10;  // [bp-0x34]
    unsigned int v11;  // [bp-0x30]
    unsigned int v12;  // [bp-0x2c]
    unsigned int v13;  // [bp-0x28]
    int v14;  // [bp-0x1c]
    int v15;  // [bp-0x18]
    char *v16;  // [bp-0x14]
    unsigned int v17;  // [bp-0x10]
    unsigned int v18;  // [bp-0xc]
    unsigned int v19;  // [bp-0x8]
    char v20;  // [bp-0x4]
    int v21;  // [bp+0x8]

    v19 = 0xffffffff;
    v18 = sub_100c4c20;
    v25 = _ccall(v22, v23, (unsigned int)v24, 0);
    v17 = *((int *)(unsigned int)v25);
    v10 = v26;
    v9 = v27;
    v8 = v28;
    v7 = g_10140164 ^ &v20;
    v29 = _ccall(v22, v23, (unsigned int)v24, 0);
    *((unsigned int **)(unsigned int)v29) = &v17;
    v16 = &v7;
    v19 = 0;
    idx = *((int *)((int)idx[21] + 44));
    if (arg_2 == 1)
    {
        v6 = 0;
        v5 = 1;
    }
    else
    {
        if (arg_2)
            goto LABEL_10035f74;
        v30 = 0;
        while (1)
        {
            v15 = v30;
            if (v30 >= (int)idx[23])
                break;
            *((char *)(v30 * 64 + (int)idx[22] + 54)) = 0;
            v30 += 1;
        }
        (*((int *)(*((int *)this) + 0x200)))(idx, 1);
        v4 = 0;
        v3 = 0;
    }
    UModel::EmptyModel(idx, v3, v4);
LABEL_10035f74:
    if (*((int *)((int)idx[21] + 44)))
    {
        v11 = &GMem;
        v12 = *((int *)&GMem);
        v13 = *((int *)&FPlane::PlaneDot);
        v31 = FMemStack::PushBytes(&GMem, *((int *)((int)idx[21] + 44)) * 4, 16);
        index = 0;
        while (1)
        {
            v14 = index;
            if (index >= *((int *)((int)idx[21] + 44)))
                break;
            v33 = *((int *)((int)idx[21] + 40)) + index * 472;
            if (v33->field_1c0)
                *((struct_0 **)(v31 + index * 4)) = v33;
            index += 1;
        }
        sub_10034530(idx, -0x1, 3, *((int *)((int)idx[21] + 44)), v31, v21, arg_1, arg_2);
        if (!arg_2)
        {
            (*((int *)(*((int *)this) + 0x200)))(idx, 1);
            (*((int *)(*((int *)this) + 520)))(idx);
        }
        FMemMark::Pop(&v11);
    }
    v2 = (int)idx[23];
    v1 = idx;
    v0 = 760;
    FOutputDevice::Logf(*((int *)&GNull), L"bspBuild built %i convex polys into %i nodes");
    v34 = _ccall(v22, v23, (unsigned int)v24, 0);
    *((unsigned int *)(unsigned int)v34) = v17;
    return;
}

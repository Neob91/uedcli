// bspUnlinkPolys @ 0x100371d0  size=132
class class UModel {
} class UModel;

extern unsigned int g_10140164;

void UEditorEngine::bspUnlinkPolys(void* this, class UModel *idx)
{
    unsigned long v7;  // ldt
    unsigned long v8;  // gdt
    unsigned short v9;  // fs
    unsigned long long v10;  // 4147
    unsigned long long v11;  // 4167
    int v12;  // edx
    unsigned long long v13;  // 4122
    unsigned int v0;  // [bp-0x30]
    int v1;  // [bp-0x18]
    char *v2;  // [bp-0x14]
    unsigned int v3;  // [bp-0x10]
    unsigned int v4;  // [bp-0xc]
    unsigned int v5;  // [bp-0x8]
    char v6;  // [bp-0x4]

    v5 = 0xffffffff;
    v4 = sub_100c4d10;
    v10 = _ccall(v7, v8, (unsigned int)v9, 0);
    v3 = *((int *)(unsigned int)v10);
    v0 = g_10140164 ^ &v6;
    v11 = _ccall(v7, v8, (unsigned int)v9, 0);
    *((unsigned int **)(unsigned int)v11) = &v3;
    v2 = &v0;
    v5 = 0;
    UModel::Modify(idx, 0);
    *((unsigned int *)&idx[61]) = 1;
    v12 = 0;
    while (1)
    {
        v1 = v12;
        if (v12 >= *((int *)((int)idx[21] + 44)))
            break;
        *((int *)(*((int *)((int)idx[21] + 40)) + v12 * 472 + 452)) = v12;
        v12 += 1;
    }
    v13 = _ccall(v7, v8, (unsigned int)v9, 0);
    *((unsigned int *)(unsigned int)v13) = v3;
    return;
}

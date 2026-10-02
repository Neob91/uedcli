// bspBuildFPolys @ 0x10036090  size=149
class class UModel {
} class UModel;

extern unsigned int g_10140164;

void UEditorEngine::bspBuildFPolys(void* this, class UModel *arg_0, int arg_1, int arg_2)
{
    unsigned long v7;  // ldt
    unsigned long v8;  // gdt
    unsigned short v9;  // fs
    unsigned long long v10;  // 4149
    unsigned long long v11;  // 4169
    int v12;  // edi
    int v13;  // esi
    int v14;  // ebx
    int v15;  // edx
    unsigned long long v16;  // 4122
    unsigned int v0;  // [bp-0x30]
    int v1;  // [bp-0x18]
    char *v2;  // [bp-0x14]
    unsigned int v3;  // [bp-0x10]
    unsigned int v4;  // [bp-0xc]
    unsigned int v5;  // [bp-0x8]
    char v6;  // [bp-0x4]

    v5 = 0xffffffff;
    v4 = sub_100c4c40;
    v10 = _ccall(v7, v8, (unsigned int)v9, 0);
    v3 = *((int *)(unsigned int)v10);
    v0 = g_10140164 ^ &v6;
    v11 = _ccall(v7, v8, (unsigned int)v9, 0);
    *((unsigned int **)(unsigned int)v11) = &v3;
    v2 = &v0;
    v5 = 0;
    sub_10015760(0, g_10140164 ^ &v6, v12, v13, v14);
    if ((int)arg_0[23])
        sub_10033bb0(arg_0, arg_2);
    if (!arg_1)
    {
        v15 = 0;
        while (1)
        {
            v1 = v15;
            if (v15 >= *((int *)((int)arg_0[21] + 44)))
                break;
            *((int *)(*((int *)((int)arg_0[21] + 40)) + v15 * 472 + 452)) = v15;
            v15 += 1;
        }
    }
    v16 = _ccall(v7, v8, (unsigned int)v9, 0);
    *((unsigned int *)(unsigned int)v16) = v3;
    return;
}

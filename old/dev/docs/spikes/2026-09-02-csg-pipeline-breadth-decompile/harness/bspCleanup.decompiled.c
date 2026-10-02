// bspCleanup @ 0x10036160  size=99
class class UModel {
} class UModel;

extern unsigned int g_10140164;

void UEditorEngine::bspCleanup(void* this, class UModel *arg_0)
{
    unsigned long v6;  // ldt
    unsigned long v7;  // gdt
    unsigned short v8;  // fs
    unsigned long long v9;  // 4189
    unsigned long long v10;  // 4193
    unsigned long long v11;  // 4122
    unsigned int v0;  // [bp-0x2c]
    char *v1;  // [bp-0x14]
    unsigned int v2;  // [bp-0x10]
    unsigned int v3;  // [bp-0xc]
    unsigned int v4;  // [bp-0x8]
    char v5;  // [bp-0x4]

    v4 = 0xffffffff;
    v3 = sub_100c4c60;
    v9 = _ccall(v6, v7, (unsigned int)v8, 0);
    v2 = *((int *)(unsigned int)v9);
    v0 = g_10140164 ^ &v5;
    v10 = _ccall(v6, v7, (unsigned int)v8, 0);
    *((unsigned int **)(unsigned int)v10) = &v2;
    v1 = &v0;
    v4 = 0;
    if ((int)arg_0[23] > 0)
        sub_10032100(arg_0, 0, -0x1);
    v11 = _ccall(v6, v7, (unsigned int)v8, 0);
    *((unsigned int *)(unsigned int)v11) = v2;
    return;
}

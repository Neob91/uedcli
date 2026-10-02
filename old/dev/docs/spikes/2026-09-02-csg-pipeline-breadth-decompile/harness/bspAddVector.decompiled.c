// bspAddVector @ 0x10035530  size=122
class class FVector {
} class FVector;

class class UModel {
} class UModel;

extern unsigned int g_10140164;

int UEditorEngine::bspAddVector(void* this, class UModel *arg_0, class FVector *arg_1, int arg_2)
{
    unsigned long v7;  // ldt
    unsigned long v8;  // gdt
    unsigned short v9;  // fs
    unsigned long long v10;  // 4185
    unsigned long long v11;  // 4189
    unsigned int v12;  // eax
    unsigned long long v13;  // 4122
    void* v0;  // [bp-0x34]
    unsigned int v1;  // [bp-0x2c]
    char *v2;  // [bp-0x14]
    unsigned int v3;  // [bp-0x10]
    unsigned int v4;  // [bp-0xc]
    unsigned int v5;  // [bp-0x8]
    char v6;  // [bp-0x4]

    v5 = 0xffffffff;
    v4 = sub_100c4bd0;
    v10 = _ccall(v7, v8, (unsigned int)v9, 0);
    v3 = *((int *)(unsigned int)v10);
    v1 = g_10140164 ^ &v6;
    v11 = _ccall(v7, v8, (unsigned int)v9, 0);
    *((unsigned int **)(unsigned int)v11) = &v3;
    v2 = &v1;
    v5 = 0;
    v0 = this;
    v12 = sub_10031ae0(arg_0 + 30, arg_1, (!arg_2 ? 970045207 : 933741996), 1);
    v13 = _ccall(v7, v8, (unsigned int)v9, 0);
    *((unsigned int *)(unsigned int)v13) = v3;
    return v12;
}

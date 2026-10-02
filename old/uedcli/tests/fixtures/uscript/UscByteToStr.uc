class UscByteToStr expands Actor;

function string Foo()
{
    local byte B;
    local string S;

    B = 1;
    S = string(B);
    B = 2;
    return S;
}

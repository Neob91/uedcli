class UscAssertObjToStr expands Actor;

function string Foo()
{
    local int X;
    local string S;

    X = 1;
    assert(X == 1);
    S = string(Level);
    X = 2;
    assert(X == 2);
    return S;
}

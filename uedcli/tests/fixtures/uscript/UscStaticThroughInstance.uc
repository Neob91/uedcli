class UscStaticThroughInstance expands Actor;

static function int Bar(int X)
{
    return X + 1;
}

function int Foo(UscStaticThroughInstance P)
{
    return P.static.Bar(5);
}

function int Foo2(UscStaticThroughInstance P)
{
    return P.Bar(5);
}

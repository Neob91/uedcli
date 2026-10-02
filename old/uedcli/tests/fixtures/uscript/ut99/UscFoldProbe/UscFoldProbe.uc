class UscFoldProbe expands Object;

var float w;

function TestVarFloatTarget()
{
    local float x;
    x = 44 + w;
}

function TestVarIntTarget()
{
    local int i;
    i = 44 + w;
}

function TestCallFloatTarget()
{
    local float x;
    x = 256 * FRand();
}

function TestCallIntTarget()
{
    local int i;
    i = 256 * FRand();
}

function TestCallPlusFloatTarget()
{
    local float x;
    x = 44 + FRand();
}

function TestCallPlusIntTarget()
{
    local int i;
    i = 44 + FRand();
}

function TestForInitFloatTarget()
{
    local float x;
    for (x = 44 + w; x < 100; x += 1) {
    }
}

function TestForInitIntTarget()
{
    local int i;
    for (i = 44 + w; i < 100; i += 1) {
    }
}

defaultproperties
{
}

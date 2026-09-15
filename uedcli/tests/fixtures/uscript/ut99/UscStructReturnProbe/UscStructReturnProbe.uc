class UscStructReturnProbe expands Object;

struct Point {
    var int X;
    var int Y;
};

function Point MakePoint(int x, int y)
{
    local Point p;
    p.X = x;
    p.Y = y;
    return p;
}

defaultproperties
{
}

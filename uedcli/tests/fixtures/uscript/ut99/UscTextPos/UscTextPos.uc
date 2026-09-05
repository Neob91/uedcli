class UscTextPos extends Object;

function int Alpha(int x)
{
	return Beta(x) + 1;
}

final function int Beta(int y)
{
	local int z;
	z = y * 2;
	return z;
}

simulated final function string Gamma(string s)
{
	return s $ s;
}

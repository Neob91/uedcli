//=============================================================================
// PlatonicsBuilder.
//=============================================================================
class PlatonicsBuilder expands BrushBuilder;

var() float Radius;
var() enum _Stellate
{
	DB_NoStellate,
	DB_Stellate1,
	DB_Stellate2
} StellateType;
var() float StellatePercent;
var() name GroupName;
var() enum _Platonic
{
	DB_Tetrahedron,
	DB_Cube,
	DB_Octahedron,
	DB_Dodecahedron,
    DB_Icosahedron
} PlatonicType;

function Extrapolate3( int a, int b, int c, int Count, float Radius )
{
	local int im;
	local vector m;
	m = GetVertex(a)+GetVertex(b);
	m += GetVertex(c);
	m = normal(m) * (Radius * StellatePercent / 100.0);
	if( Count>1 )
	{
		im=Vertexv( m);
		Extrapolate3(a,b,im,Count-1,Radius);
		Extrapolate3(b,c,im,Count-1,Radius);
		Extrapolate3(c,a,im,Count-1,Radius);
	}
	else
		Poly3i(+1,a,b,c);
}

function Extrapolate4( int a, int b, int c, int d, int Count, float Radius )
{
	local int im;
	local vector m;
	m = GetVertex(a)+GetVertex(b);
	m += GetVertex(c);
	m += GetVertex(d);
	m = normal(m) * Radius * (StellatePercent / 100.0);
	if( Count>1 )
	{
		im=Vertexv(m);
		Extrapolate3(a,b,im,Count-1,Radius);
		Extrapolate3(b,c,im,Count-1,Radius);
		Extrapolate3(c,d,im,Count-1,Radius);
		Extrapolate3(d,a,im,Count-1,Radius);
	}
	else
		Poly4i(+1,a,b,c,d);
}

function Extrapolate5( int a, int b, int c, int d, int e,int Count, float Radius )
{
	local int im;
	local vector m;

	m = GetVertex(a)+GetVertex(b);
	m += GetVertex(c);
	m += GetVertex(d);
	m += GetVertex(e);
	m = normal(m) * Radius * (StellatePercent / 100.0);
	if( Count>1 )
	{
		im=Vertexv(m);
		Extrapolate3(a,b,im,Count-1,Radius);
		Extrapolate3(b,c,im,Count-1,Radius);
		Extrapolate3(c,d,im,Count-1,Radius);
		Extrapolate3(d,e,im,Count-1,Radius);
		Extrapolate3(e,a,im,Count-1,Radius);
	}
	else
	{
//		Poly3i(+1,a,c,b);
//		Poly3i(+1,c,a,d);
//		Poly3i(+1,d,e,a);
		PolyBegin( 1, 'Cap' );
		Polyi(a);
		Polyi(b);
		Polyi(c);
		Polyi(d);
		Polyi(e);
		PolyEnd();
	}
}

function BuildTetrahedron( float R, int SphereExtrapolation )
{

	vertex3f(0,0,R);
	vertex3f(R,0,-R/2);
	vertex3f(-R*0.5,-R*0.8660254,-R/2);
	vertex3f(-R*0.5,R*0.8660254,-R/2);

	Extrapolate3(0,2,1,SphereExtrapolation,R);
	Extrapolate3(0,3,2,SphereExtrapolation,R);
	Extrapolate3(0,1,3,SphereExtrapolation,R);
	Extrapolate3(1,2,3,SphereExtrapolation,R);
}


function BuildCube( float R, int SphereExtrapolation )
{
	local float dR;

	dR = 0.70710678 * R;
	vertex3f(dR, dR, dR);
	vertex3f(dR, dR,-dR);
	vertex3f(dR,-dR,-dR);
	vertex3f(dR,-dR, dR);
	vertex3f(-dR, dR, dR);
	vertex3f(-dR, dR,-dR);
	vertex3f(-dR,-dR,-dR);
	vertex3f(-dR,-dR, dR);

	Extrapolate4(3,2,1,0,SphereExtrapolation,R);
	Extrapolate4(4,5,6,7,SphereExtrapolation,R);
	Extrapolate4(1,5,4,0,SphereExtrapolation,R);
	Extrapolate4(2,6,5,1,SphereExtrapolation,R);
	Extrapolate4(3,7,6,2,SphereExtrapolation,R);
	Extrapolate4(0,4,7,3,SphereExtrapolation,R);
}

function BuildOctahedron( float R, int SphereExtrapolation )
{
	vertex3f( R,0,0);
	vertex3f(-R,0,0);
	vertex3f(0, R,0);
	vertex3f(0,-R,0);
	vertex3f(0,0, R);
	vertex3f(0,0,-R);

	Extrapolate3(2,1,4,SphereExtrapolation,R);
	Extrapolate3(1,3,4,SphereExtrapolation,R);
	Extrapolate3(3,0,4,SphereExtrapolation,R);
	Extrapolate3(0,2,4,SphereExtrapolation,R);
	Extrapolate3(1,2,5,SphereExtrapolation,R);
	Extrapolate3(3,1,5,SphereExtrapolation,R);
	Extrapolate3(0,3,5,SphereExtrapolation,R);
	Extrapolate3(2,0,5,SphereExtrapolation,R);
}

function BuildIcosahedron( float R, int SphereExtrapolation )
{
	local float f;
	f = R / 100.0;
vertex3f(f*72.369629, f*-52.516766, f*-44.710696);
vertex3f(f*89.463058, f*0, f*44.710696);
vertex3f(f*27.707169, f*-85.065559, f*44.710696);
vertex3f(f*27.707169, f*85.065559, f*44.710696);
vertex3f(f*0, f*0, f*100);
vertex3f(f*-27.707169, f*-85.065559, f*-44.710696);
vertex3f(f*-72.369629, f*-52.516766, f*44.710696);
vertex3f(f*0, f*0, f*-100);
vertex3f(f*-89.463058, f*0, f*-44.710696);
vertex3f(f*72.369629, f*52.516766, f*-44.710696);
vertex3f(f*-27.707169, f*85.065559, f*-44.710696);
vertex3f(f*-72.369629, f*52.516766, f*44.710696);

Extrapolate3(0,1,2,SphereExtrapolation,R);
Extrapolate3(1,3,4,SphereExtrapolation,R);
Extrapolate3(0,2,5,SphereExtrapolation,R);
Extrapolate3(2,4,6,SphereExtrapolation,R);
Extrapolate3(0,5,7,SphereExtrapolation,R);
Extrapolate3(5,6,8,SphereExtrapolation,R);
Extrapolate3(0,7,9,SphereExtrapolation,R);
Extrapolate3(7,8,10,SphereExtrapolation,R);
Extrapolate3(0,9,1,SphereExtrapolation,R);
Extrapolate3(9,10,3,SphereExtrapolation,R);
Extrapolate3(4,2,1,SphereExtrapolation,R);
Extrapolate3(11,4,3,SphereExtrapolation,R);
Extrapolate3(6,5,2,SphereExtrapolation,R);
Extrapolate3(11,6,4,SphereExtrapolation,R);
Extrapolate3(8,7,5,SphereExtrapolation,R);
Extrapolate3(11,8,6,SphereExtrapolation,R);
Extrapolate3(10,9,7,SphereExtrapolation,R);
Extrapolate3(11,10,8,SphereExtrapolation,R);
Extrapolate3(3,1,9,SphereExtrapolation,R);
Extrapolate3(11,3,10,SphereExtrapolation,R);
}

function BuildDodecahedron( float R, int SphereExtrapolation )
{
	local float f;
	f = R / 100.0;
vertex3f(f*-33.333333333333, f*-57.7350269, f*-74.5355992);
vertex3f(f*-87.2677996, f*-35.6822089, f*-33.333333333333);
vertex3f(f*-87.2677996, f*35.6822089, f*-33.333333333333);
vertex3f(f*-33.333333333333, f*57.7350269, f*-74.5355992);
vertex3f(f*0, f*0, f*-100);
vertex3f(f*-12.7322004, f*93.4173257, f*33.333333333333);
vertex3f(f*12.7322004, f*93.4173257, f*-33.333333333333);
vertex3f(f*-74.5355992, f*57.7350269, f*33.333333333333);
vertex3f(f*74.5355992, f*57.7350269, f*-33.333333333333);
vertex3f(f*66.666666666666, f*0, f*-74.5355992);
vertex3f(f*74.5355992, f*-57.7350269, f*-33.333333333333);
vertex3f(f*12.7322004, f*-93.4173257, f*-33.333333333333);
vertex3f(f*-12.7322004, f*-93.4173257, f*33.333333333333);
vertex3f(f*-74.5355992, f*-57.7350269, f*33.333333333333);
vertex3f(f*-66.666666666666, f*0, f*74.5355992);
vertex3f(f*33.333333333333, f*-57.7350269, f*74.5355992);
vertex3f(f*0, f*0, f*100);
vertex3f(f*87.2677996, f*-35.6822089, f*33.333333333333);
vertex3f(f*87.2677996, f*35.6822089, f*33.333333333333);
vertex3f(f*33.333333333333, f*57.7350269, f*74.5355992);

Extrapolate5(0,1,2,3,4,SphereExtrapolation,R);
Extrapolate5(5,6,3,2,7,SphereExtrapolation,R);
Extrapolate5(8,9,4,3,6,SphereExtrapolation,R);
Extrapolate5(10,11,0,4,9,SphereExtrapolation,R);
Extrapolate5(12,13,1,0,11,SphereExtrapolation,R);
Extrapolate5(14,7,2,1,13,SphereExtrapolation,R);
Extrapolate5(13,12,15,16,14,SphereExtrapolation,R);
Extrapolate5(11,10,17,15,12,SphereExtrapolation,R);
Extrapolate5(9,8,18,17,10,SphereExtrapolation,R);
Extrapolate5(6,5,19,18,8,SphereExtrapolation,R);
Extrapolate5(7,14,16,19,5,SphereExtrapolation,R);
Extrapolate5(19,16,15,17,18,SphereExtrapolation,R);
}

event bool Build()
{
	local int SphereExtrapolation;

	if( Radius <= 0 || StellatePercent < 0)
		return BadParameters();

	if (StellateType == DB_Stellate1)
		SphereExtrapolation = 2;
	else if (StellateType == DB_Stellate2)
		SphereExtrapolation = 3;
	else
		SphereExtrapolation = 0;

	BeginBrush( false, GroupName );
	if (PlatonicType == DB_Tetrahedron)
		BuildTetrahedron( Radius, SphereExtrapolation );
	else if (PlatonicType == DB_Cube)
		BuildCube( Radius, SphereExtrapolation );
	else if (PlatonicType == DB_Octahedron)
		BuildOctahedron( Radius, SphereExtrapolation );
	else if (PlatonicType == DB_Icosahedron)
		BuildIcosahedron( Radius, SphereExtrapolation );
	else // if (PlatonicType == DB_Dodecahedron)
		BuildDodecahedron( Radius, SphereExtrapolation );
	return EndBrush();
}

defaultproperties
{
      Radius=256.000000
      StellateType=DB_NoStellate
      StellatePercent=100.000000
      GroupName="Platonics"
      PlatonicType=DB_Dodecahedron
      BitmapFilename="BBDavesPlato"
      ToolTip="5 Platonic Solids Builders"
}

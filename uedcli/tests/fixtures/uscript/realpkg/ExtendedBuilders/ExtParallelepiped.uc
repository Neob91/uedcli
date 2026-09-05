//=============================================================================
// ParallelepipedBuilder: Builds a cube brush with options to slant it
// based on Epic's CubeBuilder
// modified by Tarquin tarquindarkling@bigfoot.com
//=============================================================================
class ExtParallelepiped
	extends BrushBuilder;

var() float Height, Width, Breadth;
var() float WallThickness;
var() float BaseX , BaseY , InclineX , InclineY , DipX, DipY ;
var() name GroupName;
var() bool Hollow;
var() bool Tessellated;

function BuildCube( int Direction, vector LRi, vector LRj, vector LRk, bool _tessellated )
{
	local int n,i,j,k;
	n = GetVertexCount();

	for( i=-1; i<2; i+=2 )
		for( j=-1; j<2; j+=2 )
			for( k=-1; k<2; k+=2 )
				Vertexv( i*LRi/2 + j*LRj/2 + k*LRk/2 );

	/*
	for( i=-1; i<2; i+=2 )
		for( j=-1; j<2; j+=2 )
			for( k=-1; k<2; k+=2 )
				Vertex3f( i*dx/2, j*dy/2, k*dz/2 );
	*/
	// If the user wants a Tessellated cube, create the sides out of tris instead of quads.
	if( _tessellated )
	{
		Poly3i(Direction,n+0,n+1,n+3);
		Poly3i(Direction,n+0,n+3,n+2);
		Poly3i(Direction,n+2,n+3,n+7);
		Poly3i(Direction,n+2,n+7,n+6);
		Poly3i(Direction,n+6,n+7,n+5);
		Poly3i(Direction,n+6,n+5,n+4);
		Poly3i(Direction,n+4,n+5,n+1);
		Poly3i(Direction,n+4,n+1,n+0);
		Poly3i(Direction,n+3,n+1,n+5);
		Poly3i(Direction,n+3,n+5,n+7);
		Poly3i(Direction,n+0,n+2,n+6);
		Poly3i(Direction,n+0,n+6,n+4);
	}
	else
	{
		Poly4i(Direction,n+0,n+1,n+3,n+2);
		Poly4i(Direction,n+2,n+3,n+7,n+6);
		Poly4i(Direction,n+6,n+7,n+5,n+4);
		Poly4i(Direction,n+4,n+5,n+1,n+0);
		Poly4i(Direction,n+3,n+1,n+5,n+7);
		Poly4i(Direction,n+0,n+2,n+6,n+4);
	}
}

event bool Build()
{
	local vector Ri , Rj , Rk ;

	// check input 
	if( Height<=0 || Width<=0 || Breadth<=0 )
		return BadParameters();
	if( Hollow && (Height<=WallThickness || Width<=WallThickness || Breadth<=WallThickness) )
		return BadParameters();
	if( Hollow && Tessellated )
		return BadParameters("The 'Tessellated' option can't be specified with the 'Hollow' option.");

	/*
	BaseSkewX = 64 ;
	BaseSkewY = 32 ;
	InclineX = 64;
	InclineY = 128 ;
	DipX = 32;
	DipY = 64 ;
	*/

	// set vectors
	Ri.x = Breadth ;	Rj.x = BaseY ;		Rk.x = InclineX ;
	Ri.y = BaseX;	Rj.y = Width ;		Rk.y = InclineY ;
	Ri.z = DipX ;	Rj.z = DipY ;		Rk.z = Height ;


	BeginBrush( false, GroupName );
	BuildCube( +1, Ri, Rj, Rk, Tessellated );
	if( Hollow )
	{
		Ri.x -= WallThickness ;
		Rj.x *= (( Breadth - WallThickness ) / Breadth ) ;
		Rk.x *= (( Breadth - WallThickness ) / Breadth ) ;

		Ri.y *= (( Width - WallThickness ) / Width ) ;
		Rj.y -= WallThickness ;
		Rk.y *= (( Width - WallThickness ) / Width ) ;

		Ri.z *= (( Height - WallThickness ) / Height ) ;
		Rj.z *= (( Height - WallThickness ) / Height ) ;
		Rk.z -= WallThickness ;	

		BuildCube( -1, Ri, Rj, Rk, Tessellated );
	}
	return EndBrush();
}

defaultproperties
{
      Height=256.000000
      Width=256.000000
      Breadth=256.000000
      WallThickness=0.000000
      BaseX=0.000000
      BaseY=0.000000
      InclineX=0.000000
      InclineY=0.000000
      DipX=0.000000
      DipY=0.000000
      GroupName="Parellelepiped"
      Hollow=False
      Tessellated=False
      BitmapFilename="BBExtParallel"
      ToolTip="Slanted Cube"
}

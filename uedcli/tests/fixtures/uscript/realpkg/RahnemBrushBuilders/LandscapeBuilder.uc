//=============================================================================
// LandscapeBuilder: Builds a 3D cube brush, with a tessellated sides.
// Built using TerrainBuilder code included with UnrealEd 2.
// Amendments written by Peter "Rahnem" Respondek - 08/04/2001.
//=============================================================================
class LandscapeBuilder
	extends BrushBuilder;

var() float Height, Width, Breadth;
var() int WidthSegments, BreadthSegments, DepthSegments;		// How many breaks to have in each direction
var() name GroupName;
var() bool Terrain;								// Tesselates top if False

function BuildTerrain( int Direction, float dx, float dy, float dz, 
			     int WidthSeg, int BreadthSeg, int DepthSeg, bool _Terrain )
{
	local int n,x,y,z;
	local float WidthStep, BreadthStep, DepthStep;

	// Initialise variables
	WidthStep   = dx / WidthSeg;
	BreadthStep = dy / BreadthSeg;
	DepthStep   = dz / DepthSeg;

	//
	// TOP
	//

	n = GetVertexCount();
	
	// If use selects Terrain as True, top is created as two polys 
	if (_Terrain)
	{
		for ( x = -1; x < 2; x+=2 )
			for ( y = -1; y < 2; y+=2 )
				Vertex3f( x*dx/2, y*dy/2, dz/2 );

		Poly3i(Direction,n+0,n+2,n+1);
		Poly3i(Direction,n+3,n+1,n+2);			 
	}
	else
	{
		n = GetVertexCount();

		// Create vertices for sky
		for( x = 0 ; x < WidthSeg + 1 ; x++ )
			for( y = 0 ; y < BreadthSeg + 1 ; y++ )
				Vertex3f( (WidthStep * x) - dx/2, (BreadthStep * y) - dy/2, (dz/2) );

		// Create the sky as a mesh of triangles
		for( x = 0 ; x < WidthSeg ; x++ )
			for( y = 0 ; y < BreadthSeg ; y++ )
			{
				Poly3i(Direction,
					(n+y)		+ ((BreadthSeg+1) * (x+1)),
					((n+1)+y)   + ((BreadthSeg+1) * x),
					(n+y) 	+ ((BreadthSeg+1) * x),
					'sky');
				Poly3i(-Direction,
					(n+y)		+ ((BreadthSeg+1) * (x+1)),
					((n+1)+y)   + ((BreadthSeg+1) * x),
					((n+1)+y)	+ ((BreadthSeg+1) * (x+1)),
					'sky');
			}
	}

	//
	// BOTTOM
	//

	n = GetVertexCount();

	// Create vertices for ground
	for( x = 0 ; x < WidthSeg + 1 ; x++ )
		for( y = 0 ; y < BreadthSeg + 1 ; y++ )
			Vertex3f( (WidthStep * x) - dx/2, (BreadthStep * y) - dy/2, -(dz/2) );

	// Create the ground as a mesh of triangles
	for( x = 0 ; x < WidthSeg ; x++ )
		for( y = 0 ; y < BreadthSeg ; y++ )
		{
			Poly3i(-Direction,
				(n+y)		+ ((BreadthSeg+1) * x),
				(n+y)		+ ((BreadthSeg+1) * (x+1)),
				((n+1)+y)	+ ((BreadthSeg+1) * (x+1)),
				'ground');
			Poly3i(-Direction,
				(n+y) 	+ ((BreadthSeg+1) * x),
				((n+1)+y)   + ((BreadthSeg+1) * (x+1)),
				((n+1)+y)   + ((BreadthSeg+1) * x),
				'ground');
		}

	//
	// BREADTH SIDE
	//

	n = GetVertexCount();

	// Create vertices for wall
	for( y = 0 ; y < BreadthSeg + 1 ; y++ )
		for( z = 0 ; z < DepthSeg + 1 ; z++ )
			Vertex3f( (dx/2), (BreadthStep * y) - dy/2, (DepthStep * z) - dz/2 );

	// Create the wall as a mesh of triangles
	for( y = 0 ; y < BreadthSeg ; y++ )
		for( z = 0 ; z < DepthSeg ; z++ )
		{
			Poly3i(Direction,
				(n+z)		+ ((DepthSeg+1) * y),
				(n+z)		+ ((DepthSeg+1) * (y+1)),
				((n+1)+z)	+ ((DepthSeg+1) * (y+1)),
				'wall');
			Poly3i(Direction,
				(n+z) 	+ ((DepthSeg+1) * y),
				((n+1)+z)   + ((DepthSeg+1) * (y+1)),
				((n+1)+z)   + ((DepthSeg+1) * y),
				'wall');
		}

	n = GetVertexCount();

	// Create vertices for wall
	for( y = 0 ; y < BreadthSeg + 1 ; y++ )
		for( z = 0 ; z < DepthSeg + 1 ; z++ )
			Vertex3f( -(dx/2), (BreadthStep * y) - dy/2, (DepthStep * z) - dz/2 );

	// Create the wall as a mesh of triangles
	for( y = 0 ; y < BreadthSeg ; y++ )
		for( z = 0 ; z < DepthSeg ; z++ )
		{
			Poly3i(-Direction,
				(n+z)		+ ((DepthSeg+1) * (y+1)),
				((n+1)+z)   + ((DepthSeg+1) * y),
				(n+z) 	+ ((DepthSeg+1) * y),
				'sky');
			Poly3i(Direction,
				(n+z)		+ ((DepthSeg+1) * (y+1)),
				((n+1)+z)   + ((DepthSeg+1) * y),
				((n+1)+z)	+ ((DepthSeg+1) * (y+1)),
				'sky');
		}

	//
	// WIDTH SIDE
	//

	n = GetVertexCount();

	// Create vertices for wall
	for( x = 0 ; x < WidthSeg + 1 ; x++ )
		for( z = 0 ; z < DepthSeg + 1 ; z++ )
			Vertex3f( (WidthStep * x) - dx/2, (dy/2), (DepthStep * z) - dz/2 );

	// Create the wall as a mesh of triangles
	for( x = 0 ; x < WidthSeg ; x++ )
		for( z = 0 ; z < DepthSeg ; z++ )
		{
			Poly3i(-Direction,
				(n+z)		+ ((DepthSeg+1) * (x+1)),
				((n+1)+z)   + ((DepthSeg+1) * x),
				(n+z) 	+ ((DepthSeg+1) * x),
				'sky');
			Poly3i(Direction,
				(n+z)		+ ((DepthSeg+1) * (x+1)),
				((n+1)+z)   + ((DepthSeg+1) * x),
				((n+1)+z)	+ ((DepthSeg+1) * (x+1)),
				'sky');
		}

	n = GetVertexCount();

	// Create vertices for wall
	for( x = 0 ; x < WidthSeg + 1 ; x++ )
		for( z = 0 ; z < DepthSeg + 1 ; z++ )
			Vertex3f( (WidthStep * x) - dx/2, -(dy/2), (DepthStep * z) - dz/2 );

	// Create the wall as a mesh of triangles
	for( x = 0 ; x < WidthSeg ; x++ )
		for( z = 0 ; z < DepthSeg ; z++ )
		{
			Poly3i(Direction,
				(n+z)		+ ((DepthSeg+1) * x),
				(n+z)		+ ((DepthSeg+1) * (x+1)),
				((n+1)+z)	+ ((DepthSeg+1) * (x+1)),
				'wall');
			Poly3i(Direction,
				(n+z) 	+ ((DepthSeg+1) * x),
				((n+1)+z)   + ((DepthSeg+1) * (x+1)),
				((n+1)+z)   + ((DepthSeg+1) * x),
				'wall');
		}
}


event bool Build()
{
	if( Height<=0 || Width<=0 || Breadth<=0 || WidthSegments<=0 || BreadthSegments <=0 || DepthSegments<=0 )
		return BadParameters();

	BeginBrush( false, GroupName );
	BuildTerrain( +1, Breadth, Width, Height, WidthSegments, BreadthSegments, DepthSegments, Terrain );
	return EndBrush();
}

defaultproperties
{
      Height=256.000000
      Width=256.000000
      Breadth=512.000000
      WidthSegments=4
      BreadthSegments=2
      DepthSegments=1
      GroupName="Landscape"
      Terrain=True
      BitmapFilename="BBLandscape"
      ToolTip="BSP Based Landscape"
}

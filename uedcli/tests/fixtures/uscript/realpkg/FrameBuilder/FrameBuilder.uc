// ============================================================
// FrameBuilder.FrameBuilder
//  Coded by JohnMcL(speedman@cryogen.com)
//  (c) 12/16/00
// ============================================================

class FrameBuilder expands BrushBuilder;

var() float Height, Width, Breadth;
var() float WallThickness;
var() name GroupName;
var() bool MakeInnerSheet;
var() bool Tessellated;

function BuildFrame( int Direction, float dx, float dy, float dz, float thickness, bool _tessellated, bool _makeinner )
{
	local int n,i,j,k;
	n = GetVertexCount();

	for( i=-1; i<2; i+=2 )
		for( j=-1; j<2; j+=2 )
			for( k=-1; k<2; k+=2 )
				Vertex3f( i*dx/2, j*dy/2, k*dz/2 );


for( i=-1; i<2; i+=2 )
	for( j=-1; j<2; j+=2 )
		for( k=-1; k<2; k+=2 )
			Vertex3f( i*(dx-Thickness)/2, j*dy/2, k*(dz-thickness)/2 );
if(_makeinner)
	for( i=-1; i<2; i+=2 )
		for( k=-1; k<2; k+=2 )
			Vertex3f( i*(dx-Thickness)/2, 0, k*(dz-thickness)/2 );

  if(_tessellated)
  {
	Poly3i(Direction,n+5,n+1,n+13);
	Poly3i(Direction,n+9,n+13,n+1);
	Poly3i(Direction,n+12,n+4,n+5);
	Poly3i(Direction,n+12,n+5,n+13);
	Poly3i(Direction,n+8,n+4,n+12);
	Poly3i(Direction,n+0,n+4,n+8);
	Poly3i(Direction,n+0,n+9,n+1);
	Poly3i(Direction,n+0,n+8,n+9);

	Poly3i(Direction,n+3,n+7,n+11);
	Poly3i(Direction,n+7,n+15,n+11);
	Poly3i(Direction,n+7,n+6,n+15);
	Poly3i(Direction,n+15,n+6,n+14);
	Poly3i(Direction,n+14,n+6,n+2);
	Poly3i(Direction,n+2,n+10,n+14);
	Poly3i(Direction,n+10,n+2,n+3);
	Poly3i(Direction,n+3,n+11,n+10);

	Poly3i(Direction,n+1,n+5,n+3);
	Poly3i(Direction,n+5,n+7,n+3);
	Poly3i(Direction,n+5,n+4,n+7);
	Poly3i(Direction,n+4,n+6,n+7);
	Poly3i(Direction,n+4,n+0,n+6);
	Poly3i(Direction,n+2,n+6,n+0);
	Poly3i(Direction,n+0,n+1,n+3);
	Poly3i(Direction,n+3,n+2,n+0);

	Poly3i(Direction,n+8,n+12,n+14);
	Poly3i(Direction,n+14,n+10,n+8);
	Poly3i(Direction,n+9,n+8,n+10);
	Poly3i(Direction,n+10,n+11,n+9);
	Poly3i(Direction,n+11,n+13,n+9);
	Poly3i(Direction,n+11,n+15,n+13);
	Poly3i(Direction,n+12,n+15,n+14);
	Poly3i(Direction,n+15,n+12,n+13);

	if (_makeinner)
	  {
		Poly3i(Direction,n+16,n+17,n+19,,0x00000108);
		Poly3i(Direction,n+19,n+18,n+16,,0x00000108);
	  }
  }
  else
  {
	Poly4i(Direction,n+1,n+5,n+7,n+3);
	Poly4i(Direction,n+5,n+4,n+6,n+7);
	Poly4i(Direction,n+0,n+2,n+6,n+4);
	Poly4i(Direction,n+3,n+2,n+0,n+1);
	
	Poly4i(Direction,n+9,n+11,n+15,n+13);
	Poly4i(Direction,n+9,n+8,n+10,n+11);
	Poly4i(Direction,n+8,n+12,n+14,n+10);
	Poly4i(Direction,n+13,n+15,n+14,n+12);

	Poly4i(Direction,n+1,n+0,n+8,n+9);
	Poly4i(Direction,n+0,n+4,n+12,n+8);
	Poly4i(Direction,n+4,n+5,n+13,n+12);
	Poly4i(Direction,n+5,n+1,n+9,n+13);

	Poly4i(Direction,n+3,n+7,n+15,n+11);
	Poly4i(Direction,n+7,n+6,n+14,n+15);
	Poly4i(Direction,n+6,n+2,n+10,n+14);
	Poly4i(Direction,n+2,n+3,n+11,n+10);

	if(_makeinner)
		Poly4i(Direction,n+16,n+17,n+19,n+18,,0x00000108);
  }
}

Function Bool Build()
{
	if( Height<=0 || Width<=0 || Breadth<=0 || WallThickness<=0)
		return BadParameters();
	if (Breadth<=WallThickness||Height<=WallThickness)
		return BadParameters();
	BeginBrush( false, GroupName );
	BuildFrame( +1, Breadth, Width, Height, WallThickness, Tessellated ,MakeInnerSheet );
	return EndBrush();
}

defaultproperties
{
      Height=256.000000
      Width=64.000000
      Breadth=256.000000
      WallThickness=64.000000
      GroupName="Frame"
      MakeInnerSheet=True
      Tessellated=False
      BitmapFilename="BBFrame"
      ToolTip="Frame"
}

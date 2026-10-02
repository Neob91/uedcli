class UscW expands Object;
var int mi;
var float mf;
var bool mb;
var string ms;

function int Add(int a,int b){ return a+b; }
final function int Mul(int a,int b){ return a*b; }
function int UseMember(){ return mi + 1; }
function SetMember(int v){ mi = v; }
function float FAdd(float a,float b){ return a+b; }
function float Mixed(float a,int b){ return a + b; }
function bool Cmp(int a){ return a >= 10; }
function bool Logic(bool a,bool b){ return a && b; }
function string Concat(string a,string b){ return a $ b; }
function int Neg(int a){ return -a; }
function bool Not(bool a){ return !a; }
function int Bits(int a,int b){ return a & b; }
function IfTest(int a){ if(a>0){ mi=1; } else { mi=2; } }
function ElseIf(int a){ if(a>0){ mi=1; } else if(a<0){ mi=2; } else { mi=3; } }
function WhileTest(int n){ local int i; i=0; while(i<n){ i=i+1; } }
function ForTest(int n){ local int i; for(i=0;i<n;i=i+1){ mi=i; } }
function BreakCont(int n){ local int i; for(i=0;i<n;i=i+1){ if(i==3) break; if(i==1) continue; mi=i; } }
function CallScript(int a){ mi = Add(a,2); }
function CallFinal(int a){ mi = Mul(a,2); }
function int CastIF(float f){ return int(f); }
function float CastFI(int i){ return float(i); }

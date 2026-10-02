import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"dev/docs/spikes/2026-08-31-native-parity-report/harness"))
import parity_compare as PC
sub=ROOT/"_scratch/actor-parity/03_nyc_unatcohq/N8/maps/03_nyc_unatcohq"
PC.build_native_model(sub)

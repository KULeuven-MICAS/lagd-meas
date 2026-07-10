import os
from pathlib import Path

current_dir =  Path(os.path.dirname(os.path.realpath(__file__)))
os.system(f"export PYTHONPATH=$PYTHONPATH:{current_dir}")

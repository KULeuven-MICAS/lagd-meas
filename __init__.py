import os
from pathlib import Path

os.system(f"export PYTHONPATH=$PYTHONPATH:{Path(os.path.realpath(__file__)).parent}")

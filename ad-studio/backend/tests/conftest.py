import os
import sys
import tempfile
from pathlib import Path

os.environ["ADF_DATA_DIR"] = tempfile.mkdtemp(prefix="adforge_test_")
os.environ["ADF_DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

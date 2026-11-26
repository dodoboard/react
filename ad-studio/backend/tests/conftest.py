import os
import sys
import tempfile
from pathlib import Path

os.environ["ADF_DATA_DIR"] = tempfile.mkdtemp(prefix="adforge_test_")
os.environ["ADF_DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    from app.models import init_db
    init_db()

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    """A fresh copy of the demo dataset in a temp dir, so tests never touch data\\ or cache\\."""
    from generate_data import generate

    data = tmp_path_factory.mktemp("data")
    generate(data)
    os.environ["PROMO_DATA_DIR"] = str(data)
    os.environ["PROMO_CACHE_DIR"] = str(tmp_path_factory.mktemp("cache"))
    os.environ["LLM_PROVIDER"] = "none"
    os.environ["SIGNING_SECRET"] = "test-secret-with-at-least-32-bytes!!"
    return data


@pytest.fixture(scope="session")
def client(dataset):
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as test_client:
        yield test_client

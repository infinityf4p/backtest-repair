"""Workspace-owned test directories also work with Windows restricted tokens."""
from pathlib import Path
import uuid
import pytest


@pytest.fixture
def tmp_path():
    path = Path(__file__).resolve().parents[1] / '.test-work' / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path

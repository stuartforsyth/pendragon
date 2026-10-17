import os
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import rules as rules_module  # noqa: E402
from core.names import find_data_file, parse_names_file  # noqa: E402
from core.npc import Generator  # noqa: E402


@pytest.fixture(scope="session")
def rules():
    return rules_module.load_rules(os.path.join(ROOT, "data"))


@pytest.fixture(scope="session")
def generator(rules):
    return Generator(parse_names_file(find_data_file(ROOT)), rules)


@pytest.fixture
def client(tmp_path):
    """The web app against copies of the shipped data (never the user's files)."""
    from web.app import create_app
    data = tmp_path / "data"
    data.mkdir()
    for f in ("rules.json", "examplecombat.json"):
        shutil.copy(f"{ROOT}/data/{f}", data / f)
    app = create_app(ROOT, sessions_dir=str(tmp_path / "sessions"), data_dir=str(data))
    with TestClient(app) as c:
        c.tmp = tmp_path
        yield c


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()

import os
import sys

import pytest

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

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

needs_spider = pytest.mark.skipif(not config.SPIDER_TABLES.exists(),
                                  reason="Spider dataset not downloaded (see README)")

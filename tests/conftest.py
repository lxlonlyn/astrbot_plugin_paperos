from __future__ import annotations

import sys
from pathlib import Path

from tests.support.astrbot_stub import install_astrbot_stub


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

install_astrbot_stub()


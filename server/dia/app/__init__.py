"""
Sensor Portal API Application
"""

import sys
from pathlib import Path

pub_src = Path(__file__).resolve().parents[2] / "pub" / "src"
if pub_src.exists() and str(pub_src) not in sys.path:
    sys.path.insert(0, str(pub_src))

__version__ = "0.1.0"

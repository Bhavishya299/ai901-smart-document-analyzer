"""Make the project root importable when pytest runs from any folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

"""Migration runner: run SQL files against app DB (SQLite: SQLITE_APP_PATH)."""
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config.env import ensure_project_env

ensure_project_env(ROOT)

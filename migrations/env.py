"""Migration runner: run SQL files against POSTGRES_APP_URL."""
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

# Load .env from config/env/ or project root
for p in [ROOT / "config" / "env" / ".env", ROOT / ".env"]:
    if p.exists():
        load_dotenv(p)
        break

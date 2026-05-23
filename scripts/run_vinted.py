"""Launcher: ``python scripts/run_vinted.py`` from the repo root."""

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


if __name__ == "__main__":
    from bots.vinted.main import main
    main()

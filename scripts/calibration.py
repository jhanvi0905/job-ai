"""Print how well the system's approvals match your decisions in Notion. Read-only, no model calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ledger.db import Ledger  # noqa: E402
from src.ledger.feedback import calibration, format_calibration  # noqa: E402

if __name__ == "__main__":
    print(format_calibration(calibration(Ledger())))

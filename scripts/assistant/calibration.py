"""Print how well the system's approvals match your decisions in Notion. Read-only, no model calls."""


from jobai.core.ledger.db import Ledger  # noqa: E402
from jobai.core.ledger.feedback import calibration, format_calibration  # noqa: E402

if __name__ == "__main__":
    print(format_calibration(calibration(Ledger())))

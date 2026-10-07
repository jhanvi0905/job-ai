"""Write data/routing_preferences.json from the current ledger. Read-only, no model calls."""


from jobai.assistant.orchestrator.preferences import save_routing_preferences  # noqa: E402
from jobai.core.ledger.db import Ledger  # noqa: E402

if __name__ == "__main__":
    prefs = save_routing_preferences(Ledger())
    print(f"wrote data/routing_preferences.json — {len(prefs['rejection_patterns'])} priority bands, "
          f"{len(prefs['reject_reasons'])} reject reasons")

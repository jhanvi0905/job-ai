"""Test safety net: the suite can never spend money or touch live services.

Two independent layers, both automatic for every test:
  1. API keys are replaced with an obviously-invalid value, so even a code path
     that reached a real endpoint would be rejected (and would be a bug we'd see).
  2. The requests transport itself raises, so any un-mocked HTTP call fails
     loudly and immediately instead of quietly billing AI/ML API or writing to
     the live Notion workspace.

Tests that need HTTP behaviour must inject a fake session/transport (see
tests/fakes.py). If a test fails with LiveNetworkBlocked, that test — or the
code under test — was about to make a real call.
"""
import pytest


class LiveNetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_live_services(monkeypatch):
    for var in ("AIMLAPI_KEY", "NOTION_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(var, "test-invalid-key")

    def _blocked(self, request, **kwargs):
        raise LiveNetworkBlocked(
            f"Blocked real HTTP call in a test: {request.method} {request.url}. "
            "Inject a fake session instead (tests/fakes.py)."
        )

    monkeypatch.setattr("requests.adapters.HTTPAdapter.send", _blocked)
    yield

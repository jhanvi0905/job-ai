import pytest

from tests.conftest import LiveNetworkBlocked


def test_network_guard_is_active():
    """Proves the guard works, so a silent regression can't re-enable spending."""
    import requests

    with pytest.raises(LiveNetworkBlocked):
        requests.get("https://api.aimlapi.com/v1/models", timeout=1)
    with pytest.raises(LiveNetworkBlocked):
        requests.post("https://api.notion.com/v1/pages", json={}, timeout=1)


def test_api_keys_are_neutralised(monkeypatch):
    import os

    assert os.environ["AIMLAPI_KEY"] == "test-invalid-key"
    assert os.environ["NOTION_API_KEY"] == "test-invalid-key"

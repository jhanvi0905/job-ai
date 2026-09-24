"""Scripted stand-ins for the model provider. No sockets, no keys, no cost.

A FakeSession replays a fixed list of outcomes (a response object, or an
exception to raise) and records every request body it was sent, so tests can
assert exactly how many HTTP attempts the gateway made — including that a
blocked/over-budget call made none.
"""
from __future__ import annotations

import json as _json


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, text="", json_error=False):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text or (_json.dumps(body) if body is not None else "")
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._body


def ok_body(content, model="gpt-4o-mini-2024-07-18", prompt_tokens=120, completion_tokens=30, cost=0.0001, finish="stop"):
    """A provider-shaped success payload. `content` may be a dict (serialised) or a raw string."""
    text = content if isinstance(content, str) else _json.dumps(content)
    return {
        "model": model,
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        "meta": {"usage": {"usd_spent": cost}},
    }


def ok(content, **kw):
    return FakeResponse(200, ok_body(content, **kw))


class FakeSession:
    def __init__(self, script):
        self.script = list(script)
        self.requests: list[dict] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append(json)
        if not self.script:
            raise AssertionError("FakeSession script exhausted — the code made more HTTP attempts than the test expected")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

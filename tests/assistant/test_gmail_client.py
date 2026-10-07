"""Gmail client against a scripted session: auth handling, paging, and the read-only guarantees."""
import json

import pytest

from jobai.assistant.inbox.gmail import SCOPE, GmailAuthError, GmailReader


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Session:
    def __init__(self, gets, posts=None):
        self.gets, self.posts, self.get_calls, self.post_calls = list(gets), list(posts or [Resp(200, {"access_token": "AT"})]), [], []

    def get(self, url, params=None, headers=None, timeout=None):
        self.get_calls.append((url, params, headers))
        return self.gets.pop(0)

    def post(self, url, data=None, timeout=None):
        self.post_calls.append(data)
        return self.posts.pop(0)


@pytest.fixture
def files(tmp_path):
    c, t = tmp_path / "c.json", tmp_path / "t.json"
    c.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "sec"}}))
    t.write_text(json.dumps({"refresh_token": "RT"}))
    return c, t


def reader(session, files):
    return GmailReader(session=session, credentials_path=files[0], token_path=files[1], sleep=lambda s: None)


def test_missing_credentials_or_token_gives_a_clear_human_action(tmp_path):
    r = GmailReader(session=Session([]), credentials_path=tmp_path / "no.json", token_path=tmp_path / "no2.json")
    with pytest.raises(GmailAuthError, match="gmail_auth.py"):
        r.list_message_ids(3)


def test_listing_pages_through_results_and_uses_a_bounded_query(files):
    s = Session([Resp(200, {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "n"}), Resp(200, {"messages": [{"id": "c"}]})])
    assert reader(s, files).list_message_ids(14) == ["a", "b", "c"]
    q = s.get_calls[0][1]["q"]
    assert "newer_than:14d" in q and "-in:sent" in q
    assert s.get_calls[0][2]["Authorization"] == "Bearer AT"
    assert s.post_calls[0]["grant_type"] == "refresh_token" and s.post_calls[0]["refresh_token"] == "RT"


def test_only_metadata_is_ever_requested_never_bodies(files):
    payload = {"id": "m1", "threadId": "t1", "internalDate": "1760000000000", "snippet": "  Thanks   for applying ",
               "payload": {"headers": [{"name": "From", "value": "Acme Recruiting <No-Reply@Acme.com>"}, {"name": "Subject", "value": "Your  application"}]}}
    s = Session([Resp(200, payload)])
    m = reader(s, files).get_message("m1")
    params = dict(s.get_calls[0][1])
    assert params["format"] == "metadata" and ("format", "full") not in s.get_calls[0][1]
    assert (m.sender_name, m.sender_email, m.sender_domain) == ("Acme Recruiting", "no-reply@acme.com", "acme.com")
    assert (m.subject, m.snippet) == ("Your application", "Thanks for applying")


def test_an_expired_access_token_is_refreshed_once_and_the_call_retried(files):
    s = Session([Resp(401), Resp(200, {"messages": [{"id": "a"}]})], posts=[Resp(200, {"access_token": "AT1"}), Resp(200, {"access_token": "AT2"})])
    assert reader(s, files).list_message_ids(3) == ["a"]
    assert [c[2]["Authorization"] for c in s.get_calls] == ["Bearer AT1", "Bearer AT2"]


def test_a_revoked_refresh_token_is_a_loud_auth_error_not_a_crash_loop(files):
    s = Session([], posts=[Resp(400, {"error": "invalid_grant"})])
    with pytest.raises(GmailAuthError, match="revoked"):
        reader(s, files).list_message_ids(3)


def test_transient_5xx_is_retried_then_succeeds(files):
    s = Session([Resp(503), Resp(200, {"messages": []})])
    assert reader(s, files).list_message_ids(3) == []


def test_the_scope_is_read_only():
    assert SCOPE.endswith("gmail.readonly")


# ------------------------------------------------------------- auth script
def test_auth_url_requests_only_the_read_only_scope_and_offline_access():
    from scripts.assistant.gmail_auth import build_auth_url
    url = build_auth_url("cid", "http://127.0.0.1:1", "st")
    assert "gmail.readonly" in url and "access_type=offline" in url and "state=st" in url
    assert "gmail.modify" not in url and "mail.google.com" not in url


def test_token_file_is_private_and_missing_refresh_token_is_refused(tmp_path):
    import stat

    from scripts.assistant.gmail_auth import exchange_code, save_token
    p = tmp_path / "t.json"
    save_token({"refresh_token": "RT"}, p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600

    class S:
        def post(self, *a, **k):
            return Resp(200, {"access_token": "x"})

    with pytest.raises(SystemExit):
        exchange_code(S(), {"client_id": "a", "client_secret": "b"}, "code", "http://127.0.0.1:1")

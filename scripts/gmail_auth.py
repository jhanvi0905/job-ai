"""ONE-TIME Gmail sign-in (read-only). You run this yourself; Claude never sees your password or token.

Before running:
  1. console.cloud.google.com -> create a project -> APIs & Services -> enable "Gmail API".
  2. OAuth consent screen: External, add jarora0905@gmail.com as a TEST USER.
  3. Credentials -> Create credentials -> OAuth client ID -> "Desktop app" -> download JSON.
  4. Save it as  data/gmail_credentials.json  (gitignored).

Then:  python scripts/gmail_auth.py
A browser opens; approve "View your email messages and settings" (gmail.readonly — it cannot
send, delete or change anything). The refresh token is saved to data/gmail_token.json (mode 600).
"""
import json
import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src.inbox.gmail import CREDENTIALS_PATH, SCOPE, TOKEN_PATH, TOKEN_URL  # noqa: E402

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
    })


def exchange_code(session, client: dict, code: str, redirect_uri: str) -> dict:
    resp = session.post(TOKEN_URL, data={
        "code": code, "client_id": client["client_id"], "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    if "refresh_token" not in body:
        raise SystemExit("Google returned no refresh token. Revoke this app at myaccount.google.com/permissions and retry.")
    return {"refresh_token": body["refresh_token"], "scope": body.get("scope", SCOPE)}


def save_token(token: dict, path: Path = TOKEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token, f)


def main() -> None:
    if not CREDENTIALS_PATH.exists():
        raise SystemExit(f"Missing {CREDENTIALS_PATH}. See the steps at the top of this file.")
    raw = json.loads(CREDENTIALS_PATH.read_text())
    client = raw.get("installed") or raw.get("web") or raw
    state, result = secrets.token_urlsafe(16), {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = parse_qs(urlparse(self.path).query)
            result["code"], result["state"] = (q.get("code") or [None])[0], (q.get("state") or [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and return to the terminal.")

        def log_message(self, *a):  # keep the auth code out of the terminal
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = build_auth_url(client["client_id"], redirect, state)
    print("Opening your browser to approve READ-ONLY Gmail access...\nIf it doesn't open, visit:\n" + url)
    webbrowser.open(url)
    server.handle_request()
    if result.get("state") != state or not result.get("code"):
        raise SystemExit("Sign-in did not complete (state mismatch or no code). Nothing was saved.")
    save_token(exchange_code(requests, client, result["code"], redirect))
    print(f"Saved {TOKEN_PATH}. Try: python scripts/sync_inbox.py --dry-run --lookback 14")


if __name__ == "__main__":
    main()

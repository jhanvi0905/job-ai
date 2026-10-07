"""Logging + error reporting for the product API and worker.

* `configure_logging(service)` — one JSON object per line on stdout (Fly ships
  stdout to its log stream). Every line carries `request_id` and `user_id` from
  the current request/task context.
* `init_sentry(service)` — optional (SENTRY_DSN). No PII by default, no request
  bodies, no local variables in stack frames, and `scrub_event` strips auth
  headers, cookies and any resume/JD-shaped fields before an event leaves.

Rule for the codebase: never log resume text, job-description text, prompts,
model output or tokens. Log ids and counts. `_RedactFilter` is a backstop for
bearer tokens/JWTs only; it cannot recognise free text, so the rule stands.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from typing import Any

# A mutable dict (not separate vars) so a value set inside a dependency that runs
# in a worker thread (copied context) is still visible to the request's other
# threads and to the access-log middleware: they share the same dict object.
_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("log_ctx", default=None)

_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
# Field names whose values are resume / JD / prompt / credential content.
SENSITIVE_KEYS = frozenset({
    "authorization", "cookie", "set-cookie", "x-signature", "apikey", "password", "token", "access_token",
    "refresh_token", "secret", "text", "resume", "resume_text", "description", "jd", "jd_text", "prompt",
    "messages", "content", "summary", "proposal", "bullets", "data", "body",
})
_FILTERED = "[Filtered]"


def new_context(**values: Any) -> contextvars.Token:
    return _ctx.set({"request_id": None, "user_id": None, **values})


def reset_context(token: contextvars.Token) -> None:
    _ctx.reset(token)


def bind(**values: Any) -> None:
    """Attach fields (e.g. user_id) to the current request/task context."""
    ctx = _ctx.get()
    if ctx is None:
        _ctx.set(dict(values))
    else:
        ctx.update(values)
    if "user_id" in values and values["user_id"] is not None:
        try:
            import sentry_sdk

            sentry_sdk.set_user({"id": str(values["user_id"])})  # opaque id only, no email
        except Exception:  # noqa: BLE001 — sentry optional
            pass


def current() -> dict[str, Any]:
    return dict(_ctx.get() or {})


def redact(text: str) -> str:
    return _JWT.sub(_FILTERED, _BEARER.sub("Bearer " + _FILTERED, text))


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _ctx.get() or {}
        record.request_id = ctx.get("request_id")
        record.user_id = ctx.get("user_id")
        return True


class JsonFormatter(logging.Formatter):
    _RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id", "user_id", "service"}

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact(record.getMessage())[:4000],
            "service": self.service,
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }
        for key, value in record.__dict__.items():  # `extra=` fields
            if key not in self._RESERVED and not key.startswith("_"):
                out[key] = _FILTERED if key.lower() in SENSITIVE_KEYS else value
        if record.exc_info:
            out["exc"] = redact(self.formatException(record.exc_info))[:8000]
        return json.dumps(out, default=str)


def configure_logging(service: str, level: str | None = None) -> None:
    """Idempotent. LOG_FORMAT=text gives human-readable lines for local dev."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_product_handler", False):
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler._product_handler = True  # type: ignore[attr-defined]
    handler.addFilter(_RedactFilter())
    if os.environ.get("LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [req=%(request_id)s user=%(user_id)s] %(message)s"))
    else:
        handler.setFormatter(JsonFormatter(service))
    root.addHandler(handler)
    root.setLevel(level or os.environ.get("LOG_LEVEL", "INFO").upper())
    # uvicorn's own access log duplicates ours (and logs query strings); keep its error log.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True


# ------------------------------------------------------------------ sentry
def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return _FILTERED
    if isinstance(value, dict):
        return {k: (_FILTERED if str(k).lower() in SENSITIVE_KEYS else _scrub(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v, depth + 1) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value


def scrub_event(event: dict, _hint: dict | None = None) -> dict:
    """Sentry before_send / before_send_transaction: drop request bodies, auth
    headers, cookies, query strings and anything resume/JD-shaped."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: (_FILTERED if k.lower() in SENSITIVE_KEYS else v) for k, v in headers.items()}
    for key in ("extra", "contexts", "tags"):
        if key in event:
            event[key] = _scrub(event[key])
    crumbs = event.get("breadcrumbs")
    if isinstance(crumbs, dict) and isinstance(crumbs.get("values"), list):
        for c in crumbs["values"]:
            if isinstance(c, dict):
                if isinstance(c.get("message"), str):
                    c["message"] = redact(c["message"])
                if "data" in c:
                    c["data"] = _scrub(c["data"])
    for exc in (event.get("exception") or {}).get("values", []) or []:
        if isinstance(exc, dict) and isinstance(exc.get("value"), str):
            exc["value"] = redact(exc["value"])[:1000]
        for frame in ((exc.get("stacktrace") or {}).get("frames") or []) if isinstance(exc, dict) else []:
            frame.pop("vars", None)  # belt and braces: include_local_variables is already off
    if isinstance(event.get("logentry"), dict) and isinstance(event["logentry"].get("message"), str):
        event["logentry"]["message"] = redact(event["logentry"]["message"])
    return event


def init_sentry(service: str) -> bool:
    """Returns True if Sentry was initialised. Safe to call without SENTRY_DSN."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "dev"),
        release=os.environ.get("GIT_SHA") or None,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
        include_local_variables=False,   # frames could hold resume / JD text
        max_request_body_size="never",   # uploads and JSON bodies never leave the box
        before_send=scrub_event,
        before_send_transaction=scrub_event,
    )
    sentry_sdk.set_tag("service", service)
    return True

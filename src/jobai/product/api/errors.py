"""One error shape for every failure: {"error": {"code", "message"}}."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from jobai.engine.ai.provider import BudgetExceeded, LLMError
from jobai.product.services.billing import InsufficientCredits
from jobai.product.services.quota import QuotaExceeded
from jobai.product.services.resume import ResumeError, StorageError

_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict",
          413: "too_large", 415: "unsupported_media_type", 422: "validation_error", 429: "rate_limited",
          502: "upstream_error"}


def _body(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        resp = _body(exc.status_code, _CODES.get(exc.status_code, "error"), str(exc.detail))
        resp.headers.update(exc.headers or {})
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return _body(422, "validation_error", "invalid request", details=[
            {"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()])

    @app.exception_handler(QuotaExceeded)
    async def _quota(_: Request, exc: QuotaExceeded):
        return _body(429, "quota_exceeded", str(exc), kind=exc.kind, limit=exc.limit)

    @app.exception_handler(InsufficientCredits)
    async def _credits(_: Request, exc: InsufficientCredits):
        return _body(402, "insufficient_credits", str(exc))

    @app.exception_handler(ResumeError)
    async def _resume(_: Request, exc: ResumeError):
        return _body(exc.status, _CODES.get(exc.status, "bad_request"), str(exc))

    @app.exception_handler(StorageError)
    async def _storage(_: Request, exc: StorageError):
        return _body(502, "storage_error", "file storage is unavailable; try again")

    @app.exception_handler(BudgetExceeded)
    async def _budget(_: Request, exc: BudgetExceeded):
        return _body(429, "budget_exceeded", "model budget reached; try again later")

    @app.exception_handler(LLMError)
    async def _llm(_: Request, exc: LLMError):
        return _body(502, "llm_error", f"model call failed ({exc.outcome})")

    @app.exception_handler(LookupError)
    async def _lookup(_: Request, exc: LookupError):
        return _body(404, "not_found", str(exc) or "not found")

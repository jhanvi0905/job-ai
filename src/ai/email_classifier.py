"""Model fallback for emails the rules could not classify. Input is deliberately
tiny (company, role, sender domain, subject, ~250-char preview): the model never
sees message bodies, because Gmail metadata is all we fetch."""
from __future__ import annotations

from pathlib import Path

from src.ai.provider import LLMProvider
from src.config import load_models
from src.ledger.codes import EMAIL_CLASSES

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "classify_email_v1.txt"


def _validate(raw: dict) -> None:
    if raw.get("class") not in EMAIL_CLASSES:
        raise ValueError(f"class must be one of {sorted(EMAIL_CLASSES)}")
    c = raw.get("confidence")
    if not isinstance(c, (int, float)) or isinstance(c, bool) or not 0 <= c <= 1:
        raise ValueError("confidence must be a number between 0 and 1")


def classify_email(*, company: str, role: str, domain: str, subject: str, snippet: str,
                   provider: LLMProvider, message_id: str) -> tuple[str, float]:
    routing = load_models()["routing"]["classify_email"]
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        company=company, role=role or "unknown", domain=domain, subject=subject[:150], snippet=snippet[:250]
    )
    raw = provider._chat(  # noqa: SLF001 — same single-call-site convention as the job classifiers
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="classify_email",
        job_id=message_id,
        prompt_version="classify_email_v1",
        context={"snippet_chars": len(snippet[:250])},
        validate=_validate,
    )
    return raw["class"], float(raw["confidence"])

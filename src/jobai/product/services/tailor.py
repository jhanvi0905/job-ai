"""Resume tailoring with a hard no-invention guarantee.

The model proposes bullet rewrites, each citing evidence ids from the user's own
achievement bank. CODE then verifies every bullet before the user ever sees it:
it must cite at least one id from the evidence set the model was shown, and
any number it contains must already appear in the original bullet or cited
evidence. Anything that fails is dropped (and counted) — the prompt asks the
model to behave, the validator makes sure it did.

Results are cached per (resume, JD, bank, prompt, model): a repeat request is
free and consumes no quota.
"""
from __future__ import annotations

import hashlib
import io
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.core.config import load_models
from jobai.core.paths import PROMPTS_DIR
from jobai.engine.achievements.retrieval import retrieve_achievements
from jobai.engine.ai.provider import LLMProvider
from jobai.product.db.models import Achievement, Job, ResumeVersion, TailorRun, User, UserJobEvaluation
from jobai.product.services import billing, quota
from jobai.product.services.resume import list_achievements

PROMPT_VERSION = "tailor_resume_v1"
PROMPT_PATH = PROMPTS_DIR / f"{PROMPT_VERSION}.txt"
TOP_K = 8
MAX_BULLETS = 8
MAX_JD_CHARS = 4000
MAX_RESUME_CHARS = 6000
_NUM = re.compile(r"\d[\d,.]*")


def _index(achievements: list[Achievement]) -> list[dict]:
    """Rows -> the dict shape retrieve_achievements scores; ids are str(row.id)."""
    return [
        {"id": str(a.id), "title": a.title, "summary": a.summary,
         **{k: list(v) for k, v in a.fields.items() if isinstance(v, list)}}
        for a in achievements
    ]


def _bank_signature(achievements: list[Achievement]) -> str:
    return hashlib.sha256("|".join(f"{a.id}:{a.title}:{a.summary}" for a in achievements).encode()).hexdigest()


def compute_input_hash(resume: ResumeVersion, job: Job, bank_sig: str, model: str) -> str:
    parts = [resume.content_hash, job.description_hash, bank_sig, PROMPT_VERSION, model]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def validate_bullets(raw_bullets: list, allowed: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Split model output into (kept, dropped). `allowed` maps evidence id -> its text.

    Pure function so the no-hallucination rule is directly testable."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in raw_bullets:
        if not isinstance(item, dict):
            dropped.append({"reason": "malformed", "item": str(item)[:200]})
            continue
        proposed = str(item.get("proposed") or "").strip()
        original = str(item.get("original") or "").strip()
        ids = [str(i) for i in (item.get("evidence_ids") or [])] if isinstance(item.get("evidence_ids"), list) else []
        reason = None
        if not proposed:
            reason = "empty"
        elif not ids:
            reason = "no_evidence"
        elif any(i not in allowed for i in ids):
            reason = "unknown_evidence_id"
        else:
            support = " ".join([original] + [allowed[i] for i in ids])
            supported_numbers = {n.strip(".,") for n in _NUM.findall(support)}
            if any(n.strip(".,") not in supported_numbers for n in _NUM.findall(proposed)):
                reason = "unsupported_number"
        if reason:
            dropped.append({"reason": reason, "proposed": proposed, "evidence_ids": ids})
        else:
            kept.append({"original": original, "proposed": proposed, "evidence_ids": ids})
    return kept, dropped


def propose_tailor(session: Session, user_id: int, job_id: int, resume_id: int, provider: LLMProvider) -> TailorRun:
    resume = session.scalar(select(ResumeVersion).where(ResumeVersion.id == resume_id, ResumeVersion.user_id == user_id))
    job = session.get(Job, job_id)
    if resume is None or job is None:
        raise LookupError("resume or job not found")
    achievements = list_achievements(session, user_id)
    if not achievements:
        raise ValueError("no achievements yet; upload and parse a resume first")
    routing = load_models()["routing"]["tailor_resume"]

    input_hash = compute_input_hash(resume, job, _bank_signature(achievements), routing["model"])
    cached = session.scalar(select(TailorRun).where(TailorRun.user_id == user_id, TailorRun.input_hash == input_hash))
    if cached:
        return cached  # cache hit: zero LLM calls, zero quota

    try:
        quota.consume(session, user_id, "tailor")
    except quota.QuotaExceeded:
        # Plan cap hit: pay with a credit if there is one; otherwise surface the 429.
        try:
            billing.spend(session, user_id, 1, reason="tailor", ref=f"tailor:{input_hash}")
        except billing.InsufficientCredits:
            raise quota.QuotaExceeded("tailor", quota.PLAN_LIMITS[session.get(User, user_id).plan]["tailor"]) from None

    ev = session.scalar(select(UserJobEvaluation).where(UserJobEvaluation.user_id == user_id, UserJobEvaluation.job_id == job_id))
    cls = (ev.classification if ev else None) or {}
    index = _index(achievements)
    top = retrieve_achievements(cls.get("role_family"), list(cls.get("key_requirements") or [job.title]), top_k=TOP_K, index=index)
    by_id = {a["id"]: a for a in index}
    chosen = [by_id[r.id] for r in top if r.id in by_id] or index[:TOP_K]
    allowed = {a["id"]: f"{a['title']} {a['summary']}" for a in chosen}

    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        title=job.title, company=job.company, description=job.description[:MAX_JD_CHARS],
        evidence="\n".join(f"[{a['id']}] {a['title']}: {a['summary']}" for a in chosen),
        resume_text=resume.text[:MAX_RESUME_CHARS],
    )
    raw = provider._chat(  # noqa: SLF001
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="tailor_resume",
        job_id=str(job_id),
        prompt_version=PROMPT_VERSION,
        validate=lambda r: _require_list(r),
    )
    kept, dropped = validate_bullets(raw["bullets"], allowed)
    run = TailorRun(
        user_id=user_id, job_id=job_id, resume_id=resume_id, input_hash=input_hash, status="proposed",
        proposal={"bullets": kept[:MAX_BULLETS], "dropped": dropped},
    )
    session.add(run)
    session.flush()
    return run


def _require_list(raw: dict) -> None:
    if not isinstance(raw.get("bullets"), list):
        raise ValueError("'bullets' must be a list")


def get_run(session: Session, user_id: int, run_id: int) -> TailorRun:
    run = session.scalar(select(TailorRun).where(TailorRun.id == run_id, TailorRun.user_id == user_id))
    if run is None:
        raise LookupError("tailor run not found")
    return run


def accept_tailor(session: Session, user_id: int, run_id: int, indices: list[int]) -> TailorRun:
    run = get_run(session, user_id, run_id)
    bullets = run.proposal.get("bullets", [])
    if not indices or any((not isinstance(i, int)) or i < 0 or i >= len(bullets) for i in indices):
        raise ValueError("indices must be a non-empty list of valid bullet positions")
    run.accepted = {"bullets": [bullets[i] for i in sorted(set(indices))]}
    run.status = "accepted"
    session.flush()
    return run


def render_docx(run: TailorRun) -> bytes:
    from docx import Document

    bullets = (run.accepted or {}).get("bullets") or []
    if not bullets:
        raise ValueError("no accepted bullets to render")
    doc = Document()
    doc.add_heading("Tailored resume bullets", level=1)
    for b in bullets:
        doc.add_paragraph(b["proposed"], style="List Bullet")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

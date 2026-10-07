"""Per-user evaluation of the shared catalog: the SaaS form of process_job.evaluate.

Same funnel (Stage 0 free filters -> Stage 1 triage -> Stage 3 deep match), but
every input is the user's own (rules, profile, evidence) and every outcome is a
`UserJobEvaluation` row scoped by user_id.

Invariants:
  * Conservation: each job considered ends with exactly one disposition.
  * Fail closed: a budget/quota/LLM failure is `deferred` or `errored`, NEVER a
    rejection, and the cache never treats those as an answer — they are retried.
  * Cache: a row is reused while (jd_hash, rules_sig) match; reuse costs nothing.
  * Failed LLM work refunds its quota unit — users pay for verdicts, not outages.

Each job is committed on its own, so a crash or one bad job never loses the rest.
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.core.config import load_models
from jobai.engine.achievements.retrieval import retrieve_achievements
from jobai.engine.ai.classifier import FIT_RANK, cap_fit_by_years, classify_job, triage_reject_code
from jobai.engine.ai.matcher import analyse_match
from jobai.engine.ai.outcomes import MATCH_FIT_RANK as _MATCH_FIT_RANK
from jobai.engine.ai.outcomes import llm_failure as _llm_failure
from jobai.engine.ai.provider import LLMProvider
from jobai.engine.jobs.filters import apply_filters
from jobai.engine.jobs.schemas import JobClassification, JobMatch, NormalizedJob
from jobai.product.db.models import Job, UsageCounter, UserJobEvaluation
from jobai.product.services import quota
from jobai.product.services.prefs import (
    achievement_index,
    load_prefs,
    profile_from_user,
    resolve_role_families,
    roles_for_choice,
    rules_from_prefs,
    rules_signature,
)
from jobai.product.services.quota import QuotaExceeded

logger = logging.getLogger(__name__)

DEFAULT_DEEP_TOP_N = 10
# Dispositions that are NOT answers: always retried, never served from cache.
_RETRYABLE = ("deferred", "errored")
DISPOSITIONS = ("filtered", "rejected", "triaged", "matched", "deferred", "errored")


@dataclass
class EvalSummary:
    run_id: str
    considered: int = 0
    cached: int = 0  # considered, but already had a valid answer: 0 LLM calls
    filtered: int = 0
    rejected: int = 0
    triaged: int = 0
    matched: int = 0
    deferred: int = 0
    errored: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def conserved(self) -> bool:
        """Every considered job is accounted for exactly once."""
        return self.considered == self.cached + sum(getattr(self, d) for d in DISPOSITIONS)


@dataclass
class _Context:
    """Everything user-specific, computed once per run."""
    rules: dict
    roles: dict
    profile: dict
    index: list[dict]
    sig: str


def _context(session: Session, user_id: int) -> _Context:
    prefs = load_prefs(session, user_id)
    index = achievement_index(session, user_id)
    choice = resolve_role_families(prefs, index)  # prefs, else inferred from achievements
    rules, profile = rules_from_prefs(prefs, choice), profile_from_user(session, user_id, prefs)
    return _Context(rules, roles_for_choice(prefs, choice), profile, index,
                    rules_signature(rules, profile, load_models()))


def _normalized(job: Job) -> NormalizedJob:
    nj = NormalizedJob.model_validate(job.normalized)
    nj.job_fingerprint, nj.description_hash, nj.description = job.fingerprint, job.description_hash, job.description
    return nj


def _is_valid(row: UserJobEvaluation | None, job: Job, sig: str) -> bool:
    return bool(row and row.jd_hash == job.description_hash and row.rules_sig == sig and row.disposition not in _RETRYABLE)


def _own_row(session: Session, user_id: int, job_id: int) -> UserJobEvaluation | None:
    return session.scalar(select(UserJobEvaluation).where(
        UserJobEvaluation.user_id == user_id, UserJobEvaluation.job_id == job_id))


def _store(session: Session, user_id: int, job: Job, sig: str, disposition: str, reason: str | None, *,
           classification: JobClassification | None = None, match: JobMatch | None = None,
           fit: str | None = None) -> UserJobEvaluation:
    """Upsert the single row for (user, job) and commit."""
    row = _own_row(session, user_id, job.id)
    if row is None:
        row = UserJobEvaluation(user_id=user_id, job_id=job.id)
        session.add(row)
    row.disposition, row.reason_code = disposition, reason
    row.classification = classification.model_dump() if classification else None
    row.match = match.model_dump() if match else None
    row.fit, row.fit_rank = fit, FIT_RANK.get(fit or "", 0)
    row.jd_hash, row.rules_sig = job.description_hash, sig
    session.commit()
    return row


def _refund(session: Session, user_id: int, kind: str) -> None:
    """Give back one quota unit when the LLM never produced a verdict."""
    row = session.get(UsageCounter, (user_id, quota._today(), kind))  # noqa: SLF001
    if row is not None and row.count > 0:
        row.count -= 1
        session.flush()


def _triage(session: Session, user_id: int, nj: NormalizedJob, provider: LLMProvider, ctx: _Context) -> JobClassification:
    quota.consume(session, user_id, "triage")
    try:
        return classify_job(nj, provider, profile=ctx.profile, rules=ctx.rules, roles=ctx.roles)
    except Exception:
        _refund(session, user_id, "triage")
        raise


def _deep_match(session: Session, user_id: int, nj: NormalizedJob, cls: JobClassification,
                provider: LLMProvider, ctx: _Context) -> tuple[JobMatch, str, str, str]:
    """Stage 3 + the same banding as process_job: final fit is the LOWER of the
    two stages, then the years cap. Returns (match, disposition, reason, fit)."""
    quota.consume(session, user_id, "deep_match")
    try:
        evidence = retrieve_achievements(cls.role_family, cls.key_requirements, index=ctx.index)
        result = analyse_match(nj, cls.key_requirements, evidence, provider, cls, profile=ctx.profile, rules=ctx.rules)
    except Exception:
        _refund(session, user_id, "deep_match")
        raise
    gates = ctx.rules["ai_gates"]
    stage1, stage3 = FIT_RANK.get(cls.fit or "plausible", 2), _MATCH_FIT_RANK.get(result.fit_band, 0)
    if stage3 > 0:
        result.fit_band = {1: "weak", 2: "plausible", 3: "strong"}[min(stage1, stage3)]
    result.fit_band = cap_fit_by_years(result.fit_band, cls.min_years_required, ctx.rules["experience"]["total_years"])
    result.priority = {"strong": "P1", "plausible": "P2"}.get(result.fit_band, "P3")
    rank = _MATCH_FIT_RANK.get(result.fit_band, 0)
    fit = "no" if result.fit_band == "blocked" else result.fit_band
    if rank < FIT_RANK[gates["min_match_fit"]] or result.recommended_action == "reject":
        code = "rejected_blocked" if result.fit_band == "blocked" else "rejected_weak" if rank < FIT_RANK[gates["min_match_fit"]] else "rejected_action"
        return result, "rejected", code, fit
    return result, "matched", "approved_match", fit


def _fail(session: Session, user_id: int, job: Job, sig: str, exc: Exception, summary: EvalSummary) -> str:
    """Record a non-verdict. Quota exhaustion and LLM/budget failures defer;
    everything else is an error. Neither is ever stored as a rejection."""
    if isinstance(exc, QuotaExceeded):
        disposition, code = "deferred", f"quota_{exc.kind}"
    else:
        disposition, code = _llm_failure(exc)
    summary.errors.append(f"{job.fingerprint}: {type(exc).__name__}: {exc}"[:200])
    _store(session, user_id, job, sig, disposition, code)
    return disposition


def evaluate_for_user(
    session: Session, user_id: int, provider: LLMProvider, *, max_jobs: int | None = None,
    run_id: str | None = None, deep_top_n: int = DEFAULT_DEEP_TOP_N,
) -> EvalSummary:
    """Evaluate active catalog jobs for one user. `max_jobs` bounds jobs that
    need work (cached ones are free and always counted); newest jobs first."""
    summary = EvalSummary(run_id=run_id or f"eval-{uuid.uuid4().hex[:10]}")
    ctx = _context(session, user_id)
    existing = {r.job_id: r for r in session.scalars(
        select(UserJobEvaluation).where(UserJobEvaluation.user_id == user_id))}
    jobs = session.scalars(select(Job).where(Job.active.is_(True)).order_by(Job.first_seen_at.desc(), Job.id.desc())).all()

    final: dict[int, str] = {}  # job_id -> disposition, tallied at the end
    pool: list[tuple[Job, NormalizedJob, JobClassification, int]] = []  # triaged candidates for Stage 3
    work = 0
    for job in jobs:
        if _is_valid(existing.get(job.id), job, ctx.sig):
            summary.considered += 1
            summary.cached += 1
            continue
        if max_jobs is not None and work >= max_jobs:
            continue
        work += 1
        summary.considered += 1
        try:
            nj = _normalized(job)
            result = apply_filters(nj, ctx.rules, ctx.roles)
            if not result.passed:
                _store(session, user_id, job, ctx.sig, "filtered", result.codes[0] if result.codes else "stage0_other", fit="no")
                final[job.id] = "filtered"
                continue
            cls = _triage(session, user_id, nj, provider, ctx)
            if not cls.relevant:
                code = triage_reject_code(cls, ctx.rules["ai_gates"])
                _store(session, user_id, job, ctx.sig, "rejected", code, classification=cls, fit=cls.fit or "no")
                final[job.id] = "rejected"
                continue
            _store(session, user_id, job, ctx.sig, "triaged", "approved_triage", classification=cls, fit=cls.fit)
            final[job.id] = "triaged"
            pool.append((job, nj, cls, FIT_RANK.get(cls.fit or "", 0)))
        except Exception as exc:  # noqa: BLE001 — one job's failure must not stop the run
            session.rollback()
            logger.warning("evaluation failed for user %s job %s", user_id, job.id, exc_info=True)
            final[job.id] = _fail(session, user_id, job, ctx.sig, exc, summary)

    # Stage 3 only for the best triage passes; the rest stay `triaged` (user can deep-match on demand).
    pool.sort(key=lambda item: item[3], reverse=True)
    for job, nj, cls, _rank in pool[:deep_top_n]:
        try:
            match, disposition, code, fit = _deep_match(session, user_id, nj, cls, provider, ctx)
            _store(session, user_id, job, ctx.sig, disposition, code, classification=cls, match=match, fit=fit)
            final[job.id] = disposition
        except QuotaExceeded as exc:
            session.rollback()
            summary.errors.append(f"{job.fingerprint}: {exc}")
            _store(session, user_id, job, ctx.sig, "triaged", "deep_match_quota", classification=cls, fit=cls.fit)
            break  # the cap is per day: no later job can succeed either
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            _, code = _llm_failure(exc)
            summary.errors.append(f"{job.fingerprint}: {type(exc).__name__}: {exc}"[:200])
            _store(session, user_id, job, ctx.sig, "triaged", f"match_{code}", classification=cls, fit=cls.fit)

    for disposition, n in Counter(final.values()).items():
        setattr(summary, disposition, n)
    return summary


def deep_match_job(session: Session, user_id: int, job_id: int, provider: LLMProvider) -> UserJobEvaluation:
    """On-demand Stage 3 for one job. Idempotent: a valid cached match is returned
    without spending quota. Raises QuotaExceeded / LLMError on failure (the API maps
    them to 429/503) and leaves any existing row untouched — never a rejection."""
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError(f"job {job_id} not found")
    ctx = _context(session, user_id)
    row = _own_row(session, user_id, job_id)
    usable = _is_valid(row, job, ctx.sig) and row is not None and row.disposition != "filtered"
    if usable and row.match:
        return row

    nj = _normalized(job)
    if usable and row.classification:
        cls = JobClassification(**row.classification)
    else:  # no triage on record (or the user overrides a Stage-0 filter): triage first
        cls = _triage(session, user_id, nj, provider, ctx)
        if not cls.relevant:
            return _store(session, user_id, job, ctx.sig, "rejected", triage_reject_code(cls, ctx.rules["ai_gates"]),
                          classification=cls, fit=cls.fit or "no")
        _store(session, user_id, job, ctx.sig, "triaged", "approved_triage", classification=cls, fit=cls.fit)
    match, disposition, code, fit = _deep_match(session, user_id, nj, cls, provider, ctx)
    return _store(session, user_id, job, ctx.sig, disposition, code, classification=cls, match=match, fit=fit)

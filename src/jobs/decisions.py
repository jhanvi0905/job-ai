"""Memory of AI verdicts, stored in the ledger's `verdicts` table (Phase 3).

Formerly a decisions.jsonl file; the ledger gives us joins with events and
human outcomes, and one place to back up. Rules below are unchanged.

Why this exists: Notion only holds jobs worth reviewing.

Notion only holds jobs worth reviewing (that's the whole point — no clutter),
so a job the AI rejected leaves no trace there. Without a memory, that same
job would be re-fetched, pass Stage 0, and be re-sent to the LLM every single
day. PRD success criterion: "a previously analysed unchanged job requires 0
new LLM calls".

A decision is reused only while (a) the job's description hash is unchanged
and (b) the *signature* still matches — a hash over everything that shapes the
verdict (candidate profile, experience/AI gates, prompts, models). Edit any of
those and old rejections are ignored automatically, so tightening or loosening
the rules re-evaluates instead of silently trusting stale verdicts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import CONFIG_DIR, load_career_rules, load_models
from src.ledger.db import Ledger

LEGACY_DECISIONS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "decisions.jsonl"
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
MAX_AGE_DAYS = 30


def rules_signature() -> str:
    rules = load_career_rules()
    parts = [
        (CONFIG_DIR / "candidate_profile.yaml").read_text(encoding="utf-8"),
        json.dumps(
            {k: rules.get(k) for k in ("experience", "ai_gates", "title_signals", "seniority")},
            sort_keys=True,
        ),
        (PROMPTS_DIR / "classify_job_v2.txt").read_text(encoding="utf-8"),
        (PROMPTS_DIR / "analyse_match_v3.txt").read_text(encoding="utf-8"),
        json.dumps(load_models()["routing"], sort_keys=True),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


class DecisionCache:
    """In-memory view of the ledger's verdicts, with write-through when a ledger
    is attached and `persist` is on. With no ledger it is purely in-memory
    (tests, dry-runs of helper scripts)."""

    def __init__(self, ledger: Ledger | None = None, run_id: str | None = None, persist: bool = True):
        self.ledger = ledger
        self.run_id = run_id
        self.persist = persist and ledger is not None
        self.signature = rules_signature()
        self._by_fp: dict[str, dict] = {}
        if ledger is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).isoformat()
            for row in ledger.latest_verdicts(cutoff):
                self._by_fp[row["fingerprint"]] = {
                    "verdict": row["verdict"], "jd_hash": row["jd_hash"], "sig": row["rules_sig"],
                }

    def is_known_rejection(self, fingerprint: str, description_hash: str) -> bool:
        rec = self._by_fp.get(fingerprint)
        return bool(
            rec
            and rec["verdict"] == "rejected"
            and rec["jd_hash"] == description_hash
            and rec["sig"] == self.signature
        )

    def record_rejection(
        self, fingerprint: str, description_hash: str, reason: str, *, node: str = "triage", code: str | None = None
    ) -> None:
        self._record("rejected", fingerprint, description_hash, node, code, reason)

    def record_approval(
        self, fingerprint: str, description_hash: str, *, fit_band: str | None, priority: str | None
    ) -> None:
        """Approvals are remembered too — not to skip work (a vetted job is
        already in Notion, which the dedup index covers) but so the human's
        later decision can be compared with what the system said."""
        self._record("approved", fingerprint, description_hash, "match", "approved_match", None, fit_band, priority)

    def _record(self, verdict, fp, jd_hash, node, code, reason, fit_band=None, priority=None) -> None:
        self._by_fp[fp] = {"verdict": verdict, "jd_hash": jd_hash, "sig": self.signature}
        if self.persist:
            self.ledger.record_verdict(
                fingerprint=fp, jd_hash=jd_hash, verdict=verdict, node=node, rules_sig=self.signature,
                run_id=self.run_id, reason_code=code, reason=reason, fit_band=fit_band, priority=priority,
            )


def import_legacy_decisions(ledger: Ledger, path: Path | None = None) -> int:
    """One-time, idempotent import of decisions.jsonl. Keeps each record's original
    timestamp and rules signature, so still-valid rejections keep saving tokens."""
    path = path if path is not None else LEGACY_DECISIONS_PATH
    if not path.exists():
        return 0
    have = {(r["fingerprint"], r["created_at"]) for r in ledger.query("SELECT fingerprint, created_at FROM verdicts WHERE node='legacy'")}
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (rec["fp"], rec["ts"]) in have:
            continue
        ledger.record_verdict(
            fingerprint=rec["fp"], jd_hash=rec["jd_hash"], verdict="rejected", node="legacy",
            rules_sig=rec["sig"], reason=rec.get("reason"), created_at=rec["ts"],
        )
        n += 1
    return n

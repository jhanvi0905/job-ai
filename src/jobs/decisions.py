"""Local memory of AI verdicts for jobs that were NOT written to Notion.

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

DECISIONS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "decisions.jsonl"
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
    def __init__(self, path: Path = DECISIONS_PATH, persist: bool = True):
        self.path = path
        self.persist = persist
        self.signature = rules_signature()
        self._by_fp: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if datetime.fromisoformat(rec["ts"]) >= cutoff:
                    self._by_fp[rec["fp"]] = rec  # append-only, last write wins

    def is_known_rejection(self, fingerprint: str, description_hash: str) -> bool:
        rec = self._by_fp.get(fingerprint)
        return bool(
            rec
            and rec["verdict"] == "rejected"
            and rec["jd_hash"] == description_hash
            and rec["sig"] == self.signature
        )

    def record_rejection(self, fingerprint: str, description_hash: str, reason: str) -> None:
        rec = {
            "fp": fingerprint,
            "jd_hash": description_hash,
            "verdict": "rejected",
            "reason": reason[:200],
            "sig": self.signature,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._by_fp[fingerprint] = rec
        if not self.persist:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

"""SQLite ledger: an append-only record of what the system did, what it cost,
and how each model call ended.

Why SQLite, and why not Notion: this is operational data that needs joins,
aggregates and constraints, and gets written many times per run. It costs no
infrastructure, lives in one file, and the same file can later hold the
LangGraph checkpointer. Notion stays the human-facing surface only.

Design rules:
  * Append-only. Rows are facts about what happened; nothing is updated in
    place except a run's own status/end time.
  * Closed vocabularies enforced by CHECK constraints (see codes.py).
  * One writer lock: the gateway is used from a thread pool, and sqlite3
    connections aren't safe to share unguarded.
  * Schema changes go through numbered migrations, never ad-hoc ALTERs.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.ledger.codes import (
    CALL_OUTCOMES, DISPOSITIONS, NODE_REASONS, NODES, REASON_CODES, RUN_STATUSES, VERDICT_NODES, VERDICTS, sql_in,
)

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ledger.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Numbered migrations. Never edit an applied one; add the next number.
MIGRATIONS: dict[int, str] = {
    1: f"""
    CREATE TABLE runs (
        run_id           TEXT PRIMARY KEY,
        graph            TEXT NOT NULL,
        started_at       TEXT NOT NULL,
        ended_at         TEXT,
        status           TEXT NOT NULL CHECK (status IN ({sql_in(RUN_STATUSES)})),
        code_version     TEXT,
        config_signature TEXT,
        budget_usd       REAL,
        note             TEXT
    );

    CREATE TABLE llm_calls (
        call_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id           TEXT NOT NULL REFERENCES runs(run_id),
        node             TEXT NOT NULL,
        item_id          TEXT,
        attempt          INTEGER NOT NULL CHECK (attempt >= 1),
        model_requested  TEXT NOT NULL,
        model_resolved   TEXT,
        prompt_version   TEXT,
        outcome          TEXT NOT NULL CHECK (outcome IN ({sql_in(CALL_OUTCOMES)})),
        tokens_in        INTEGER,
        tokens_out       INTEGER,
        cost_usd         REAL NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
        latency_ms       INTEGER,
        input_hash       TEXT,
        context_json     TEXT,
        detail           TEXT,
        created_at       TEXT NOT NULL
    );
    CREATE INDEX idx_llm_calls_run     ON llm_calls(run_id);
    CREATE INDEX idx_llm_calls_created ON llm_calls(created_at);
    CREATE INDEX idx_llm_calls_node    ON llm_calls(node, outcome);
    """,
    2: f"""
    CREATE TABLE events (
        event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id       TEXT NOT NULL REFERENCES runs(run_id),
        item_id      TEXT NOT NULL,
        node         TEXT NOT NULL CHECK (node IN ({sql_in(NODES)})),
        disposition  TEXT NOT NULL CHECK (disposition IN ({sql_in(DISPOSITIONS)})),
        reason_code  TEXT NOT NULL CHECK (reason_code IN ({sql_in(REASON_CODES)})),
        detail       TEXT,
        created_at   TEXT NOT NULL
    );
    CREATE UNIQUE INDEX idx_events_terminal ON events(run_id, item_id, node);
    CREATE INDEX idx_events_analysis ON events(node, disposition, reason_code);

    CREATE TABLE funnel (
        run_id       TEXT NOT NULL REFERENCES runs(run_id),
        node         TEXT NOT NULL CHECK (node IN ({sql_in(NODES)})),
        reason_code  TEXT NOT NULL CHECK (reason_code IN ({sql_in(REASON_CODES)})),
        n            INTEGER NOT NULL CHECK (n >= 0),
        PRIMARY KEY (run_id, node, reason_code)
    );
    """,
    3: f"""
    CREATE TABLE verdicts (
        verdict_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id       TEXT REFERENCES runs(run_id),
        fingerprint  TEXT NOT NULL,
        jd_hash      TEXT NOT NULL,
        verdict      TEXT NOT NULL CHECK (verdict IN ({sql_in(VERDICTS)})),
        node         TEXT NOT NULL CHECK (node IN ({sql_in(VERDICT_NODES)})),
        reason_code  TEXT,
        reason       TEXT,
        fit_band     TEXT,
        priority     TEXT,
        rules_sig    TEXT NOT NULL,
        created_at   TEXT NOT NULL
    );
    CREATE INDEX idx_verdicts_fp ON verdicts(fingerprint, created_at);

    CREATE TABLE human_outcomes (
        outcome_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id         TEXT REFERENCES runs(run_id),
        fingerprint    TEXT NOT NULL,
        notion_page_id TEXT,
        status         TEXT,
        reject_reason  TEXT,
        observed_at    TEXT NOT NULL
    );
    CREATE INDEX idx_outcomes_fp ON human_outcomes(fingerprint, observed_at);
    """,
}


class Ledger:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path if path is not None else DEFAULT_LEDGER_PATH)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + our own lock: the gateway calls in from a pool.
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    @classmethod
    def memory(cls) -> "Ledger":
        return cls(":memory:")

    def close(self) -> None:
        self._conn.close()

    # ---- schema -----------------------------------------------------------
    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
            for version in sorted(v for v in MIGRATIONS if v > current):
                self._conn.execute("BEGIN")
                try:
                    for statement in MIGRATIONS[version].split(";"):
                        if statement.strip():
                            self._conn.execute(statement)
                    self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

    def schema_version(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"] or 0

    # ---- runs -------------------------------------------------------------
    def start_run(
        self,
        graph: str,
        budget_usd: float | None = None,
        code_version: str | None = None,
        config_signature: str | None = None,
    ) -> str:
        run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (run_id, graph, started_at, status, code_version, config_signature, budget_usd)"
                " VALUES (?, ?, ?, 'running', ?, ?, ?)",
                (run_id, graph, _now(), code_version, config_signature, budget_usd),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, note: str | None = None) -> None:
        if status not in RUN_STATUSES or status == "running":
            raise ValueError(f"invalid final run status: {status!r}")
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, ended_at = ?, note = ? WHERE run_id = ?",
                (status, _now(), note, run_id),
            )

    # ---- llm calls --------------------------------------------------------
    def record_call(
        self,
        *,
        run_id: str,
        node: str,
        attempt: int,
        model_requested: str,
        outcome: str,
        item_id: str | None = None,
        model_resolved: str | None = None,
        prompt_version: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float = 0.0,
        latency_ms: int | None = None,
        input_hash: str | None = None,
        context: dict | None = None,
        detail: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO llm_calls (run_id, node, item_id, attempt, model_requested, model_resolved,"
                " prompt_version, outcome, tokens_in, tokens_out, cost_usd, latency_ms, input_hash,"
                " context_json, detail, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id, node, item_id, attempt, model_requested, model_resolved, prompt_version,
                    outcome, tokens_in, tokens_out, cost_usd, latency_ms, input_hash,
                    json.dumps(context, sort_keys=True) if context else None,
                    (detail or "")[:300] or None,
                    _now(),
                ),
            )

    # ---- item-level events (Phase 2) ---------------------------------------
    def record_event(
        self, *, run_id: str, item_id: str, node: str, disposition: str, reason_code: str, detail: str | None = None
    ) -> None:
        """One TERMINAL event per (run, item, node). A second one for the same
        triple raises IntegrityError: that is a pipeline bug, not something to absorb."""
        _check_reason(node, reason_code)
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (run_id, item_id, node, disposition, reason_code, detail, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (run_id, item_id, node, disposition, reason_code, (detail or "")[:300] or None, _now()),
            )

    def record_funnel(self, run_id: str, node: str, counts: dict[str, int]) -> None:
        """Aggregate counts for high-volume nodes (Stage 0 sees ~6,000 items a run;
        per-item rows there would add noise, not insight). Accumulates on repeat."""
        for code in counts:
            _check_reason(node, code)
        with self._lock:
            for code, n in counts.items():
                if n:
                    self._conn.execute(
                        "INSERT INTO funnel (run_id, node, reason_code, n) VALUES (?,?,?,?)"
                        " ON CONFLICT(run_id, node, reason_code) DO UPDATE SET n = n + excluded.n",
                        (run_id, node, code, int(n)),
                    )

    # ---- verdict store (Phase 3) -------------------------------------------
    def record_verdict(
        self, *, fingerprint: str, jd_hash: str, verdict: str, node: str, rules_sig: str,
        run_id: str | None = None, reason_code: str | None = None, reason: str | None = None,
        fit_band: str | None = None, priority: str | None = None, created_at: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO verdicts (run_id, fingerprint, jd_hash, verdict, node, reason_code, reason,"
                " fit_band, priority, rules_sig, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, fingerprint, jd_hash, verdict, node, reason_code, (reason or "")[:200] or None,
                 fit_band, priority, rules_sig, created_at or _now()),
            )

    def latest_verdicts(self, since: str) -> list[dict]:
        """Newest verdict per fingerprint since `since` (ISO timestamp)."""
        return self.query(
            "SELECT v.* FROM verdicts v JOIN (SELECT fingerprint, MAX(verdict_id) AS m FROM verdicts"
            " WHERE created_at >= ? GROUP BY fingerprint) l ON l.m = v.verdict_id",
            (since,),
        )

    # ---- human outcomes (Phase 3) ------------------------------------------
    def record_human_outcome(
        self, *, fingerprint: str, status: str | None, reject_reason: str | None,
        notion_page_id: str | None = None, run_id: str | None = None,
    ) -> bool:
        """Append an observation ONLY if it differs from the latest one for this
        fingerprint, so the table is a change history, not a daily snapshot."""
        with self._lock:
            last = self._conn.execute(
                "SELECT status, reject_reason FROM human_outcomes WHERE fingerprint = ? ORDER BY outcome_id DESC LIMIT 1",
                (fingerprint,),
            ).fetchone()
            if last and last["status"] == status and last["reject_reason"] == reject_reason:
                return False
            self._conn.execute(
                "INSERT INTO human_outcomes (run_id, fingerprint, notion_page_id, status, reject_reason, observed_at)"
                " VALUES (?,?,?,?,?,?)",
                (run_id, fingerprint, notion_page_id, status, reject_reason, _now()),
            )
            return True

    # ---- budget queries (read by the gateway before every call) -----------
    def spent_in_run(self, run_id: str) -> float:
        return self._scalar("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE run_id = ?", (run_id,))

    def calls_in_run(self, run_id: str) -> int:
        """Actual HTTP attempts (guardrail rows, where no call was made, don't count)."""
        return int(
            self._scalar(
                "SELECT COUNT(*) FROM llm_calls WHERE run_id = ? AND outcome NOT IN ('budget_exceeded','circuit_open')",
                (run_id,),
            )
        )

    def spent_today(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._scalar("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= ?", (today,))

    def _scalar(self, sql: str, params: tuple = ()) -> float:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()[0]

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Read-only helper for health checks and tests."""
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]


def _check_reason(node: str, code: str) -> None:
    allowed = NODE_REASONS.get(node)
    if allowed is None:
        raise ValueError(f"unknown node {node!r}")
    if code not in allowed:
        raise ValueError(f"reason code {code!r} is not valid at node {node!r}")

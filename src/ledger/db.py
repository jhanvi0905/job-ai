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

from src.ledger.codes import CALL_OUTCOMES, RUN_STATUSES, sql_in

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
}


class Ledger:
    def __init__(self, path: str | Path = DEFAULT_LEDGER_PATH):
        self.path = str(path)
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

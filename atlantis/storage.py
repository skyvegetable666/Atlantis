from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .contracts import Record, RuleError


class SQLiteStorage:
    """Small experiments use an atomic, versioned JSON snapshot per run."""

    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, snapshot TEXT NOT NULL)"
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _decode(row: tuple | None) -> Record:
        if row is None:
            raise RuleError("not_found", "Experiment does not exist.")
        state = json.loads(row[0])
        if state.get("schema_version") != 1:
            raise RuleError("schema_version", "Unsupported experiment schema version.")
        return state

    def create(self, state: Record) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO runs VALUES (?, 0, ?)",
                (state["id"], json.dumps(state, allow_nan=False)),
            )

    def read(self, run_id: str) -> Record:
        with self._lock:
            return self._decode(self._connection.execute("SELECT snapshot FROM runs WHERE id=?", (run_id,)).fetchone())

    def list_runs(self) -> list[Record]:
        with self._lock:
            return [self._decode(row) for row in self._connection.execute("SELECT snapshot FROM runs ORDER BY rowid DESC")]

    @contextmanager
    def transaction(self, run_id: str) -> Iterator[Record]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                state = self._decode(self._connection.execute("SELECT snapshot FROM runs WHERE id=?", (run_id,)).fetchone())
                yield state
                self._connection.execute(
                    "UPDATE runs SET revision=revision+1, snapshot=? WHERE id=?",
                    (json.dumps(state, allow_nan=False), run_id),
                )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

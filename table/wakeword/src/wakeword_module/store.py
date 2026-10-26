"""Metadata-only SQLite durability for the v2 protocol."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterator, Any, Callable
from uuid import UUID

from .contracts import MAX_SEQUENCE, canonical_json


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredCommand:
    command_id: UUID
    kind: str
    digest: bytes
    controller_epoch: UUID
    command_sequence: int
    listen_session_id: UUID
    state: str
    response: bytes | None
    status_revision: int | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class StoredRequest:
    request_id: UUID
    digest: bytes
    state: str
    response: bytes | None
    status_revision: int | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class OutboxItem:
    outbox_id: int
    status_revision: int
    device_id: str
    kind: str
    payload: bytes
    event_id: UUID | None
    requires_ack: bool
    broker_acked: bool
    application_acked: bool


@dataclass(frozen=True, slots=True)
class StoredLatch:
    status: str
    event_id: UUID
    listen_session_id: UUID
    model_id: str
    model_sha256: str
    confidence: float
    occurred_at: str
    config_revision: str
    status_revision: int
    payload: bytes
    application_acked: bool


class DurableStateStore:
    """One coordinator-owned SQLite connection with explicit transactions."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: str | Path,
        *,
        device_id: str,
        max_rows: int = 256,
        max_bytes: int = 1_048_576,
        reserved_rows: int = 8,
        reserved_bytes: int = 65_536,
        controller_epoch: UUID | None = None,
    ) -> None:
        self.path = Path(path)
        self.device_id = device_id
        self.max_rows = max_rows
        self.max_bytes = max_bytes
        self.reserved_rows = reserved_rows
        self.reserved_bytes = reserved_bytes
        self.controller_epoch = controller_epoch
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StoreError("state store is not open")
        return self._connection

    def open(self) -> None:
        if self._connection is not None:
            return
        if self.path.parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(self.path, timeout=5, isolation_level=None, check_same_thread=True)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=5000")
            self._connection = connection
            self._migrate()
            self.integrity_check()
            if self.controller_epoch is not None:
                persisted = self.get_meta("controller_epoch")
                if persisted is None:
                    self.set_meta("controller_epoch", str(self.controller_epoch))
                elif persisted != str(self.controller_epoch):
                    raise StoreError("configured controller epoch differs from durable store")
        except Exception as exc:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if isinstance(exc, StoreError):
                raise
            raise StoreError("cannot open or migrate state store") from exc

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self.connection
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def _migrate(self) -> None:
        # sqlite3.executescript() implicitly commits any active transaction.
        # Keep schema creation in autocommit mode, then use explicit
        # transactions for all runtime metadata mutations below.
        with self._lock:
            db = self.connection
            db.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            version = db.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            if version is not None and int(version[0]) > self.SCHEMA_VERSION:
                raise StoreError("state store schema is newer than this service")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    digest BLOB NOT NULL,
                    controller_epoch TEXT NOT NULL,
                    command_sequence INTEGER NOT NULL CHECK(command_sequence BETWEEN 0 AND 9223372036854775807),
                    listen_session_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    response BLOB,
                    status_revision INTEGER,
                    reason_code TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    digest BLOB NOT NULL,
                    state TEXT NOT NULL,
                    response BLOB,
                    status_revision INTEGER,
                    reason_code TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS latch (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    status TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    listen_session_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_sha256 TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    occurred_at TEXT NOT NULL,
                    config_revision TEXT NOT NULL,
                    status_revision INTEGER NOT NULL,
                    payload BLOB NOT NULL,
                    application_acked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status_revision INTEGER NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    event_id TEXT,
                    requires_ack INTEGER NOT NULL DEFAULT 0,
                    broker_acked INTEGER NOT NULL DEFAULT 0,
                    application_acked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS acknowledgements (
                    ack_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    listen_session_id TEXT NOT NULL,
                    received_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS outbox_pending_idx ON outbox(application_acked, broker_acked, status_revision);
                """
            )
            db.execute(
                "INSERT INTO schema_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("schema_version", str(self.SCHEMA_VERSION)),
            )

    def integrity_check(self) -> None:
        result = self.connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise StoreError("state store integrity check failed")

    def get_meta(self, key: str) -> str | None:
        row = self.connection.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO schema_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def _next_revision_in_transaction(self, db: sqlite3.Connection) -> int:
        row = db.execute("SELECT value FROM schema_meta WHERE key='status_revision'").fetchone()
        current = int(row[0]) if row else -1
        if current >= MAX_SEQUENCE:
            raise StoreError("status revision exhausted; coordinated reprovision is required")
        revision = current + 1
        db.execute(
            "INSERT INTO schema_meta(key,value) VALUES('status_revision',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(revision),),
        )
        return revision

    def next_status_revision(self) -> int:
        with self.transaction() as db:
            return self._next_revision_in_transaction(db)

    def _outbox_usage(self, db: sqlite3.Connection) -> tuple[int, int]:
        row = db.execute("SELECT COUNT(*), COALESCE(SUM(length(payload)),0) FROM outbox WHERE application_acked=0").fetchone()
        return int(row[0]), int(row[1])

    def reserve_start_quota(self, *, response_bytes: int = 2048, detection_bytes: int = 2048) -> bool:
        with self.transaction() as db:
            rows, size = self._outbox_usage(db)
            return rows + 2 <= self.max_rows - self.reserved_rows and size + response_bytes + detection_bytes <= self.max_bytes - self.reserved_bytes

    def accept_sequence(
        self,
        *,
        controller_epoch: UUID,
        command_sequence: int,
        command_id: UUID,
    ) -> str | None:
        """Persist the v2 high-water mark before lifecycle execution.

        Returns a closed reason code for a command that must not execute, or
        ``None`` after atomically accepting the sequence into the durable
        ordering window.
        """

        if not 0 <= command_sequence <= MAX_SEQUENCE:
            return "invalid_schema"
        with self.transaction() as db:
            persisted_epoch = db.execute("SELECT value FROM schema_meta WHERE key='controller_epoch'").fetchone()
            if persisted_epoch is None:
                db.execute(
                    "INSERT INTO schema_meta(key,value) VALUES('controller_epoch',?)",
                    (str(controller_epoch),),
                )
            elif persisted_epoch[0] != str(controller_epoch):
                return "controller_epoch_mismatch"
            row = db.execute("SELECT value FROM schema_meta WHERE key='command_high_water'").fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO schema_meta(key,value) VALUES('command_high_water',?)",
                    (json.dumps({"sequence": command_sequence, "commandId": str(command_id)}, separators=(",", ":")),),
                )
                return None
            high = json.loads(row[0])
            high_sequence = int(high["sequence"])
            high_id = str(high["commandId"])
            if command_sequence < high_sequence:
                return "stale_command"
            if command_sequence == high_sequence and high_id != str(command_id):
                return "sequence_conflict"
            if command_sequence > high_sequence:
                db.execute(
                    "UPDATE schema_meta SET value=? WHERE key='command_high_water'",
                    (json.dumps({"sequence": command_sequence, "commandId": str(command_id)}, separators=(",", ":")),),
                )
            return None

    def _insert_outbox(
        self,
        db: sqlite3.Connection,
        *,
        revision: int,
        kind: str,
        payload: bytes,
        event_id: UUID | None = None,
        requires_ack: bool = False,
    ) -> int:
        rows, size = self._outbox_usage(db)
        if rows + 1 > self.max_rows or size + len(payload) > self.max_bytes:
            raise StoreError("status outbox capacity is exhausted")
        cursor = db.execute(
            "INSERT INTO outbox(status_revision,device_id,kind,payload,event_id,requires_ack,created_at) VALUES(?,?,?,?,?,?,?)",
            (revision, self.device_id, kind, sqlite3.Binary(payload), str(event_id) if event_id else None, int(requires_ack), datetime.now(timezone.utc).isoformat()),
        )
        return int(cursor.lastrowid)

    def queue_status(
        self,
        payload: bytes | Callable[[int], bytes],
        *,
        kind: str = "status",
        event_id: UUID | None = None,
        requires_ack: bool = False,
    ) -> int:
        with self.transaction() as db:
            revision = self._next_revision_in_transaction(db)
            if callable(payload):
                payload = payload(revision)
            self._insert_outbox(db, revision=revision, kind=kind, payload=payload, event_id=event_id, requires_ack=requires_ack)
            return revision

    def begin_command(
        self,
        *,
        command_id: UUID,
        kind: str,
        digest: bytes,
        controller_epoch: UUID,
        command_sequence: int,
        listen_session_id: UUID,
    ) -> StoredCommand | None:
        if not 0 <= command_sequence <= MAX_SEQUENCE:
            raise StoreError("command sequence is out of range")
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as db:
            existing = db.execute(
                "SELECT command_id,kind,digest,controller_epoch,command_sequence,listen_session_id,state,response,status_revision,reason_code FROM commands WHERE command_id=?",
                (str(command_id),),
            ).fetchone()
            if existing:
                return self._command_from_row(existing)
            db.execute(
                "INSERT INTO commands(command_id,kind,digest,controller_epoch,command_sequence,listen_session_id,state,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (str(command_id), kind, sqlite3.Binary(digest), str(controller_epoch), command_sequence, str(listen_session_id), "PROCESSING", now),
            )
            db.execute(
                "INSERT INTO sessions(session_id,state,created_at) VALUES(?,?,?) ON CONFLICT(session_id) DO NOTHING",
                (str(listen_session_id), "active", now),
            )
            return None

    def _command_from_row(self, row: tuple[Any, ...]) -> StoredCommand:
        return StoredCommand(UUID(row[0]), row[1], bytes(row[2]), UUID(row[3]), int(row[4]), UUID(row[5]), row[6], None if row[7] is None else bytes(row[7]), row[8], row[9])

    def get_command(self, command_id: UUID) -> StoredCommand | None:
        row = self.connection.execute(
            "SELECT command_id,kind,digest,controller_epoch,command_sequence,listen_session_id,state,response,status_revision,reason_code FROM commands WHERE command_id=?",
            (str(command_id),),
        ).fetchone()
        return None if row is None else self._command_from_row(row)

    def processing_commands(self) -> list[StoredCommand]:
        rows = self.connection.execute(
            "SELECT command_id,kind,digest,controller_epoch,command_sequence,listen_session_id,state,response,status_revision,reason_code FROM commands WHERE state='PROCESSING' ORDER BY created_at"
        ).fetchall()
        return [self._command_from_row(row) for row in rows]

    def finish_command(self, command_id: UUID, *, response: bytes, status_revision: int, state: str, reason_code: str | None = None) -> None:
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE commands SET state=?,response=?,status_revision=?,reason_code=? WHERE command_id=?",
                (state, sqlite3.Binary(response), status_revision, reason_code, str(command_id)),
            ).rowcount
            if changed != 1:
                raise StoreError("cannot finish unknown v2 command")

    def finish_command_with_status(
        self,
        command_id: UUID,
        *,
        payload: bytes | Callable[[int], bytes],
        state: str,
        reason_code: str | None = None,
        kind: str = "command-response",
    ) -> tuple[int, bytes]:
        """Atomically allocate, serialize, enqueue, and cache a terminal response."""

        with self.transaction() as db:
            revision = self._next_revision_in_transaction(db)
            if callable(payload):
                payload = payload(revision)
            self._insert_outbox(db, revision=revision, kind=kind, payload=payload)
            changed = db.execute(
                "UPDATE commands SET state=?,response=?,status_revision=?,reason_code=? WHERE command_id=?",
                (state, sqlite3.Binary(payload), revision, reason_code, str(command_id)),
            ).rowcount
            if changed != 1:
                raise StoreError("cannot finish unknown v2 command")
            return revision, payload

    def begin_request(self, *, request_id: UUID, digest: bytes) -> StoredRequest | None:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as db:
            existing = db.execute(
                "SELECT request_id,digest,state,response,status_revision,reason_code FROM requests WHERE request_id=?",
                (str(request_id),),
            ).fetchone()
            if existing:
                return StoredRequest(UUID(existing[0]), bytes(existing[1]), existing[2], None if existing[3] is None else bytes(existing[3]), existing[4], existing[5])
            db.execute(
                "INSERT INTO requests(request_id,digest,state,created_at) VALUES(?,?,?,?)",
                (str(request_id), sqlite3.Binary(digest), "PROCESSING", now),
            )
            return None

    def finish_request(self, request_id: UUID, *, response: bytes, status_revision: int, state: str, reason_code: str | None = None) -> None:
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE requests SET state=?,response=?,status_revision=?,reason_code=? WHERE request_id=?",
                (state, sqlite3.Binary(response), status_revision, reason_code, str(request_id)),
            ).rowcount
            if changed != 1:
                raise StoreError("cannot finish unknown v2 request")

    def finish_request_with_status(
        self,
        request_id: UUID,
        *,
        payload: bytes | Callable[[int], bytes],
        state: str,
        reason_code: str | None = None,
        kind: str = "request-response",
    ) -> tuple[int, bytes]:
        with self.transaction() as db:
            revision = self._next_revision_in_transaction(db)
            if callable(payload):
                payload = payload(revision)
            self._insert_outbox(db, revision=revision, kind=kind, payload=payload)
            changed = db.execute(
                "UPDATE requests SET state=?,response=?,status_revision=?,reason_code=? WHERE request_id=?",
                (state, sqlite3.Binary(payload), revision, reason_code, str(request_id)),
            ).rowcount
            if changed != 1:
                raise StoreError("cannot finish unknown v2 request")
            return revision, payload

    def commit_detection(
        self,
        *,
        status: str,
        event_id: UUID,
        listen_session_id: UUID,
        model_id: str,
        model_sha256: str,
        confidence: float,
        occurred_at: str,
        config_revision: str,
        payload: bytes | Callable[[int], bytes],
    ) -> tuple[int, bytes]:
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM latch WHERE singleton=1").fetchone() is not None:
                raise StoreError("a durable latch already exists")
            revision = self._next_revision_in_transaction(db)
            if callable(payload):
                payload = payload(revision)
            self._insert_outbox(db, revision=revision, kind="detection", payload=payload, event_id=event_id, requires_ack=True)
            db.execute(
                "INSERT INTO latch(singleton,status,event_id,listen_session_id,model_id,model_sha256,confidence,occurred_at,config_revision,status_revision,payload) VALUES(1,?,?,?,?,?,?,?,?,?,?)",
                (status, str(event_id), str(listen_session_id), model_id, model_sha256, confidence, occurred_at, config_revision, revision, sqlite3.Binary(payload)),
            )
            return revision, payload

    def restore_latch(self) -> StoredLatch | None:
        row = self.connection.execute(
            "SELECT status,event_id,listen_session_id,model_id,model_sha256,confidence,occurred_at,config_revision,status_revision,payload,application_acked FROM latch WHERE singleton=1"
        ).fetchone()
        if row is None:
            return None
        return StoredLatch(row[0], UUID(row[1]), UUID(row[2]), row[3], row[4], float(row[5]), row[6], row[7], int(row[8]), bytes(row[9]), bool(row[10]))

    def clear_latch(self) -> None:
        with self.transaction() as db:
            db.execute("DELETE FROM latch WHERE singleton=1")

    def mark_application_ack(self, event_id: UUID) -> bool:
        with self.transaction() as db:
            changed = db.execute("UPDATE latch SET application_acked=1 WHERE event_id=?", (str(event_id),)).rowcount
            db.execute("UPDATE outbox SET application_acked=1 WHERE event_id=?", (str(event_id),))
            return changed == 1

    def record_application_ack(self, *, ack_id: UUID, event_id: UUID, listen_session_id: UUID, received_at: str) -> bool:
        with self.transaction() as db:
            existing = db.execute(
                "SELECT event_id,listen_session_id FROM acknowledgements WHERE ack_id=?",
                (str(ack_id),),
            ).fetchone()
            if existing is not None:
                return existing[0] == str(event_id) and existing[1] == str(listen_session_id)
            latch = db.execute(
                "SELECT listen_session_id FROM latch WHERE event_id=?",
                (str(event_id),),
            ).fetchone()
            if latch is None or latch[0] != str(listen_session_id):
                return False
            db.execute(
                "INSERT INTO acknowledgements(ack_id,event_id,listen_session_id,received_at) VALUES(?,?,?,?)",
                (str(ack_id), str(event_id), str(listen_session_id), received_at),
            )
            db.execute("UPDATE latch SET application_acked=1 WHERE event_id=?", (str(event_id),))
            db.execute("UPDATE outbox SET application_acked=1 WHERE event_id=?", (str(event_id),))
            return True

    def mark_broker_ack(self, outbox_id: int) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE outbox SET broker_acked=1,application_acked=CASE WHEN requires_ack=0 THEN 1 ELSE application_acked END WHERE outbox_id=?",
                (outbox_id,),
            )

    def pending_outbox(self, *, limit: int = 32) -> list[OutboxItem]:
        rows = self.connection.execute(
            "SELECT outbox_id,status_revision,device_id,kind,payload,event_id,requires_ack,broker_acked,application_acked FROM outbox WHERE application_acked=0 ORDER BY status_revision LIMIT ?",
            (limit,),
        ).fetchall()
        return [OutboxItem(int(row[0]), int(row[1]), row[2], row[3], bytes(row[4]), UUID(row[5]) if row[5] else None, bool(row[6]), bool(row[7]), bool(row[8])) for row in rows]

    def mark_session_closed(self, session_id: UUID) -> None:
        with self.transaction() as db:
            db.execute("UPDATE sessions SET state='closed',closed_at=? WHERE session_id=?", (datetime.now(timezone.utc).isoformat(), str(session_id)))

    def close_active_sessions(self) -> int:
        """Tombstone sessions left active by a process crash before restart."""

        with self.transaction() as db:
            return int(
                db.execute(
                    "UPDATE sessions SET state='closed',closed_at=? WHERE state='active'",
                    (datetime.now(timezone.utc).isoformat(),),
                ).rowcount
            )

    def session_state(self, session_id: UUID) -> str | None:
        row = self.connection.execute("SELECT state FROM sessions WHERE session_id=?", (str(session_id),)).fetchone()
        return None if row is None else str(row[0])

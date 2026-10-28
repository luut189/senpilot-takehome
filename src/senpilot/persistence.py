import sqlite3
import time
import uuid
from pathlib import Path

from senpilot.models import InboundMessage, JobResult, JobStatus


class JobStore:
    def __init__(self, path: Path, capacity: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.capacity = capacity
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, email_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
          message TEXT NOT NULL, result TEXT, send_started INTEGER NOT NULL DEFAULT 0,
          created REAL NOT NULL, updated REAL NOT NULL)""")
        self.connection.commit()

    def close(self):
        self.connection.close()

    def by_email(self, email_id: str):
        return self.connection.execute(
            "SELECT * FROM jobs WHERE email_id=?", (email_id,)
        ).fetchone()

    def get(self, job_id):
        return self.connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()

    def add(self, email_id: str, message: InboundMessage) -> str:
        with self.connection:
            existing = self.by_email(email_id)
            if existing:
                return existing["id"]
            count = self.connection.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('pending','processing')"
            ).fetchone()[0]
            if count >= self.capacity:
                raise OverflowError("Job queue is full")
            job_id = str(uuid.uuid4())
            now = time.time()
            self.connection.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,0,?,?)",
                (job_id, email_id, JobStatus.PENDING, message.model_dump_json(), None, now, now),
            )
            return job_id

    def claim(self):
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM jobs WHERE status='pending' ORDER BY created,id LIMIT 1"
            ).fetchone()
            if row:
                self.connection.execute(
                    "UPDATE jobs SET status='processing',updated=? WHERE id=?",
                    (time.time(), row["id"]),
                )
            return row

    def mark_sending(self, job_id):
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET send_started=1,updated=? WHERE id=?", (time.time(), job_id)
            )

    def finish(self, job_id: str, status: JobStatus, result: JobResult):
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET status=?,result=?,updated=? WHERE id=?",
                (status, result.model_dump_json(), time.time(), job_id),
            )

    def recover(self):
        # Never resend interrupted processing jobs automatically. Pending jobs
        # are safe to resume; any send_started job may already have been accepted.
        rows = self.connection.execute("SELECT * FROM jobs WHERE status='processing'").fetchall()
        for row in rows:
            self.finish(
                row["id"],
                JobStatus.DELIVERY_UNKNOWN if row["send_started"] else JobStatus.FAILED,
                JobResult(error="interrupted"),
            )

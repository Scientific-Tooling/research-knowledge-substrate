from __future__ import annotations

import json
import sqlite3

from rks.domain.models import TaskRecord
from rks.ids import next_id
from rks.utils import utc_now


class TaskRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_task(
        self,
        task_type: str,
        paper_id: str,
        mode: str,
        request_artifact_id: str | None,
        spec_version: str | None,
        schema_version: str | None,
    ) -> TaskRecord:
        timestamp = utc_now()
        task_id = next_id(self.conn, "task")
        self.conn.execute(
            """
            INSERT INTO tasks(
                id, task_type, paper_id, mode, status, request_artifact_id, result_artifact_id,
                spec_version, schema_version, error_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                paper_id,
                mode,
                "queued",
                request_artifact_id,
                None,
                spec_version,
                schema_version,
                None,
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def complete_latest_task(self, paper_id: str, task_type: str, result_artifact_id: str | None) -> TaskRecord | None:
        row = self.conn.execute(
            """
            SELECT id
            FROM tasks
            WHERE paper_id = ? AND task_type = ? AND status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (paper_id, task_type),
        ).fetchone()
        if row is None:
            return None
        return self.update_task(
            row["id"],
            status="completed",
            result_artifact_id=result_artifact_id,
            error_json=None,
        )

    def fail_task(self, task_id: str, message: str) -> TaskRecord:
        return self.update_task(task_id, status="failed", result_artifact_id=None, error_json={"message": message})

    def update_task(self, task_id: str, status: str, result_artifact_id: str | None, error_json) -> TaskRecord:
        self.conn.execute(
            """
            UPDATE tasks
            SET status = ?, result_artifact_id = ?, error_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                result_artifact_id,
                json.dumps(error_json, sort_keys=True) if error_json is not None else None,
                utc_now(),
                task_id,
            ),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def list_tasks(self, paper_id: str | None = None, status: str | None = None) -> list[TaskRecord]:
        query = "SELECT * FROM tasks WHERE 1 = 1"
        params: list[str] = []
        if paper_id:
            query += " AND paper_id = ?"
            params.append(paper_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC, id DESC"
        rows = self.conn.execute(query, tuple(params)).fetchall()
        return [TaskRecord(**dict(row)) for row in rows]

    def get_task(self, task_id: str) -> TaskRecord:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Task not found: {task_id}")
        return TaskRecord(**dict(row))

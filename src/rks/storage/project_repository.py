from __future__ import annotations

import json
import sqlite3

from rks.domain.models import ProjectLinkRecord, ProjectRecord
from rks.ids import next_id
from rks.utils import utc_now


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_project(
        self,
        *,
        name: str,
        description: str | None,
        research_question: str | None,
        status: str,
        created_by: str,
    ) -> ProjectRecord:
        timestamp = utc_now()
        project_id = next_id(self.conn, "project")
        self.conn.execute(
            """
            INSERT INTO research_projects(
                id, name, description, research_question, status, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                name,
                description,
                research_question,
                status,
                created_by,
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> ProjectRecord:
        row = self.conn.execute(
            "SELECT * FROM research_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return ProjectRecord(**dict(row))

    def list_projects(self) -> list[ProjectRecord]:
        rows = self.conn.execute(
            "SELECT * FROM research_projects ORDER BY created_at ASC, id ASC",
        ).fetchall()
        return [ProjectRecord(**dict(row)) for row in rows]

    def touch_project(self, project_id: str) -> None:
        self.conn.execute(
            "UPDATE research_projects SET updated_at = ? WHERE id = ?",
            (utc_now(), project_id),
        )
        self.conn.commit()

    def add_link(
        self,
        *,
        project_id: str,
        object_id: str,
        object_type: str,
        link_type: str,
        created_by: str,
        metadata: dict | None = None,
    ) -> ProjectLinkRecord:
        existing = self.conn.execute(
            """
            SELECT *
            FROM project_links
            WHERE project_id = ? AND object_id = ? AND object_type = ? AND link_type = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (project_id, object_id, object_type, link_type),
        ).fetchone()
        if existing is not None:
            return ProjectLinkRecord(**dict(existing))

        link_id = next_id(self.conn, "project_link")
        timestamp = utc_now()
        self.conn.execute(
            """
            INSERT INTO project_links(
                id, project_id, object_id, object_type, link_type, metadata_json, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                project_id,
                object_id,
                object_type,
                link_type,
                json.dumps(metadata or {}, sort_keys=True),
                created_by,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_link(link_id)

    def get_link(self, link_id: str) -> ProjectLinkRecord:
        row = self.conn.execute(
            "SELECT * FROM project_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Project link not found: {link_id}")
        return ProjectLinkRecord(**dict(row))

    def list_links_for_project(self, project_id: str, *, object_type: str | None = None) -> list[ProjectLinkRecord]:
        if object_type is None:
            rows = self.conn.execute(
                "SELECT * FROM project_links WHERE project_id = ? ORDER BY created_at ASC, id ASC",
                (project_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT *
                FROM project_links
                WHERE project_id = ? AND object_type = ?
                ORDER BY created_at ASC, id ASC
                """,
                (project_id, object_type),
            ).fetchall()
        return [ProjectLinkRecord(**dict(row)) for row in rows]

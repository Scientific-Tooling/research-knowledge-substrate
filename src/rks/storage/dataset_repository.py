from __future__ import annotations

import hashlib
import json
import sqlite3

from rks.domain.models import DatasetRecord
from rks.ids import next_id
from rks.utils import utc_now


class DatasetRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_datasets_for_paper(self, paper_id: str, datasets: list[dict]) -> list[DatasetRecord]:
        timestamp = utc_now()
        existing_by_fingerprint = self._existing_datasets_by_fingerprint(paper_id)
        self.conn.execute("DELETE FROM datasets WHERE paper_id = ?", (paper_id,))
        created: list[DatasetRecord] = []

        for dataset in datasets:
            fingerprint = self._dataset_fingerprint(dataset)
            existing = existing_by_fingerprint.get(fingerprint, [])
            prior = existing.pop(0) if existing else None
            dataset_id = prior.id if prior is not None else next_id(self.conn, "dataset")
            created_at = prior.created_at if prior is not None else timestamp
            self.conn.execute(
                """
                INSERT INTO datasets(
                    id, paper_id, name, description, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    paper_id,
                    dataset["name"],
                    dataset.get("description"),
                    dataset.get("source"),
                    created_at,
                    timestamp,
                ),
            )
            created.append(self.get_dataset(dataset_id))

        self.conn.commit()
        return created

    def list_datasets_for_paper(self, paper_id: str) -> list[DatasetRecord]:
        rows = self.conn.execute(
            "SELECT * FROM datasets WHERE paper_id = ? ORDER BY created_at ASC, id ASC",
            (paper_id,),
        ).fetchall()
        return [DatasetRecord(**dict(row)) for row in rows]

    def get_dataset(self, dataset_id: str) -> DatasetRecord:
        row = self.conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise KeyError(f"Dataset not found: {dataset_id}")
        return DatasetRecord(**dict(row))

    def search_datasets(self, query: str) -> list[DatasetRecord]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT *
            FROM datasets
            WHERE name LIKE ? OR description LIKE ? OR source LIKE ?
            ORDER BY updated_at DESC, id DESC
            """,
            (like, like, like),
        ).fetchall()
        return [DatasetRecord(**dict(row)) for row in rows]

    def _existing_datasets_by_fingerprint(self, paper_id: str) -> dict[str, list[DatasetRecord]]:
        records: dict[str, list[DatasetRecord]] = {}
        for dataset in self.list_datasets_for_paper(paper_id):
            fingerprint = self._dataset_fingerprint(
                {
                    "name": dataset.name,
                    "description": dataset.description,
                    "source": dataset.source,
                }
            )
            records.setdefault(fingerprint, []).append(dataset)
        return records

    def _dataset_fingerprint(self, dataset: dict) -> str:
        payload = {
            "name": dataset.get("name"),
            "description": dataset.get("description"),
            "source": dataset.get("source"),
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

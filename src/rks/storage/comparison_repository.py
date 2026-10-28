"""Append-only comparison persistence; operations own transactions and validation."""
import json

from rks.operations.evidence_contract import canonical
from rks.utils import utc_now


class ComparisonRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, comparison_id):
        row = self.conn.execute("SELECT * FROM comparisons WHERE id = ?", (comparison_id,)).fetchone()
        if row is None:
            raise ValueError("Comparison not found in this workspace")
        return dict(row)

    def list(self, workspace_id, source_id):
        return self.conn.execute(
            "SELECT * FROM comparisons WHERE workspace_id = ? AND source_id = ? ORDER BY created_at, id",
            (workspace_id, source_id),
        ).fetchall()

    def content(self, comparison_id):
        row = self.conn.execute(
            "SELECT * FROM comparison_versions WHERE comparison_id = ? ORDER BY version DESC LIMIT 1",
            (comparison_id,),
        ).fetchone()
        return row["version"], json.loads(row["content_json"])

    def history(self, comparison_id):
        return [{"version": row["version"], "created_at": row["created_at"],
                 "cells": json.loads(row["content_json"])} for row in self.conn.execute(
            "SELECT * FROM comparison_versions WHERE comparison_id = ? ORDER BY version", (comparison_id,))]

    def reviews(self, comparison_id):
        return [json.loads(row[0]) for row in self.conn.execute(
            "SELECT review_json FROM comparison_reviews WHERE comparison_id = ? ORDER BY sequence", (comparison_id,))]

    def create(self, comparison_id, workspace_id, source_id, definition):
        self.conn.execute("INSERT INTO comparisons VALUES (?, ?, ?, ?, ?)",
                          (comparison_id, workspace_id, source_id, canonical(definition), utc_now()))
        self.save(comparison_id, 1, [])

    def save(self, comparison_id, version, cells):
        self.conn.execute("INSERT INTO comparison_versions VALUES (?, ?, ?, ?)",
                          (comparison_id, version, canonical(cells), utc_now()))

    def review(self, comparison_id, review):
        sequence = self.conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM comparison_reviews WHERE comparison_id = ?",
            (comparison_id,),
        ).fetchone()[0]
        self.conn.execute("INSERT INTO comparison_reviews VALUES (?, ?, ?)",
                          (comparison_id, sequence, canonical(review)))

    def receipt(self, request_id):
        return self.conn.execute("SELECT * FROM comparison_requests WHERE request_id = ?", (request_id,)).fetchone()

    def remember(self, request_id, request_hash, comparison_id):
        self.conn.execute("INSERT INTO comparison_requests VALUES (?, ?, ?)", (request_id, request_hash, comparison_id))

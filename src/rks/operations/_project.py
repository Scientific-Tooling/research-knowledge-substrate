"""Project and hypothesis operations."""

from __future__ import annotations

import json

from rks.operations._helpers import (
    hypothesis_evidence_entries,
    hypothesis_payload,
    note_payload,
    optional_text,
    paper_payload,
    project_link_entries,
    project_link_entry,
    project_paper_entries,
    project_payload,
    resolve_hypothesis_evidence_target,
    resolve_project_link_target,
)


class ProjectOps:
    def __init__(
        self,
        *,
        papers,
        projects,
        hypotheses,
        claims,
        concepts,
        notes,
        edges,
        methods,
        datasets,
        query,
    ):
        self.papers = papers
        self.projects = projects
        self.hypotheses = hypotheses
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.query = query

    def create_project(
        self,
        *,
        name: str,
        description: str | None = None,
        research_question: str | None = None,
        status: str = "active",
        created_by: str = "human:user",
    ) -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("name must not be empty")
        normalized_status = status.strip() or "active"
        project = self.projects.create_project(
            name=normalized_name,
            description=optional_text(description),
            research_question=optional_text(research_question),
            status=normalized_status,
            created_by=created_by,
        )
        return project_payload(project)

    def list_projects(self) -> list[dict]:
        return [project_payload(project) for project in self.projects.list_projects()]

    def get_project(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        notes = self.notes.list_notes_for_target(target_id=project_id, target_type="project")
        grouped_links = self._grouped_project_links(project_id)
        return {
            **project_payload(project),
            "notes": [note_payload(note) for note in notes],
            "links": grouped_links["links"],
            "papers": grouped_links["papers"],
            "claims": grouped_links["claims"],
            "methods": grouped_links["methods"],
            "datasets": grouped_links["datasets"],
            "concepts": grouped_links["concepts"],
            "hypotheses": [hypothesis_payload(item) for item in self.hypotheses.list_hypotheses_for_project(project_id)],
        }

    def list_project_notes(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        notes = self.notes.list_notes_for_target(target_id=project_id, target_type="project")
        return [note_payload(note) for note in notes]

    def add_project_note(self, project_id: str, *, content: str, created_by: str = "human:user") -> dict:
        self.projects.get_project(project_id)
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("content must not be empty")
        note = self.notes.add_note(
            target_id=project_id,
            target_type="project",
            content=normalized_content,
            created_by=created_by,
        )
        self.projects.touch_project(project_id)
        return note_payload(note)

    def list_project_papers(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="paper")
        return project_paper_entries(self.papers, links)

    def list_project_links(self, project_id: str, *, object_type: str | None = None) -> list[dict]:
        self.projects.get_project(project_id)
        return project_link_entries(
            self.papers,
            self.claims,
            self.methods,
            self.datasets,
            self.concepts,
            self.query,
            self.projects.list_links_for_project(project_id, object_type=object_type),
        )

    def list_project_claims(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="claim")
        return project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def list_project_methods(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="method")
        return project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def list_project_datasets(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="dataset")
        return project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def list_project_concepts(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="concept")
        return project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def add_project_link(
        self,
        project_id: str,
        object_type: str,
        object_id: str,
        *,
        link_type: str = "in_scope",
        created_by: str = "human:user",
    ) -> dict:
        self.projects.get_project(project_id)
        normalized_object_type = object_type.strip()
        normalized_link_type = link_type.strip()
        if normalized_object_type not in {"paper", "claim", "method", "dataset", "concept"}:
            raise ValueError("object_type must be one of: paper, claim, method, dataset, concept")
        if not normalized_link_type:
            raise ValueError("link_type must not be empty")

        target_payload = resolve_project_link_target(
            self.papers,
            self.claims,
            self.methods,
            self.datasets,
            self.concepts,
            self.query,
            normalized_object_type,
            object_id,
        )
        link = self.projects.add_link(
            project_id=project_id,
            object_id=object_id,
            object_type=normalized_object_type,
            link_type=normalized_link_type,
            created_by=created_by,
            metadata=None,
        )
        self.projects.touch_project(project_id)
        return project_link_entry(link, target_payload)

    def add_project_paper(
        self,
        project_id: str,
        paper_id: str,
        *,
        link_type: str = "in_scope",
        created_by: str = "human:user",
    ) -> dict:
        return self.add_project_link(
            project_id,
            "paper",
            paper_id,
            link_type=link_type,
            created_by=created_by,
        )

    def create_hypothesis(
        self,
        project_id: str,
        *,
        text: str,
        status: str = "draft",
        confidence: float | None = None,
        context: dict | None = None,
        created_by: str = "human:user",
    ) -> dict:
        self.projects.get_project(project_id)
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("text must not be empty")
        normalized_status = status.strip() or "draft"
        hypothesis = self.hypotheses.create_hypothesis(
            project_id=project_id,
            text=normalized_text,
            status=normalized_status,
            confidence=confidence,
            context=context or {},
            created_by=created_by,
        )
        self.projects.touch_project(project_id)
        return hypothesis_payload(hypothesis)

    def list_project_hypotheses(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        return [hypothesis_payload(item) for item in self.hypotheses.list_hypotheses_for_project(project_id)]

    def get_hypothesis(self, hypothesis_id: str) -> dict:
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)
        return {
            **hypothesis_payload(hypothesis),
            "project": project_payload(self.projects.get_project(hypothesis.project_id)),
            "evidence_links": hypothesis_evidence_entries(self.papers, self.claims, evidence_links),
        }

    def list_hypothesis_evidence(self, hypothesis_id: str) -> list[dict]:
        self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)
        return hypothesis_evidence_entries(self.papers, self.claims, evidence_links)

    def add_hypothesis_evidence(
        self,
        hypothesis_id: str,
        object_type: str,
        object_id: str,
        *,
        relation_type: str = "supports",
        created_by: str = "human:user",
        note: str | None = None,
    ) -> dict:
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        normalized_object_type = object_type.strip()
        normalized_relation_type = relation_type.strip()
        if normalized_object_type not in {"paper", "claim"}:
            raise ValueError("object_type must be one of: paper, claim")
        if not normalized_relation_type:
            raise ValueError("relation_type must not be empty")

        target = resolve_hypothesis_evidence_target(self.papers, self.claims, normalized_object_type, object_id)
        metadata = {}
        if note:
            metadata["note"] = note.strip()
        link = self.hypotheses.add_evidence_link(
            hypothesis_id=hypothesis.id,
            object_id=object_id,
            object_type=normalized_object_type,
            relation_type=normalized_relation_type,
            created_by=created_by,
            metadata=metadata,
        )
        self.hypotheses.touch_hypothesis(hypothesis_id)
        self.projects.touch_project(hypothesis.project_id)
        from rks.operations._helpers import hypothesis_evidence_entry
        return hypothesis_evidence_entry(link, target)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _grouped_project_links(self, project_id: str) -> dict:
        entries = self.list_project_links(project_id)
        grouped = {
            "links": entries,
            "papers": [],
            "claims": [],
            "methods": [],
            "datasets": [],
            "concepts": [],
        }
        for entry in entries:
            object_type = entry["link"]["object_type"]
            if object_type == "paper":
                grouped["papers"].append(entry)
            elif object_type == "claim":
                grouped["claims"].append(entry)
            elif object_type == "method":
                grouped["methods"].append(entry)
            elif object_type == "dataset":
                grouped["datasets"].append(entry)
            elif object_type == "concept":
                grouped["concepts"].append(entry)
        return grouped

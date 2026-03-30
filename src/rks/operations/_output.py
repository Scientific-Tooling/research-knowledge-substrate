"""Research output generation, query planning, and comparison."""

from __future__ import annotations

from rks.operations._helpers import (
    claim_payload,
    concept_payload,
    dataset_payload,
    hypothesis_payload,
    method_payload,
    optional_text,
    paper_payload,
    project_payload,
)
from rks.reasoning import (
    build_comparison,
    build_research_answer,
    build_research_opportunities,
    build_scoped_answer,
    build_scoped_brief,
    build_scoped_disagreements,
    build_scoped_open_questions,
    build_scoped_opportunities,
    build_scoped_reading_list,
    build_scoped_review_priorities,
    build_topic_brief,
    build_topic_disagreements,
    build_topic_open_questions,
    build_topic_reading_list,
    build_topic_review_priorities,
    plan_research_request,
)


class OutputOps:
    def __init__(
        self,
        *,
        papers,
        projects,
        hypotheses,
        claims,
        concepts,
        methods,
        datasets,
        query,
        evolution_ops=None,
    ):
        self.papers = papers
        self.projects = projects
        self.hypotheses = hypotheses
        self.claims = claims
        self.concepts = concepts
        self.methods = methods
        self.datasets = datasets
        self.query = query
        self._evolution = evolution_ops

    # ------------------------------------------------------------------
    # Global-scope outputs
    # ------------------------------------------------------------------

    def answer_question(self, question: str) -> dict:
        return build_research_answer(self.query, question)

    def topic_brief(self, topic: str) -> dict:
        return build_topic_brief(self.query, topic)

    def topic_disagreements(self, topic: str) -> dict:
        result = build_topic_disagreements(self.query, topic)
        if self._evolution is not None:
            result["conflict_clusters"] = self._evolution.global_conflict_clusters(limit=5)
        else:
            result["conflict_clusters"] = []
        return result

    def research_opportunities(self, topic: str) -> dict:
        return build_research_opportunities(self.query, topic)

    def topic_reading_list(self, topic: str) -> dict:
        return build_topic_reading_list(self.query, topic)

    def topic_open_questions(self, topic: str) -> dict:
        result = build_topic_open_questions(self.query, topic)
        if self._evolution is not None:
            evo = self._evolution.compute_open_questions()
            result["evolution_questions"] = evo.get("questions", [])[:5]
        else:
            result["evolution_questions"] = []
        return result

    def topic_review_priorities(self, topic: str) -> dict:
        result = build_topic_review_priorities(self.query, topic)
        if self._evolution is not None:
            evo = self._evolution.compute_review_priorities()
            result["evolution_priorities"] = evo.get("priorities", [])[:10]
        else:
            result["evolution_priorities"] = []
        return result

    # ------------------------------------------------------------------
    # Project-scope outputs
    # ------------------------------------------------------------------

    def project_answer(self, project_id: str, *, question: str | None = None) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_answer(
            self.query,
            "project",
            project.name,
            context,
            question=optional_text(question) or project.research_question or project.name,
        )

    def project_brief(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        hypotheses = [hypothesis_payload(h) for h in self.hypotheses.list_hypotheses_for_project(project_id)]
        return build_scoped_brief(
            self.query,
            "project",
            project.name,
            context,
            hypotheses=hypotheses,
            research_question=project.research_question,
        )

    def project_disagreements(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        result = build_scoped_disagreements(self.query, "project", project.name, context)
        if self._evolution is not None:
            result["conflict_clusters"] = self._evolution.project_conflict_clusters(project_id, limit=5)
        else:
            result["conflict_clusters"] = []
        return result

    def project_opportunities(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_opportunities(self.query, "project", project.name, context)

    def project_reading_list(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_reading_list(self.query, "project", project.name, context)

    def project_open_questions(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        hypotheses = [hypothesis_payload(h) for h in self.hypotheses.list_hypotheses_for_project(project_id)]
        result = build_scoped_open_questions(
            self.query,
            "project",
            project.name,
            context,
            hypotheses=hypotheses,
        )
        if self._evolution is not None:
            evo = self._evolution.compute_open_questions(scope_type="project", scope_id=project_id)
            result["evolution_questions"] = evo.get("questions", [])[:5]
        else:
            result["evolution_questions"] = []
        return result

    def project_review_priorities(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        result = build_scoped_review_priorities(self.query, "project", project.name, context)
        if self._evolution is not None:
            evo = self._evolution.compute_review_priorities(scope_type="project", scope_id=project_id)
            result["evolution_priorities"] = evo.get("priorities", [])[:10]
        else:
            result["evolution_priorities"] = []
        return result

    # ------------------------------------------------------------------
    # Query planning and comparison
    # ------------------------------------------------------------------

    def plan_query(self, request: str, *, project_id: str | None = None) -> dict:
        project = None
        if project_id is not None:
            project = project_payload(self.projects.get_project(project_id))
        return plan_research_request(request, project=project)

    def compare_targets(self, left: str, right: str) -> dict:
        return build_comparison(self.query, left, right)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _project_output_context(self, project_id: str) -> dict:
        self.projects.get_project(project_id)
        paper_ids: set[str] = set()
        claim_ids: set[str] = set()
        method_ids: set[str] = set()
        dataset_ids: set[str] = set()
        concept_ids: set[str] = set()
        expanded_papers: set[str] = set()
        expanded_methods: set[str] = set()
        expanded_concepts: set[str] = set()

        def include_paper(pid: str) -> bool:
            if pid in paper_ids:
                return False
            self.papers.get_paper(pid)
            paper_ids.add(pid)
            return True

        def include_claim(cid: str) -> bool:
            if cid in claim_ids:
                return False
            claim = self.claims.get_claim(cid)
            claim_ids.add(cid)
            include_paper(claim.paper_id)
            if claim.subject_concept_id:
                concept_ids.add(claim.subject_concept_id)
            if claim.object_concept_id:
                concept_ids.add(claim.object_concept_id)
            return True

        def include_method(mid: str) -> bool:
            if mid in method_ids:
                return False
            method = self.methods.get_method(mid)
            method_ids.add(mid)
            include_paper(method.paper_id)
            if method.about_concept_id:
                concept_ids.add(method.about_concept_id)
            return True

        def include_dataset(did: str) -> bool:
            if did in dataset_ids:
                return False
            dataset = self.datasets.get_dataset(did)
            dataset_ids.add(did)
            include_paper(dataset.paper_id)
            return True

        def include_concept(cid: str) -> bool:
            if cid in concept_ids:
                return False
            self.concepts.get_concept(cid)
            concept_ids.add(cid)
            return True

        for link in self.projects.list_links_for_project(project_id):
            if link.object_type == "paper":
                include_paper(link.object_id)
            elif link.object_type == "claim":
                include_claim(link.object_id)
            elif link.object_type == "method":
                include_method(link.object_id)
            elif link.object_type == "dataset":
                include_dataset(link.object_id)
            elif link.object_type == "concept":
                include_concept(link.object_id)

        for hypothesis in self.hypotheses.list_hypotheses_for_project(project_id):
            for evidence_link in self.hypotheses.list_evidence_links_for_hypothesis(hypothesis.id):
                if evidence_link.object_type == "paper":
                    include_paper(evidence_link.object_id)
                elif evidence_link.object_type == "claim":
                    include_claim(evidence_link.object_id)

        changed = True
        while changed:
            changed = False

            for pid in list(paper_ids - expanded_papers):
                expanded_papers.add(pid)
                for claim in self.claims.list_claims_for_paper(pid):
                    changed = include_claim(claim.id) or changed
                for method in self.methods.list_methods_for_paper(pid):
                    changed = include_method(method.id) or changed
                for dataset in self.datasets.list_datasets_for_paper(pid):
                    changed = include_dataset(dataset.id) or changed
                for concept in self.query.concepts_for_paper(pid):
                    changed = include_concept(concept["id"]) or changed

            for mid in list(method_ids - expanded_methods):
                expanded_methods.add(mid)
                for dataset in self.query.datasets_for(mid).get("datasets", []):
                    changed = include_dataset(dataset["id"]) or changed

            for cid in list(concept_ids - expanded_concepts):
                expanded_concepts.add(cid)
                claims_p = self.query.claims_about(cid).get("claims", [])
                methods_p = self.query.methods_for(cid).get("methods", [])
                datasets_p = self.query.evidence_for(cid).get("datasets", [])
                for c in claims_p:
                    changed = include_claim(c["id"]) or changed
                for m in methods_p:
                    changed = include_method(m["id"]) or changed
                for d in datasets_p:
                    changed = include_dataset(d["id"]) or changed

        claims = sorted(
            [claim_payload(self.concepts, self.claims.get_claim(cid)) for cid in claim_ids],
            key=lambda item: (item.get("confidence") or 0.0, item["id"]),
            reverse=True,
        )
        papers = sorted(
            [paper_payload(self.papers.get_paper(pid)) for pid in paper_ids],
            key=lambda item: (item["title"].lower(), item["id"]),
        )
        methods_out = sorted(
            [method_payload(self.concepts, self.methods.get_method(mid)) for mid in method_ids],
            key=lambda item: (item["name"].lower(), item["id"]),
        )
        datasets_out = sorted(
            [dataset_payload(self.datasets.get_dataset(did)) for did in dataset_ids],
            key=lambda item: (item["name"].lower(), item["id"]),
        )
        concepts_out = sorted(
            [concept_payload(self.concepts.get_concept(cid)) for cid in concept_ids],
            key=lambda item: (item["name"].lower(), item["id"]),
        )
        return {
            "project_id": project_id,
            "claims": claims,
            "claim_ids": [c["id"] for c in claims[:12]],
            "papers": papers,
            "methods": methods_out,
            "datasets": datasets_out,
            "concepts": concepts_out,
        }

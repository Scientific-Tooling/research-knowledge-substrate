"""Facade that composes all operations sub-services.

ResearchOperations keeps the same public API as before — CLI and HTTP
code do not need to change. Internally it delegates to focused sub-services.
"""

from __future__ import annotations

from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService

from rks.operations._concept import ConceptOps
from rks.operations._evolution import EvolutionOps
from rks.operations._output import OutputOps
from rks.operations._paper import PaperOps
from rks.operations._project import ProjectOps
from rks.operations._review import ReviewOps


class ResearchOperations:
    """Thin facade delegating to focused sub-services."""

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
        embeddings,
        tasks,
        candidates=None,
        evolution=None,
        conflict_clusters=None,
    ):
        # Store repos as direct attributes (some code accesses ops.papers, etc.)
        self.papers = papers
        self.projects = projects
        self.hypotheses = hypotheses
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings
        self.tasks = tasks
        self.candidates = candidates
        self.conflict_clusters = conflict_clusters
        self.evolution = evolution

        self.query = QueryService(
            papers=papers,
            claims=claims,
            concepts=concepts,
            edges=edges,
            methods=methods,
            datasets=datasets,
            embeddings=embeddings,
            embedding_provider=LocalHashEmbeddingProvider(),
        )

        # Build sub-services
        self._project = ProjectOps(
            papers=papers, projects=projects, hypotheses=hypotheses,
            claims=claims, concepts=concepts, notes=notes, edges=edges,
            methods=methods, datasets=datasets, query=self.query,
        )
        self._paper = PaperOps(
            papers=papers, claims=claims, concepts=concepts, notes=notes,
            edges=edges, methods=methods, datasets=datasets, tasks=tasks,
            query=self.query,
        )
        self._concept = ConceptOps(
            concepts=concepts, evolution=evolution,
        )
        self._evolution = EvolutionOps(
            papers=papers, projects=projects, hypotheses=hypotheses,
            claims=claims, concepts=concepts, edges=edges,
            evolution=evolution, conflict_clusters=conflict_clusters,
            candidates=candidates,
        )
        self._review = ReviewOps(
            claims=claims, edges=edges, candidates=candidates,
            evolution=evolution, query=self.query,
        )
        self._output = OutputOps(
            papers=papers, projects=projects, hypotheses=hypotheses,
            claims=claims, concepts=concepts, methods=methods,
            datasets=datasets, query=self.query,
            evolution_ops=self._evolution,
        )

    # ------------------------------------------------------------------
    # Project & hypothesis
    # ------------------------------------------------------------------

    def create_project(self, **kw): return self._project.create_project(**kw)
    def list_projects(self): return self._project.list_projects()
    def get_project(self, *a, **kw): return self._project.get_project(*a, **kw)
    def list_project_notes(self, *a, **kw): return self._project.list_project_notes(*a, **kw)
    def add_project_note(self, *a, **kw): return self._project.add_project_note(*a, **kw)
    def list_project_papers(self, *a, **kw): return self._project.list_project_papers(*a, **kw)
    def list_project_links(self, *a, **kw): return self._project.list_project_links(*a, **kw)
    def list_project_claims(self, *a, **kw): return self._project.list_project_claims(*a, **kw)
    def list_project_methods(self, *a, **kw): return self._project.list_project_methods(*a, **kw)
    def list_project_datasets(self, *a, **kw): return self._project.list_project_datasets(*a, **kw)
    def list_project_concepts(self, *a, **kw): return self._project.list_project_concepts(*a, **kw)
    def add_project_link(self, *a, **kw): return self._project.add_project_link(*a, **kw)
    def add_project_paper(self, *a, **kw): return self._project.add_project_paper(*a, **kw)
    def create_hypothesis(self, *a, **kw): return self._project.create_hypothesis(*a, **kw)
    def list_project_hypotheses(self, *a, **kw): return self._project.list_project_hypotheses(*a, **kw)
    def get_hypothesis(self, *a, **kw): return self._project.get_hypothesis(*a, **kw)
    def list_hypothesis_evidence(self, *a, **kw): return self._project.list_hypothesis_evidence(*a, **kw)
    def add_hypothesis_evidence(self, *a, **kw): return self._project.add_hypothesis_evidence(*a, **kw)

    # ------------------------------------------------------------------
    # Paper management
    # ------------------------------------------------------------------

    def paper_status(self, *a, **kw): return self._paper.paper_status(*a, **kw)
    def claim_relations(self, *a, **kw): return self._paper.claim_relations(*a, **kw)
    def list_paper_notes(self, *a, **kw): return self._paper.list_paper_notes(*a, **kw)
    def add_paper_note(self, *a, **kw): return self._paper.add_paper_note(*a, **kw)
    def find_duplicate_papers(self, **kw): return self._paper.find_duplicate_papers(**kw)
    def merge_papers(self, *a, **kw): return self._paper.merge_papers(*a, **kw)
    def add_concept_alias(self, *a, **kw): return self._concept.add_concept_alias(*a, **kw)
    def merge_concepts(self, *a, **kw): return self._concept.merge_concepts(*a, **kw)
    def find_duplicate_concepts(self, *a, **kw): return self._concept.find_duplicate_concepts(*a, **kw)
    def prepare_paper_for_output(self, *a, **kw): return self._paper.prepare_paper_for_output(*a, **kw)
    def workspace_stats(self): return self._paper.workspace_stats()
    def extraction_quality_report(self): return self._paper.extraction_quality_report()

    # ------------------------------------------------------------------
    # Research outputs
    # ------------------------------------------------------------------

    def answer_question(self, *a, **kw): return self._output.answer_question(*a, **kw)
    def topic_brief(self, *a, **kw): return self._output.topic_brief(*a, **kw)
    def topic_disagreements(self, *a, **kw): return self._output.topic_disagreements(*a, **kw)
    def research_opportunities(self, *a, **kw): return self._output.research_opportunities(*a, **kw)
    def topic_reading_list(self, *a, **kw): return self._output.topic_reading_list(*a, **kw)
    def topic_open_questions(self, *a, **kw): return self._output.topic_open_questions(*a, **kw)
    def topic_review_priorities(self, *a, **kw): return self._output.topic_review_priorities(*a, **kw)
    def project_answer(self, *a, **kw): return self._output.project_answer(*a, **kw)
    def project_brief(self, *a, **kw): return self._output.project_brief(*a, **kw)
    def project_disagreements(self, *a, **kw): return self._output.project_disagreements(*a, **kw)
    def project_opportunities(self, *a, **kw): return self._output.project_opportunities(*a, **kw)
    def project_reading_list(self, *a, **kw): return self._output.project_reading_list(*a, **kw)
    def project_open_questions(self, *a, **kw): return self._output.project_open_questions(*a, **kw)
    def project_review_priorities(self, *a, **kw): return self._output.project_review_priorities(*a, **kw)
    def plan_query(self, *a, **kw): return self._output.plan_query(*a, **kw)
    def compare_targets(self, *a, **kw): return self._output.compare_targets(*a, **kw)

    # ------------------------------------------------------------------
    # Review (claim relations & candidates)
    # ------------------------------------------------------------------

    def promote_claim_relation(self, *a, **kw): return self._review.promote_claim_relation(*a, **kw)
    def retract_claim_relation(self, *a, **kw): return self._review.retract_claim_relation(*a, **kw)
    def materialize_claim_relation_candidates(self, *a, **kw): return self._review.materialize_claim_relation_candidates(*a, **kw)
    def list_relation_candidates(self, *a, **kw): return self._review.list_relation_candidates(*a, **kw)
    def promote_candidate(self, *a, **kw): return self._review.promote_candidate(*a, **kw)
    def reject_candidate(self, *a, **kw): return self._review.reject_candidate(*a, **kw)

    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------

    def list_evolution_events(self, *a, **kw): return self._evolution.list_evolution_events(*a, **kw)
    def build_concept_timeline(self, *a, **kw): return self._evolution.build_concept_timeline(*a, **kw)
    def build_hypothesis_evolution(self, *a, **kw): return self._evolution.build_hypothesis_evolution(*a, **kw)
    def build_hypothesis_evolution_bucketed(self, *a, **kw): return self._evolution.build_hypothesis_evolution_bucketed(*a, **kw)
    def project_evolution_timeline(self, *a, **kw): return self._evolution.project_evolution_timeline(*a, **kw)
    def concept_timeline(self, *a, **kw): return self._evolution.concept_timeline(*a, **kw)
    def build_concept_timeline_bucketed(self, *a, **kw): return self._evolution.build_concept_timeline_bucketed(*a, **kw)
    def cluster_claim_conflicts(self, *a, **kw): return self._evolution.cluster_claim_conflicts(*a, **kw)
    def list_conflict_clusters(self, *a, **kw): return self._evolution.list_conflict_clusters(*a, **kw)
    def conflict_graph(self, *a, **kw): return self._evolution.conflict_graph(*a, **kw)
    def compute_review_priorities(self, *a, **kw): return self._evolution.compute_review_priorities(*a, **kw)
    def compute_open_questions(self, *a, **kw): return self._evolution.compute_open_questions(*a, **kw)
    def list_concept_controversies(self, *a, **kw): return self._evolution.list_concept_controversies(*a, **kw)
    def project_evolution_summary(self, *a, **kw): return self._evolution.project_evolution_summary(*a, **kw)


# ------------------------------------------------------------------
# Public standalone function (re-exported via __init__)
# ------------------------------------------------------------------


def describe_claim_schema() -> dict:
    return {
        "object_type": "claim",
        "description": (
            "A structured research claim extracted from a paper, representing a "
            "Subject-Predicate-Object triple with supporting context and evidence."
        ),
        "fields": {
            "id": {"type": "string", "description": "Unique claim identifier (e.g. c_000001).", "required": True},
            "paper_id": {"type": "string", "description": "ID of the source paper.", "required": True},
            "text": {"type": "string", "description": "Full natural-language claim sentence.", "required": True},
            "subject": {"type": "string|null", "description": "Resolved subject name (from linked concept or context.subject_text).", "required": False},
            "predicate": {
                "type": "string",
                "description": "Relation expressed by the claim.",
                "required": True,
                "allowed_values": [
                    "outperforms", "improves", "reduces", "increases",
                    "enables", "requires", "supports", "replaces",
                    "refines", "extends",
                ],
            },
            "object": {"type": "string|null", "description": "Resolved object name (from linked concept or object_text).", "required": False},
            "confidence": {"type": "float|null", "description": "Extraction confidence score between 0.0 and 1.0.", "required": False},
            "context": {
                "type": "object",
                "description": "Structured context parsed from the claim sentence.",
                "required": False,
                "fields": {
                    "subject_text": {"type": "string|null", "description": "Raw subject text as extracted.", "required": False},
                    "section": {"type": "string|null", "description": "Paper section where the claim appeared.", "required": False},
                    "claim_key": {"type": "string|null", "description": "Short SHA1 fingerprint of the claim sentence.", "required": False},
                    "dataset": {"type": "string|null", "description": "Benchmark or dataset mentioned in the claim.", "required": False},
                    "task": {"type": "string|null", "description": "Task or problem domain mentioned in the claim.", "required": False},
                    "domain": {"type": "string|null", "description": "Research domain mentioned in the claim.", "required": False},
                },
            },
            "evidence": {
                "type": "object",
                "description": "Location of the claim within the source paper.",
                "required": False,
                "fields": {
                    "paper_id": {"type": "string|null", "description": "ID of the paper containing the evidence.", "required": False},
                    "extraction": {"type": "string|null", "description": "Extraction method used (e.g. heuristic, agent).", "required": False},
                    "extractor_version": {"type": "string|null", "description": "Version of the extractor that produced the claim.", "required": False},
                    "section": {"type": "string|null", "description": "Section of the paper where the sentence appears.", "required": False},
                    "paragraph_index": {"type": "integer|null", "description": "Zero-based paragraph index within the section.", "required": False},
                    "sentence_index": {"type": "integer|null", "description": "Zero-based sentence index within the paragraph.", "required": False},
                    "char_start": {"type": "integer|null", "description": "Character offset of the sentence start in the full text.", "required": False},
                    "char_end": {"type": "integer|null", "description": "Character offset of the sentence end in the full text.", "required": False},
                    "snippet": {"type": "string|null", "description": "Original sentence text before normalization.", "required": False},
                    "schema_version": {"type": "string|null", "description": "Schema version used when the claim was extracted.", "required": False},
                },
            },
            "created_by": {"type": "string", "description": "Creator label (e.g. system:heuristic, system:llm_api, human:user).", "required": True},
            "created_at": {"type": "string", "description": "ISO 8601 timestamp of creation.", "required": True},
            "updated_at": {"type": "string", "description": "ISO 8601 timestamp of last update.", "required": True},
        },
    }

"""Knowledge evolution: timelines, conflict clustering, review priorities, open questions."""

from __future__ import annotations

import json

from rks.operations._helpers import hypothesis_payload, snapshot_payload


class EvolutionOps:
    def __init__(
        self,
        *,
        papers,
        projects,
        hypotheses,
        claims,
        concepts,
        edges,
        evolution,
        conflict_clusters,
        candidates,
    ):
        self.papers = papers
        self.projects = projects
        self.hypotheses = hypotheses
        self.claims = claims
        self.concepts = concepts
        self.edges = edges
        self.evolution = evolution
        self.conflict_clusters = conflict_clusters
        self.candidates = candidates

    # ------------------------------------------------------------------
    # Events and timeline snapshots
    # ------------------------------------------------------------------

    def list_evolution_events(self, subject_id: str, subject_type: str | None = None) -> list[dict]:
        if self.evolution is None:
            return []
        records = self.evolution.list_events_for_subject(subject_id, subject_type)
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "subject_id": r.subject_id,
                "subject_type": r.subject_type,
                "detail": json.loads(r.detail_json or "{}"),
                "created_by": r.created_by,
                "created_at": r.created_at,
            }
            for r in records
        ]

    def build_concept_timeline(self, concept_id: str) -> dict:
        if self.evolution is None:
            return {"error": "evolution repository not available"}

        concept = self.concepts.get_concept(concept_id)
        claims = self.claims.list_claims_for_concept(concept_id)
        paper_ids = sorted({claim.paper_id for claim in claims})

        support_count = 0
        contradiction_count = 0
        refine_count = 0
        for claim in claims:
            for edge in self.edges.list_claim_relation_edges(claim.id):
                if edge.relation_type == "supports":
                    support_count += 1
                elif edge.relation_type == "contradicts":
                    contradiction_count += 1
                elif edge.relation_type == "refines":
                    refine_count += 1

        total = support_count + contradiction_count
        consensus_score = support_count / max(1, total)
        controversy_score = min(support_count, contradiction_count) / max(1, total)

        snapshot = self.evolution.create_snapshot(
            concept_id=concept_id,
            support_count=support_count,
            contradiction_count=contradiction_count,
            paper_count=len(paper_ids),
            claim_count=len(claims),
            detail={"paper_ids": paper_ids},
            refine_count=refine_count,
            consensus_score=consensus_score,
            controversy_score=controversy_score,
            basis_layer="reviewed",
        )

        self.evolution.record_event(
            event_type="concept_snapshot",
            subject_id=concept_id,
            subject_type="concept",
            detail={
                "snapshot_id": snapshot.id,
                "support_count": support_count,
                "contradiction_count": contradiction_count,
                "refine_count": refine_count,
                "paper_count": len(paper_ids),
                "claim_count": len(claims),
                "consensus_score": consensus_score,
                "controversy_score": controversy_score,
            },
            created_by="system:timeline",
        )

        return {
            "concept": {"id": concept.id, "name": concept.name},
            "snapshot": {
                "id": snapshot.id,
                "snapshot_at": snapshot.snapshot_at,
                "support_count": snapshot.support_count,
                "contradiction_count": snapshot.contradiction_count,
                "refine_count": snapshot.refine_count,
                "paper_count": snapshot.paper_count,
                "claim_count": snapshot.claim_count,
                "consensus_score": snapshot.consensus_score,
                "controversy_score": snapshot.controversy_score,
            },
        }

    def build_hypothesis_evolution(self, hypothesis_id: str) -> dict:
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)

        support_count = 0
        contradiction_count = 0
        neutral_count = 0
        for link in evidence_links:
            if link.relation_type == "supports":
                support_count += 1
            elif link.relation_type == "contradicts":
                contradiction_count += 1
            else:
                neutral_count += 1

        total = support_count + contradiction_count + neutral_count
        if total == 0:
            trend = "no_evidence"
        elif contradiction_count == 0:
            trend = "strengthening"
        elif support_count == 0:
            trend = "weakening"
        elif support_count > contradiction_count * 2:
            trend = "strengthening"
        elif contradiction_count > support_count * 2:
            trend = "weakening"
        else:
            trend = "contested"

        events = []
        if self.evolution is not None:
            events = [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "detail": json.loads(r.detail_json or "{}"),
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                }
                for r in self.evolution.list_events_for_subject(hypothesis_id, "hypothesis")
            ]

        return {
            "hypothesis": hypothesis_payload(hypothesis),
            "evidence_summary": {
                "support_count": support_count,
                "contradiction_count": contradiction_count,
                "neutral_count": neutral_count,
                "total": total,
            },
            "trend": trend,
            "events": events,
        }

    def build_hypothesis_evolution_bucketed(self, hypothesis_id: str, bucket_size: str = "yearly") -> dict:
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)

        buckets: dict[str, dict] = {}
        for link in evidence_links:
            year_key = "unknown"
            try:
                if link.object_type == "claim":
                    claim = self.claims.get_claim(link.object_id)
                    paper = self.papers.get_paper(claim.paper_id)
                elif link.object_type == "paper":
                    paper = self.papers.get_paper(link.object_id)
                else:
                    paper = None
                if paper and paper.year:
                    year_key = str(paper.year)
            except KeyError:
                pass

            if year_key not in buckets:
                buckets[year_key] = {"support": 0, "contradiction": 0, "neutral": 0, "links": []}
            bucket = buckets[year_key]
            if link.relation_type == "supports":
                bucket["support"] += 1
            elif link.relation_type == "contradicts":
                bucket["contradiction"] += 1
            else:
                bucket["neutral"] += 1
            bucket["links"].append({
                "object_type": link.object_type,
                "object_id": link.object_id,
                "relation_type": link.relation_type,
            })

        result_buckets = []
        for key in sorted(buckets):
            b = buckets[key]
            total = b["support"] + b["contradiction"]
            consensus_score = b["support"] / max(1, total)
            controversy_score = min(b["support"], b["contradiction"]) / max(1, total)
            if total == 0:
                trend = "no_evidence"
            elif b["contradiction"] == 0:
                trend = "strengthening"
            elif b["support"] == 0:
                trend = "weakening"
            elif b["support"] > b["contradiction"] * 2:
                trend = "strengthening"
            elif b["contradiction"] > b["support"] * 2:
                trend = "weakening"
            else:
                trend = "contested"
            result_buckets.append({
                "time_bucket": key,
                "support_count": b["support"],
                "contradiction_count": b["contradiction"],
                "neutral_count": b["neutral"],
                "total_evidence": b["support"] + b["contradiction"] + b["neutral"],
                "consensus_score": round(consensus_score, 4),
                "controversy_score": round(controversy_score, 4),
                "trend": trend,
                "links": b["links"],
            })

        return {
            "hypothesis": hypothesis_payload(hypothesis),
            "bucket_size": bucket_size,
            "buckets": result_buckets,
        }

    def project_evolution_timeline(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        hypotheses = self.hypotheses.list_hypotheses_for_project(project_id)

        year_totals: dict[str, dict] = {}
        hypothesis_summaries = []

        for h in hypotheses:
            h_bucketed = self.build_hypothesis_evolution_bucketed(h.id)
            hypothesis_summaries.append({
                "hypothesis_id": h.id,
                "text": h.text,
                "bucket_count": len(h_bucketed["buckets"]),
            })
            for bucket in h_bucketed["buckets"]:
                key = bucket["time_bucket"]
                if key not in year_totals:
                    year_totals[key] = {"support": 0, "contradiction": 0, "neutral": 0, "hypothesis_ids": []}
                year_totals[key]["support"] += bucket["support_count"]
                year_totals[key]["contradiction"] += bucket["contradiction_count"]
                year_totals[key]["neutral"] += bucket["neutral_count"]
                if h.id not in year_totals[key]["hypothesis_ids"]:
                    year_totals[key]["hypothesis_ids"].append(h.id)

        timeline = []
        for key in sorted(year_totals):
            t = year_totals[key]
            total = t["support"] + t["contradiction"]
            consensus_score = t["support"] / max(1, total)
            controversy_score = min(t["support"], t["contradiction"]) / max(1, total)
            timeline.append({
                "time_bucket": key,
                "support_count": t["support"],
                "contradiction_count": t["contradiction"],
                "neutral_count": t["neutral"],
                "hypothesis_count": len(t["hypothesis_ids"]),
                "hypothesis_ids": t["hypothesis_ids"],
                "consensus_score": round(consensus_score, 4),
                "controversy_score": round(controversy_score, 4),
            })

        return {
            "project": {"id": project.id, "name": project.name},
            "timeline": timeline,
            "hypotheses": hypothesis_summaries,
        }

    def concept_timeline(self, concept_id: str) -> dict:
        if self.evolution is None:
            return {"error": "evolution repository not available", "snapshots": []}
        concept = self.concepts.get_concept(concept_id)
        snapshots = self.evolution.list_snapshots_for_concept(concept_id)
        return {
            "concept": {"id": concept.id, "name": concept.name},
            "snapshots": [snapshot_payload(s) for s in snapshots],
        }

    # ------------------------------------------------------------------
    # Time-bucketed concept snapshots
    # ------------------------------------------------------------------

    def build_concept_timeline_bucketed(self, concept_id: str, bucket_size: str = "yearly") -> dict:
        if self.evolution is None:
            return {"error": "evolution repository not available"}

        concept = self.concepts.get_concept(concept_id)
        claims = self.claims.list_claims_for_concept(concept_id)

        buckets: dict[str, list] = {}
        for claim in claims:
            try:
                paper = self.papers.get_paper(claim.paper_id)
            except KeyError:
                continue
            year = paper.year
            bucket_key = str(year) if year is not None else "unknown"
            buckets.setdefault(bucket_key, []).append(claim)

        created_snapshots = []
        for bucket_key in sorted(buckets):
            bucket_claims = buckets[bucket_key]
            bucket_claim_ids = {c.id for c in bucket_claims}
            paper_ids = sorted({c.paper_id for c in bucket_claims})

            support_count = 0
            contradiction_count = 0
            refine_count = 0
            for claim in bucket_claims:
                for edge in self.edges.list_claim_relation_edges(claim.id):
                    other_id = edge.target_id if edge.source_id == claim.id else edge.source_id
                    if other_id not in bucket_claim_ids:
                        continue
                    if edge.relation_type == "supports":
                        support_count += 1
                    elif edge.relation_type == "contradicts":
                        contradiction_count += 1
                    elif edge.relation_type == "refines":
                        refine_count += 1

            support_count = support_count // 2
            contradiction_count = contradiction_count // 2
            refine_count = refine_count // 2

            total = support_count + contradiction_count
            consensus_score = support_count / max(1, total)
            controversy_score = min(support_count, contradiction_count) / max(1, total)

            snapshot = self.evolution.create_snapshot(
                concept_id=concept_id,
                support_count=support_count,
                contradiction_count=contradiction_count,
                paper_count=len(paper_ids),
                claim_count=len(bucket_claims),
                detail={"paper_ids": paper_ids},
                time_bucket=bucket_key,
                refine_count=refine_count,
                consensus_score=consensus_score,
                controversy_score=controversy_score,
                basis_layer="reviewed",
            )
            created_snapshots.append(snapshot)

        self.evolution.record_event(
            event_type="concept_timeline_bucketed",
            subject_id=concept_id,
            subject_type="concept",
            detail={
                "bucket_size": bucket_size,
                "bucket_count": len(created_snapshots),
                "buckets": [s.time_bucket for s in created_snapshots],
            },
            created_by="system:timeline",
        )

        return {
            "concept": {"id": concept.id, "name": concept.name},
            "bucket_size": bucket_size,
            "snapshots": [snapshot_payload(s) for s in created_snapshots],
        }

    # ------------------------------------------------------------------
    # Conflict clustering
    # ------------------------------------------------------------------

    def cluster_claim_conflicts(self, concept_id: str | None = None) -> dict:
        if self.conflict_clusters is None:
            return {"error": "conflict cluster repository not available"}

        concept_ids = []
        if concept_id:
            concept_ids.append(concept_id)
        else:
            for paper in self.papers.list_papers():
                for claim in self.claims.list_claims_for_paper(paper.id):
                    if claim.subject_concept_id and claim.subject_concept_id not in concept_ids:
                        concept_ids.append(claim.subject_concept_id)
                    if claim.object_concept_id and claim.object_concept_id not in concept_ids:
                        concept_ids.append(claim.object_concept_id)

        total_clusters = 0
        results = []
        for cid in concept_ids:
            concept = self.concepts.get_concept(cid)
            claims = self.claims.list_claims_for_concept(cid)
            claim_ids = {c.id for c in claims}

            adjacency: dict[str, set[str]] = {c.id: set() for c in claims}
            for claim in claims:
                for edge in self.edges.list_claim_relation_edges(claim.id, relation_types=["contradicts"]):
                    src, tgt = edge.source_id, edge.target_id
                    if src in claim_ids and tgt in claim_ids:
                        adjacency.setdefault(src, set()).add(tgt)
                        adjacency.setdefault(tgt, set()).add(src)

            visited: set[str] = set()
            components: list[set[str]] = []
            for node in adjacency:
                if node in visited or not adjacency[node]:
                    continue
                component: set[str] = set()
                queue = [node]
                while queue:
                    current = queue.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    component.add(current)
                    for neighbor in adjacency.get(current, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
                if len(component) >= 2:
                    components.append(component)

            if not components:
                continue

            self.conflict_clusters.clear_clusters_for_concept(cid)

            for component in components:
                cluster = self.conflict_clusters.create_cluster(
                    anchor_concept_id=cid,
                    topic_label=concept.name,
                    summary={"claim_count": len(component)},
                )

                claim_support_counts: dict[str, int] = {}
                for claim_id_in_component in component:
                    count = 0
                    for edge in self.edges.list_claim_relation_edges(claim_id_in_component, relation_types=["supports"]):
                        count += 1
                    claim_support_counts[claim_id_in_component] = count

                if claim_support_counts:
                    median_support = sorted(claim_support_counts.values())[len(claim_support_counts) // 2]
                else:
                    median_support = 0

                for claim_id_in_component in component:
                    support = claim_support_counts.get(claim_id_in_component, 0)
                    stance = "mainstream" if support >= median_support else "dissenting"
                    self.conflict_clusters.add_member(
                        cluster_id=cluster.id,
                        claim_id=claim_id_in_component,
                        role="member",
                        stance=stance,
                    )

                total_clusters += 1

                if self.evolution is not None:
                    self.evolution.record_event(
                        event_type="conflict_cluster_created",
                        subject_id=cluster.id,
                        subject_type="conflict_cluster",
                        detail={
                            "anchor_concept_id": cid,
                            "concept_name": concept.name,
                            "member_count": len(component),
                        },
                        created_by="system:clustering",
                    )

            results.append({
                "concept_id": cid,
                "concept_name": concept.name,
                "cluster_count": len(components),
            })

        return {"total_clusters": total_clusters, "concepts": results}

    def list_conflict_clusters(self, concept_id: str) -> dict:
        if self.conflict_clusters is None:
            return {"error": "conflict cluster repository not available", "clusters": []}

        concept = self.concepts.get_concept(concept_id)
        clusters = self.conflict_clusters.list_clusters_for_concept(concept_id)
        result = []
        for cluster in clusters:
            members = self.conflict_clusters.list_members_for_cluster(cluster.id)
            enriched_members = []
            for m in members:
                member_entry = {
                    "id": m.id,
                    "claim_id": m.claim_id,
                    "role": m.role,
                    "stance": m.stance,
                    "confidence": m.confidence,
                }
                try:
                    claim = self.claims.get_claim(m.claim_id)
                    paper = self.papers.get_paper(claim.paper_id)
                    member_entry["claim_text"] = claim.text
                    member_entry["claim_predicate"] = claim.predicate
                    member_entry["claim_confidence"] = claim.confidence
                    member_entry["paper_id"] = claim.paper_id
                    member_entry["paper_title"] = paper.title
                    member_entry["paper_year"] = paper.year
                except KeyError:
                    pass
                enriched_members.append(member_entry)
            result.append({
                "id": cluster.id,
                "topic_label": cluster.topic_label,
                "status": cluster.status,
                "members": enriched_members,
                "created_at": cluster.created_at,
            })
        return {
            "concept": {"id": concept.id, "name": concept.name},
            "clusters": result,
        }

    def conflict_graph(self, concept_id: str) -> dict:
        concept = self.concepts.get_concept(concept_id)
        claims = self.claims.list_claims_for_concept(concept_id)
        claim_ids = {c.id for c in claims}

        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edges: set[frozenset] = set()

        for claim in claims:
            for edge in self.edges.list_claim_relation_edges(claim.id, relation_types=["contradicts"]):
                src, tgt = edge.source_id, edge.target_id
                if src not in claim_ids or tgt not in claim_ids:
                    continue
                pair = frozenset((src, tgt))
                if pair in seen_edges:
                    continue
                seen_edges.add(pair)
                edges.append({
                    "source_id": src,
                    "target_id": tgt,
                    "relation_type": edge.relation_type,
                    "confidence": edge.confidence,
                    "created_by": edge.created_by,
                })
                for cid in (src, tgt):
                    if cid not in nodes:
                        nodes[cid] = cid

        resolved_nodes = []
        for cid in nodes:
            try:
                claim = self.claims.get_claim(cid)
                paper = self.papers.get_paper(claim.paper_id)
                subject_name = None
                if claim.subject_concept_id:
                    try:
                        subject_name = self.concepts.get_concept(claim.subject_concept_id).name
                    except KeyError:
                        pass
                resolved_nodes.append({
                    "id": cid,
                    "text": claim.text,
                    "predicate": claim.predicate,
                    "subject": subject_name,
                    "object": claim.object_text,
                    "confidence": claim.confidence,
                    "paper_id": claim.paper_id,
                    "paper_title": paper.title,
                    "paper_year": paper.year,
                })
            except KeyError:
                resolved_nodes.append({"id": cid})

        cluster_membership: dict[str, dict] = {}
        if self.conflict_clusters is not None:
            for cluster in self.conflict_clusters.list_clusters_for_concept(concept_id):
                for m in self.conflict_clusters.list_members_for_cluster(cluster.id):
                    cluster_membership[m.claim_id] = {
                        "cluster_id": cluster.id,
                        "stance": m.stance,
                        "role": m.role,
                    }
        for node in resolved_nodes:
            if node["id"] in cluster_membership:
                node["cluster"] = cluster_membership[node["id"]]

        return {
            "concept": {"id": concept.id, "name": concept.name},
            "node_count": len(resolved_nodes),
            "edge_count": len(edges),
            "nodes": resolved_nodes,
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # Review priorities and open questions
    # ------------------------------------------------------------------

    def compute_review_priorities(self, scope_type: str = "concept", scope_id: str | None = None) -> dict:
        if self.candidates is None:
            return {"error": "candidate repository not available", "priorities": []}

        pending = self.candidates.list_pending(limit=200)
        if not pending:
            return {"priorities": [], "count": 0}

        hypothesis_claim_ids: set[str] = set()
        try:
            for paper in self.papers.list_papers():
                pass
            if scope_id and scope_type == "project":
                for h in self.hypotheses.list_hypotheses_for_project(scope_id):
                    for link in self.hypotheses.list_evidence_links_for_hypothesis(h.id):
                        if link.object_type == "claim":
                            hypothesis_claim_ids.add(link.object_id)
            else:
                for project in self.projects.list_projects():
                    for h in self.hypotheses.list_hypotheses_for_project(project.id):
                        for link in self.hypotheses.list_evidence_links_for_hypothesis(h.id):
                            if link.object_type == "claim":
                                hypothesis_claim_ids.add(link.object_id)
        except Exception:
            pass

        concept_controversy: dict[str, float] = {}

        priorities = []
        for candidate in pending:
            score = candidate.score or 0.0

            hypothesis_relevant = (
                candidate.source_claim_id in hypothesis_claim_ids
                or candidate.target_claim_id in hypothesis_claim_ids
            )

            controversy = 0.0
            try:
                source_claim = self.claims.get_claim(candidate.source_claim_id)
                for cid in [source_claim.subject_concept_id, source_claim.object_concept_id]:
                    if cid and cid not in concept_controversy and self.evolution:
                        snapshots = self.evolution.list_snapshots_for_concept(cid)
                        if snapshots:
                            latest = snapshots[-1]
                            concept_controversy[cid] = latest.controversy_score or 0.0
                    if cid and cid in concept_controversy:
                        controversy = max(controversy, concept_controversy[cid])
            except KeyError:
                pass

            recency = 0.0
            try:
                source_claim = self.claims.get_claim(candidate.source_claim_id)
                paper = self.papers.get_paper(source_claim.paper_id)
                if paper.year and paper.year >= 2024:
                    recency = 1.0
                elif paper.year and paper.year >= 2022:
                    recency = 0.5
            except KeyError:
                pass

            cluster_member = False
            if self.conflict_clusters is not None:
                try:
                    source_claim = self.claims.get_claim(candidate.source_claim_id)
                    for cid in [source_claim.subject_concept_id, source_claim.object_concept_id]:
                        if cid and self.conflict_clusters.list_clusters_for_concept(cid):
                            for cluster in self.conflict_clusters.list_clusters_for_concept(cid):
                                member_ids = {m.claim_id for m in self.conflict_clusters.list_members_for_cluster(cluster.id)}
                                if candidate.source_claim_id in member_ids or candidate.target_claim_id in member_ids:
                                    cluster_member = True
                                    break
                        if cluster_member:
                            break
                except KeyError:
                    pass

            priority_score = (
                score * 0.25
                + controversy * 0.25
                + (1.0 if hypothesis_relevant else 0.0) * 0.25
                + recency * 0.15
                + (1.0 if cluster_member else 0.0) * 0.1
            )

            priorities.append({
                "candidate_id": candidate.id,
                "source_claim_id": candidate.source_claim_id,
                "target_claim_id": candidate.target_claim_id,
                "relation_type": candidate.relation_type,
                "priority_score": round(priority_score, 4),
                "factors": {
                    "candidate_score": score,
                    "controversy": round(controversy, 4),
                    "hypothesis_relevant": hypothesis_relevant,
                    "recency": recency,
                    "cluster_member": cluster_member,
                },
            })

        priorities.sort(key=lambda p: p["priority_score"], reverse=True)
        return {"priorities": priorities, "count": len(priorities)}

    def compute_open_questions(self, scope_type: str = "concept", scope_id: str | None = None) -> dict:
        if self.evolution is None:
            return {"error": "evolution repository not available", "questions": []}

        questions = []

        concept_ids: list[str] = []
        if scope_id and scope_type == "concept":
            concept_ids = [scope_id]
        elif scope_id and scope_type == "project":
            links = self.projects.list_links_for_project(scope_id)
            concept_ids = [link.object_id for link in links if link.object_type == "concept"]
        else:
            seen = set()
            for paper in self.papers.list_papers():
                for claim in self.claims.list_claims_for_paper(paper.id):
                    for cid in [claim.subject_concept_id, claim.object_concept_id]:
                        if cid and cid not in seen:
                            seen.add(cid)
                            concept_ids.append(cid)
                            if len(concept_ids) >= 200:
                                break

        concept_trend: dict[str, str] = {}

        for cid in concept_ids:
            try:
                concept = self.concepts.get_concept(cid)
            except KeyError:
                continue
            snapshots = self.evolution.list_snapshots_for_concept(cid)
            if not snapshots:
                continue
            latest = snapshots[-1]

            cs = latest.controversy_score or 0.0
            if cs > 0.3 and latest.claim_count <= 5:
                questions.append({
                    "concept_id": cid,
                    "concept_name": concept.name,
                    "type": "evidence_sparse_controversy",
                    "controversy_score": cs,
                    "claim_count": latest.claim_count,
                    "description": f"'{concept.name}' has controversy score {cs:.2f} but only {latest.claim_count} claims — more evidence needed.",
                })

            if len(snapshots) >= 2:
                first = snapshots[0]
                first_cs = first.consensus_score or 0.5
                latest_cs = latest.consensus_score or 0.5
                shift = abs(latest_cs - first_cs)
                if shift > 0.3:
                    direction = "weakening consensus" if latest_cs < first_cs else "strengthening consensus"
                    concept_trend[cid] = direction
                    questions.append({
                        "concept_id": cid,
                        "concept_name": concept.name,
                        "type": "trend_shift",
                        "consensus_shift": round(shift, 4),
                        "direction": direction,
                        "description": f"'{concept.name}' shows {direction} (shift={shift:.2f}) — worth investigating.",
                    })
                else:
                    concept_trend[cid] = "stable"
            else:
                latest_cs = latest.consensus_score or 0.5
                concept_trend[cid] = "strengthening" if latest_cs >= 0.6 else "weakening" if latest_cs <= 0.4 else "stable"

        if self.conflict_clusters is not None:
            for cid in concept_ids:
                try:
                    concept = self.concepts.get_concept(cid)
                except KeyError:
                    continue
                clusters = self.conflict_clusters.list_clusters_for_concept(cid)
                for cluster in clusters:
                    members = self.conflict_clusters.list_members_for_cluster(cluster.id)
                    has_reviewed = False
                    for m in members:
                        cluster_edges = self.edges.list_claim_relation_edges(m.claim_id)
                        if any(e.created_by and "review" in e.created_by for e in cluster_edges):
                            has_reviewed = True
                            break
                    if not has_reviewed and len(members) >= 2:
                        questions.append({
                            "concept_id": cid,
                            "concept_name": concept.name,
                            "cluster_id": cluster.id,
                            "type": "unreviewed_conflict_cluster",
                            "member_count": len(members),
                            "description": f"Conflict cluster for '{concept.name}' has {len(members)} members but no reviewed relations — review is blocked.",
                        })

        try:
            project_ids_to_check: list[str] = []
            if scope_id and scope_type == "project":
                project_ids_to_check = [scope_id]
            else:
                project_ids_to_check = [p.id for p in self.projects.list_projects()]

            for project_id in project_ids_to_check:
                for h in self.hypotheses.list_hypotheses_for_project(project_id):
                    evo = self.build_hypothesis_evolution(h.id)
                    ev = evo["evidence_summary"]
                    if ev["total"] == 0 or ev["support_count"] == 0:
                        questions.append({
                            "hypothesis_id": h.id,
                            "hypothesis_text": h.text,
                            "project_id": project_id,
                            "type": "unsupported_hypothesis",
                            "evidence_total": ev["total"],
                            "description": f"Hypothesis '{h.text[:80]}' has no supporting evidence — needs claim-level evidence links.",
                        })
        except Exception:
            pass

        try:
            project_ids_to_check2: list[str] = []
            if scope_id and scope_type == "project":
                project_ids_to_check2 = [scope_id]
            else:
                project_ids_to_check2 = [p.id for p in self.projects.list_projects()]

            for project_id in project_ids_to_check2:
                for h in self.hypotheses.list_hypotheses_for_project(project_id):
                    evo = self.build_hypothesis_evolution(h.id)
                    h_trend = evo["trend"]
                    if h_trend not in ("strengthening", "weakening"):
                        continue
                    for link in self.hypotheses.list_evidence_links_for_hypothesis(h.id):
                        if link.object_type != "claim":
                            continue
                        try:
                            claim = self.claims.get_claim(link.object_id)
                        except KeyError:
                            continue
                        for concept_id_check in [claim.subject_concept_id, claim.object_concept_id]:
                            if not concept_id_check or concept_id_check not in concept_trend:
                                continue
                            c_trend = concept_trend[concept_id_check]
                            diverges = (
                                (h_trend == "strengthening" and "weakening" in c_trend)
                                or (h_trend == "weakening" and "strengthening" in c_trend)
                            )
                            if diverges:
                                try:
                                    concept = self.concepts.get_concept(concept_id_check)
                                    concept_name = concept.name
                                except KeyError:
                                    concept_name = concept_id_check
                                questions.append({
                                    "hypothesis_id": h.id,
                                    "hypothesis_text": h.text,
                                    "concept_id": concept_id_check,
                                    "concept_name": concept_name,
                                    "type": "hypothesis_concept_divergence",
                                    "hypothesis_trend": h_trend,
                                    "concept_trend": c_trend,
                                    "description": (
                                        f"Hypothesis is '{h_trend}' but concept '{concept_name}' shows '{c_trend}' — "
                                        "the hypothesis may be based on stale or inconsistent evidence."
                                    ),
                                })
                                break
        except Exception:
            pass

        return {"questions": questions, "count": len(questions)}

    def list_concept_controversies(self, min_score: float = 0.0, limit: int = 50) -> dict:
        if self.evolution is None:
            return {"error": "evolution repository not available", "concepts": []}

        concept_ids = self.evolution.list_concept_ids_with_snapshots()
        entries = []
        for cid in concept_ids:
            snapshot = self.evolution.get_latest_snapshot_for_concept(cid)
            if snapshot is None:
                continue
            score = snapshot.controversy_score or 0.0
            if score < min_score:
                continue
            try:
                concept = self.concepts.get_concept(cid)
                name = concept.name
            except KeyError:
                name = cid
            entries.append({
                "concept_id": cid,
                "concept_name": name,
                "controversy_score": round(score, 4),
                "consensus_score": round(snapshot.consensus_score or 0.0, 4),
                "claim_count": snapshot.claim_count,
                "support_count": snapshot.support_count,
                "contradiction_count": snapshot.contradiction_count,
                "snapshot_at": snapshot.snapshot_at,
            })

        entries.sort(key=lambda x: x["controversy_score"], reverse=True)
        return {"concepts": entries[:limit], "count": len(entries)}

    # ------------------------------------------------------------------
    # Conflict cluster accessors (used by OutputOps)
    # ------------------------------------------------------------------

    def global_conflict_clusters(self, limit: int = 5) -> list[dict]:
        if self.conflict_clusters is None:
            return []
        concept_ids = []
        seen: set[str] = set()
        for paper in self.papers.list_papers():
            for claim in self.claims.list_claims_for_paper(paper.id):
                for cid in [claim.subject_concept_id, claim.object_concept_id]:
                    if cid and cid not in seen:
                        seen.add(cid)
                        concept_ids.append(cid)
        results = []
        for cid in concept_ids:
            if len(results) >= limit:
                break
            clusters = self.conflict_clusters.list_clusters_for_concept(cid)
            for cluster in clusters:
                if len(results) >= limit:
                    break
                members = self.conflict_clusters.list_members_for_cluster(cluster.id)
                results.append({
                    "id": cluster.id,
                    "anchor_concept_id": cid,
                    "topic_label": cluster.topic_label,
                    "member_count": len(members),
                    "status": cluster.status,
                })
        return results

    def project_conflict_clusters(self, project_id: str, limit: int = 5) -> list[dict]:
        if self.conflict_clusters is None:
            return []
        links = self.projects.list_links_for_project(project_id)
        concept_ids = [link.object_id for link in links if link.object_type == "concept"]
        results = []
        for cid in concept_ids:
            if len(results) >= limit:
                break
            clusters = self.conflict_clusters.list_clusters_for_concept(cid)
            for cluster in clusters:
                if len(results) >= limit:
                    break
                members = self.conflict_clusters.list_members_for_cluster(cluster.id)
                results.append({
                    "id": cluster.id,
                    "anchor_concept_id": cid,
                    "topic_label": cluster.topic_label,
                    "member_count": len(members),
                    "status": cluster.status,
                })
        return results

    # ------------------------------------------------------------------
    # Project-scoped evolution summary
    # ------------------------------------------------------------------

    def project_evolution_summary(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)

        links = self.projects.list_links_for_project(project_id)
        concept_ids = [link.object_id for link in links if link.object_type == "concept"]

        concept_summaries = []
        for cid in concept_ids:
            try:
                concept = self.concepts.get_concept(cid)
            except KeyError:
                continue
            snapshots = self.evolution.list_snapshots_for_concept(cid) if self.evolution else []
            latest = snapshots[-1] if snapshots else None
            cluster_count = 0
            if self.conflict_clusters:
                cluster_count = len(self.conflict_clusters.list_clusters_for_concept(cid))
            concept_summaries.append({
                "concept_id": cid,
                "concept_name": concept.name,
                "snapshot_count": len(snapshots),
                "latest_consensus": latest.consensus_score if latest else None,
                "latest_controversy": latest.controversy_score if latest else None,
                "conflict_cluster_count": cluster_count,
            })

        hypotheses = self.hypotheses.list_hypotheses_for_project(project_id)
        hypothesis_summaries = []
        for h in hypotheses:
            evo = self.build_hypothesis_evolution(h.id)
            hypothesis_summaries.append({
                "hypothesis_id": h.id,
                "text": h.text,
                "trend": evo["trend"],
                "evidence_summary": evo["evidence_summary"],
            })

        priorities = self.compute_review_priorities(scope_type="project", scope_id=project_id)

        return {
            "project": {"id": project.id, "name": project.name},
            "concepts": concept_summaries,
            "hypotheses": hypothesis_summaries,
            "review_priorities": priorities.get("priorities", [])[:10],
        }

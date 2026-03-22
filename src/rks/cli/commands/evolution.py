from __future__ import annotations

import argparse
import json

from rks.cli._context import _open_session, _operations


def register(subparsers) -> None:
    evolution_parser = subparsers.add_parser("evolution", help="Knowledge evolution events and timeline.")
    evolution_subparsers = evolution_parser.add_subparsers(dest="evolution_command", required=True)

    evo_events_parser = evolution_subparsers.add_parser("events", help="List evolution events for a subject.")
    evo_events_parser.add_argument("subject_id", help="Subject ID (claim, concept, hypothesis).")
    evo_events_parser.add_argument("--type", dest="subject_type", default=None, help="Optional subject type filter.")
    evo_events_parser.set_defaults(handler=handle_evolution_events)

    evo_snapshot_parser = evolution_subparsers.add_parser(
        "snapshot-concept", help="Take a timeline snapshot of a concept."
    )
    evo_snapshot_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_snapshot_parser.set_defaults(handler=handle_evolution_snapshot_concept)

    evo_timeline_parser = evolution_subparsers.add_parser(
        "concept-timeline", help="Show the full timeline for a concept."
    )
    evo_timeline_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_timeline_parser.set_defaults(handler=handle_evolution_concept_timeline)

    evo_hypothesis_parser = evolution_subparsers.add_parser(
        "hypothesis", help="Show evolution view for a hypothesis."
    )
    evo_hypothesis_parser.add_argument("hypothesis_id", help="Hypothesis ID.")
    evo_hypothesis_parser.set_defaults(handler=handle_evolution_hypothesis)

    evo_bucketed_parser = evolution_subparsers.add_parser(
        "build-timeline-bucketed", help="Build time-bucketed timeline snapshots for a concept."
    )
    evo_bucketed_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_bucketed_parser.add_argument("--bucket-size", default="yearly", choices=("yearly",), help="Bucket size.")
    evo_bucketed_parser.set_defaults(handler=handle_evolution_build_timeline_bucketed)

    evo_cluster_parser = evolution_subparsers.add_parser(
        "cluster-conflicts", help="Detect and persist conflict clusters from contradicts edges."
    )
    evo_cluster_parser.add_argument("--concept-id", default=None, help="Optional concept ID to scope clustering.")
    evo_cluster_parser.set_defaults(handler=handle_evolution_cluster_conflicts)

    evo_list_clusters_parser = evolution_subparsers.add_parser(
        "list-clusters", help="List conflict clusters for a concept."
    )
    evo_list_clusters_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_list_clusters_parser.set_defaults(handler=handle_evolution_list_clusters)

    evo_project_parser = evolution_subparsers.add_parser(
        "project-summary", help="Show evolution summary for a project."
    )
    evo_project_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    evo_project_parser.set_defaults(handler=handle_evolution_project_summary)

    evo_conflict_graph_parser = evolution_subparsers.add_parser(
        "conflict-graph", help="Show the full contradiction graph for a concept (nodes + edges)."
    )
    evo_conflict_graph_parser.add_argument("concept_id", help="Concept ID, for example k_000001.")
    evo_conflict_graph_parser.set_defaults(handler=handle_evolution_conflict_graph)

    evo_hypothesis_bucketed_parser = evolution_subparsers.add_parser(
        "hypothesis-bucketed", help="Show time-bucketed evolution view for a hypothesis."
    )
    evo_hypothesis_bucketed_parser.add_argument("hypothesis_id", help="Hypothesis ID.")
    evo_hypothesis_bucketed_parser.add_argument("--bucket-size", default="yearly", choices=("yearly",), help="Bucket size.")
    evo_hypothesis_bucketed_parser.set_defaults(handler=handle_evolution_hypothesis_bucketed)

    evo_project_timeline_parser = evolution_subparsers.add_parser(
        "project-timeline", help="Show aggregate year-by-year evidence timeline for a project."
    )
    evo_project_timeline_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    evo_project_timeline_parser.set_defaults(handler=handle_evolution_project_timeline)


def handle_evolution_events(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_evolution_events(
            subject_id=args.subject_id,
            subject_type=args.subject_type,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_snapshot_concept(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_concept_timeline(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_concept_timeline(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).concept_timeline(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_hypothesis(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_hypothesis_evolution(
            hypothesis_id=args.hypothesis_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_build_timeline_bucketed(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_concept_timeline_bucketed(
            concept_id=args.concept_id,
            bucket_size=args.bucket_size,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_cluster_conflicts(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).cluster_claim_conflicts(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_list_clusters(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_conflict_clusters(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_project_summary(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_evolution_summary(
            project_id=args.project_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_conflict_graph(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).conflict_graph(
            concept_id=args.concept_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_hypothesis_bucketed(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).build_hypothesis_evolution_bucketed(
            hypothesis_id=args.hypothesis_id,
            bucket_size=args.bucket_size,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_evolution_project_timeline(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_evolution_timeline(
            project_id=args.project_id,
        )
    print(json.dumps(payload, indent=2))
    return 0

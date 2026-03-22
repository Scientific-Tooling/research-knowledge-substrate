from __future__ import annotations

import argparse
import json

from rks.cli._context import _open_session, _operations


def register(subparsers) -> None:
    project_parser = subparsers.add_parser("project", help="Create and organize research projects.")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)

    project_create_parser = project_subparsers.add_parser("create", help="Create a research project.")
    project_create_parser.add_argument("--name", required=True, help="Project name.")
    project_create_parser.add_argument("--description", help="Optional project description.")
    project_create_parser.add_argument("--research-question", help="Optional core research question.")
    project_create_parser.add_argument("--status", default="active", help="Project status label.")
    project_create_parser.add_argument("--created-by", default="human:user", help="Project creator label.")
    project_create_parser.set_defaults(handler=handle_project_create)

    project_list_parser = project_subparsers.add_parser("list", help="List research projects.")
    project_list_parser.set_defaults(handler=handle_project_list)

    project_add_paper_parser = project_subparsers.add_parser("add-paper", help="Link a paper to a project.")
    project_add_paper_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_add_paper_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    project_add_paper_parser.add_argument("--link-type", default="in_scope", help="Project-paper link label.")
    project_add_paper_parser.add_argument("--created-by", default="human:user", help="Actor label for the link.")
    project_add_paper_parser.set_defaults(handler=handle_project_add_paper)

    project_papers_parser = project_subparsers.add_parser("papers", help="List papers linked to a project.")
    project_papers_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_papers_parser.set_defaults(handler=handle_project_papers)

    project_add_link_parser = project_subparsers.add_parser("add-link", help="Link a graph object to a project.")
    project_add_link_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_add_link_parser.add_argument("object_type", choices=("paper", "claim", "method", "dataset", "concept"))
    project_add_link_parser.add_argument("object_id", help="Target object ID.")
    project_add_link_parser.add_argument("--link-type", default="in_scope", help="Project link label.")
    project_add_link_parser.add_argument("--created-by", default="human:user", help="Actor label for the link.")
    project_add_link_parser.set_defaults(handler=handle_project_add_link)

    project_links_parser = project_subparsers.add_parser("links", help="List graph objects linked to a project.")
    project_links_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    project_links_parser.add_argument("--object-type", choices=("paper", "claim", "method", "dataset", "concept"))
    project_links_parser.set_defaults(handler=handle_project_links)

    hypothesis_parser = subparsers.add_parser("hypothesis", help="Create and inspect project hypotheses.")
    hypothesis_subparsers = hypothesis_parser.add_subparsers(dest="hypothesis_command", required=True)

    hypothesis_create_parser = hypothesis_subparsers.add_parser("create", help="Create a hypothesis for a project.")
    hypothesis_create_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    hypothesis_create_parser.add_argument("--text", required=True, help="Hypothesis text.")
    hypothesis_create_parser.add_argument("--status", default="draft", help="Hypothesis status label.")
    hypothesis_create_parser.add_argument("--confidence", type=float, help="Optional confidence score.")
    hypothesis_create_parser.add_argument("--context", help="Optional JSON object describing hypothesis context.")
    hypothesis_create_parser.add_argument("--created-by", default="human:user", help="Hypothesis author label.")
    hypothesis_create_parser.set_defaults(handler=handle_hypothesis_create)

    hypothesis_list_parser = hypothesis_subparsers.add_parser("list", help="List hypotheses for a project.")
    hypothesis_list_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    hypothesis_list_parser.set_defaults(handler=handle_hypothesis_list)

    hypothesis_add_evidence_parser = hypothesis_subparsers.add_parser(
        "add-evidence",
        help="Link a paper or claim as evidence for a hypothesis.",
    )
    hypothesis_add_evidence_parser.add_argument("hypothesis_id", help="Hypothesis ID, for example h_000001.")
    hypothesis_add_evidence_parser.add_argument("object_type", choices=("paper", "claim"))
    hypothesis_add_evidence_parser.add_argument("object_id", help="Target object ID.")
    hypothesis_add_evidence_parser.add_argument("--relation-type", default="supported_by", help="Evidence relation label.")
    hypothesis_add_evidence_parser.add_argument("--note", help="Optional note stored on the evidence link.")
    hypothesis_add_evidence_parser.add_argument("--created-by", default="human:user", help="Actor label for the evidence link.")
    hypothesis_add_evidence_parser.set_defaults(handler=handle_hypothesis_add_evidence)

    hypothesis_evidence_parser = hypothesis_subparsers.add_parser("evidence", help="List evidence linked to a hypothesis.")
    hypothesis_evidence_parser.add_argument("hypothesis_id", help="Hypothesis ID, for example h_000001.")
    hypothesis_evidence_parser.set_defaults(handler=handle_hypothesis_evidence)


def handle_project_create(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).create_project(
            name=args.name,
            description=args.description,
            research_question=args.research_question,
            status=args.status,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_projects()
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_add_paper(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_project_paper(
            args.project_id,
            args.paper_id,
            link_type=args.link_type,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_papers(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_papers(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_add_link(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_project_link(
            args.project_id,
            args.object_type,
            args.object_id,
            link_type=args.link_type,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_project_links(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_links(args.project_id, object_type=args.object_type)
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_create(args: argparse.Namespace) -> int:
    context = json.loads(args.context) if args.context else None
    with _open_session() as session:
        payload = _operations(session).create_hypothesis(
            args.project_id,
            text=args.text,
            status=args.status,
            confidence=args.confidence,
            context=context,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_project_hypotheses(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_add_evidence(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).add_hypothesis_evidence(
            args.hypothesis_id,
            args.object_type,
            args.object_id,
            relation_type=args.relation_type,
            note=args.note,
            created_by=args.created_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_hypothesis_evidence(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_hypothesis_evidence(args.hypothesis_id)
    print(json.dumps(payload, indent=2))
    return 0

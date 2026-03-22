from __future__ import annotations

import argparse
import json

from rks.cli._context import _open_session, _operations


def register(subparsers) -> None:
    output_parser = subparsers.add_parser("output", help="Generate direct research outputs from the local graph.")
    output_subparsers = output_parser.add_subparsers(dest="output_command", required=True)

    output_answer_parser = output_subparsers.add_parser("answer", help="Answer a research question from the local graph.")
    output_answer_parser.add_argument("question", help="Research question text.")
    output_answer_parser.set_defaults(handler=handle_output_answer)

    output_brief_parser = output_subparsers.add_parser("brief", help="Generate a structured topic briefing.")
    output_brief_parser.add_argument("topic", help="Topic text.")
    output_brief_parser.set_defaults(handler=handle_output_brief)

    output_disagreements_parser = output_subparsers.add_parser(
        "disagreements",
        help="Surface contradictions and refinements around a topic.",
    )
    output_disagreements_parser.add_argument("topic", help="Topic text.")
    output_disagreements_parser.set_defaults(handler=handle_output_disagreements)

    output_opportunities_parser = output_subparsers.add_parser(
        "opportunities",
        help="Generate research opportunities and next-step guidance for a topic.",
    )
    output_opportunities_parser.add_argument("topic", help="Topic text.")
    output_opportunities_parser.set_defaults(handler=handle_output_opportunities)

    output_reading_list_parser = output_subparsers.add_parser(
        "reading-list",
        help="Generate a prioritized reading path for a topic.",
    )
    output_reading_list_parser.add_argument("topic", help="Topic text.")
    output_reading_list_parser.set_defaults(handler=handle_output_reading_list)

    output_compare_parser = output_subparsers.add_parser(
        "compare",
        help="Compare two claims, papers, methods, datasets, or concepts.",
    )
    output_compare_parser.add_argument("left", help="Left target text or object ID.")
    output_compare_parser.add_argument("right", help="Right target text or object ID.")
    output_compare_parser.set_defaults(handler=handle_output_compare)

    output_open_questions_parser = output_subparsers.add_parser(
        "open-questions",
        help="Surface grounded open questions for a topic.",
    )
    output_open_questions_parser.add_argument("topic", help="Topic text.")
    output_open_questions_parser.set_defaults(handler=handle_output_open_questions)

    output_review_priorities_parser = output_subparsers.add_parser(
        "review-priorities",
        help="Surface review priorities and replication risks for a topic.",
    )
    output_review_priorities_parser.add_argument("topic", help="Topic text.")
    output_review_priorities_parser.set_defaults(handler=handle_output_review_priorities)

    output_project_answer_parser = output_subparsers.add_parser(
        "project-answer",
        help="Answer a project-scoped research question from project-linked evidence.",
    )
    output_project_answer_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_answer_parser.add_argument("--question", help="Optional override question text.")
    output_project_answer_parser.set_defaults(handler=handle_output_project_answer)

    output_project_brief_parser = output_subparsers.add_parser(
        "project-brief",
        help="Generate a structured project briefing from project-linked evidence.",
    )
    output_project_brief_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_brief_parser.set_defaults(handler=handle_output_project_brief)

    output_project_disagreements_parser = output_subparsers.add_parser(
        "project-disagreements",
        help="Surface contradictions and refinements within a project scope.",
    )
    output_project_disagreements_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_disagreements_parser.set_defaults(handler=handle_output_project_disagreements)

    output_project_opportunities_parser = output_subparsers.add_parser(
        "project-opportunities",
        help="Generate research opportunities within a project scope.",
    )
    output_project_opportunities_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_opportunities_parser.set_defaults(handler=handle_output_project_opportunities)

    output_project_reading_list_parser = output_subparsers.add_parser(
        "project-reading-list",
        help="Generate a prioritized project reading path.",
    )
    output_project_reading_list_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_reading_list_parser.set_defaults(handler=handle_output_project_reading_list)

    output_project_open_questions_parser = output_subparsers.add_parser(
        "project-open-questions",
        help="Surface grounded open questions within a project scope.",
    )
    output_project_open_questions_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_open_questions_parser.set_defaults(handler=handle_output_project_open_questions)

    output_project_review_priorities_parser = output_subparsers.add_parser(
        "project-review-priorities",
        help="Surface project-scoped review priorities and replication risks.",
    )
    output_project_review_priorities_parser.add_argument("project_id", help="Project ID, for example rp_000001.")
    output_project_review_priorities_parser.set_defaults(handler=handle_output_project_review_priorities)

    plan_parser = subparsers.add_parser("plan", help="Generate deterministic research workflow plans.")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)

    plan_query_parser = plan_subparsers.add_parser("query", help="Plan the next RKS commands for a research request.")
    plan_query_parser.add_argument("request", help="Research request text.")
    plan_query_parser.add_argument("--project-id", help="Optional project scope to plan against.")
    plan_query_parser.set_defaults(handler=handle_plan_query)


def handle_output_answer(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).answer_question(args.question)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_brief(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_brief(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_disagreements(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_disagreements(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_opportunities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).research_opportunities(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_reading_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_reading_list(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_compare(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).compare_targets(args.left, args.right)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_open_questions(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_open_questions(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_review_priorities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).topic_review_priorities(args.topic)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_answer(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_answer(args.project_id, question=args.question)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_brief(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_brief(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_disagreements(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_disagreements(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_opportunities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_opportunities(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_reading_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_reading_list(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_open_questions(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_open_questions(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_output_project_review_priorities(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).project_review_priorities(args.project_id)
    print(json.dumps(payload, indent=2))
    return 0


def handle_plan_query(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).plan_query(args.request, project_id=args.project_id)
    print(json.dumps(payload, indent=2))
    return 0

from __future__ import annotations

import argparse
import json

from rks.cli._context import _open_session, _operations


def register(subparsers) -> None:
    review_parser = subparsers.add_parser("review", help="Promote or retract reviewed graph facts.")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    review_promote_parser = review_subparsers.add_parser(
        "promote-claim-relation",
        help="Persist a reviewed claim-to-claim relation.",
    )
    review_promote_parser.add_argument("source_claim_id", help="Source claim ID.")
    review_promote_parser.add_argument("relation_type", choices=("supports", "refines", "contradicts"))
    review_promote_parser.add_argument("target_claim_id", help="Target claim ID.")
    review_promote_parser.add_argument("--confidence", type=float, default=1.0)
    review_promote_parser.add_argument("--reviewed-by", default="agent:review")
    review_promote_parser.add_argument("--note", help="Optional review note to persist in edge metadata.")
    review_promote_parser.set_defaults(handler=handle_review_promote_claim_relation)

    review_retract_parser = review_subparsers.add_parser(
        "retract-claim-relation",
        help="Retract a previously reviewed claim-to-claim relation.",
    )
    review_retract_parser.add_argument("source_claim_id", help="Source claim ID.")
    review_retract_parser.add_argument("relation_type", choices=("supports", "refines", "contradicts"))
    review_retract_parser.add_argument("target_claim_id", help="Target claim ID.")
    review_retract_parser.set_defaults(handler=handle_review_retract_claim_relation)

    review_materialize_parser = review_subparsers.add_parser(
        "materialize-candidates",
        help="Materialize inferred claim relations into the candidate table.",
    )
    review_materialize_parser.add_argument("--claim-id", default=None, help="Optional claim ID to scope materialization.")
    review_materialize_parser.set_defaults(handler=handle_review_materialize_candidates)

    review_candidates_parser = review_subparsers.add_parser(
        "list-candidates",
        help="List claim relation candidates.",
    )
    review_candidates_parser.add_argument("--claim-id", default=None, help="Optional claim ID to filter.")
    review_candidates_parser.add_argument("--status", default=None, choices=("pending", "promoted", "rejected", "superseded"))
    review_candidates_parser.set_defaults(handler=handle_review_list_candidates)

    review_promote_candidate_parser = review_subparsers.add_parser(
        "promote-candidate",
        help="Promote a candidate relation into the durable graph.",
    )
    review_promote_candidate_parser.add_argument("candidate_id", help="Candidate ID.")
    review_promote_candidate_parser.add_argument("--reviewed-by", default="agent:review")
    review_promote_candidate_parser.set_defaults(handler=handle_review_promote_candidate)

    review_reject_candidate_parser = review_subparsers.add_parser(
        "reject-candidate",
        help="Reject a candidate relation.",
    )
    review_reject_candidate_parser.add_argument("candidate_id", help="Candidate ID.")
    review_reject_candidate_parser.set_defaults(handler=handle_review_reject_candidate)


def handle_review_promote_claim_relation(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).promote_claim_relation(
            source_claim_id=args.source_claim_id,
            relation_type=args.relation_type,
            target_claim_id=args.target_claim_id,
            confidence=args.confidence,
            reviewed_by=args.reviewed_by,
            note=args.note,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_retract_claim_relation(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).retract_claim_relation(
            source_claim_id=args.source_claim_id,
            relation_type=args.relation_type,
            target_claim_id=args.target_claim_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_materialize_candidates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).materialize_claim_relation_candidates(
            claim_id=args.claim_id,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_list_candidates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).list_relation_candidates(
            claim_id=args.claim_id,
            status=args.status,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_promote_candidate(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).promote_candidate(
            candidate_id=args.candidate_id,
            reviewed_by=args.reviewed_by,
        )
    print(json.dumps(payload, indent=2))
    return 0


def handle_review_reject_candidate(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).reject_candidate(
            candidate_id=args.candidate_id,
        )
    print(json.dumps(payload, indent=2))
    return 0

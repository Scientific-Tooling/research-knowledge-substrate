from __future__ import annotations

import argparse
import json

from rks.cli._context import (
    _open_session,
    _operations,
    _paper_to_payload,
    _paper_with_tags_payload,
)


def register(subparsers) -> None:
    papers_parser = subparsers.add_parser("papers", help="List and manage tracked papers.")
    papers_subparsers = papers_parser.add_subparsers(dest="papers_command", required=True)

    papers_list_parser = papers_subparsers.add_parser("list", help="List tracked papers.")
    papers_list_parser.add_argument("--limit", type=int, default=20, help="Maximum papers to return.")
    papers_list_parser.add_argument("--offset", type=int, default=0, help="Offset for pagination.")
    papers_list_parser.add_argument(
        "--sort",
        choices=("created_at", "updated_at"),
        default="created_at",
        help="Sort field for returned papers.",
    )
    papers_list_parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Sort direction.",
    )
    papers_list_parser.add_argument(
        "--tag",
        help="Optional tag filter (for example read_later).",
    )
    papers_list_parser.set_defaults(handler=handle_papers_list)

    papers_mark_parser = papers_subparsers.add_parser("mark", help="Add a tag to a paper.")
    papers_mark_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    papers_mark_parser.add_argument(
        "--tag",
        default="read_later",
        help="Tag to add (for example read_later, survey, replication).",
    )
    papers_mark_parser.set_defaults(handler=handle_papers_mark)

    papers_unmark_parser = papers_subparsers.add_parser("unmark", help="Remove a tag from a paper.")
    papers_unmark_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    papers_unmark_parser.add_argument(
        "--tag",
        required=True,
        help="Tag to remove.",
    )
    papers_unmark_parser.set_defaults(handler=handle_papers_unmark)

    papers_tags_parser = papers_subparsers.add_parser("tags", help="List tags for a paper.")
    papers_tags_parser.add_argument("paper_id", help="Paper ID, for example p_000001.")
    papers_tags_parser.set_defaults(handler=handle_papers_tags)

    papers_read_later_parser = papers_subparsers.add_parser("read-later", help="List papers marked as read_later.")
    papers_read_later_parser.add_argument("--limit", type=int, default=20, help="Maximum papers to return.")
    papers_read_later_parser.add_argument("--offset", type=int, default=0, help="Offset for pagination.")
    papers_read_later_parser.add_argument(
        "--sort",
        choices=("created_at", "updated_at"),
        default="created_at",
        help="Sort field for returned papers.",
    )
    papers_read_later_parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Sort direction.",
    )
    papers_read_later_parser.set_defaults(handler=handle_papers_read_later)

    papers_find_duplicates_parser = papers_subparsers.add_parser(
        "find-duplicates",
        help="Find likely duplicate papers by identifier and optional title matching.",
    )
    papers_find_duplicates_parser.add_argument(
        "--mode",
        choices=("title", "identifiers"),
        default="title",
        help="Detection mode. title uses DOI/arXiv/title; identifiers uses DOI/arXiv only.",
    )
    papers_find_duplicates_parser.set_defaults(handler=handle_papers_find_duplicates)

    papers_merge_parser = papers_subparsers.add_parser(
        "merge",
        help="Merge a duplicate paper into a target paper and delete the source paper.",
    )
    papers_merge_parser.add_argument("target_paper_id", help="Canonical paper ID to keep, for example p_000001.")
    papers_merge_parser.add_argument("source_paper_id", help="Duplicate paper ID to merge and remove.")
    papers_merge_parser.add_argument(
        "--prefer",
        choices=("target", "source"),
        default="target",
        help="When both papers have the same field or artifact type, prefer target or source.",
    )
    papers_merge_parser.set_defaults(handler=handle_papers_merge)


def handle_papers_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        papers = session.papers.list_recent_papers(
            limit=args.limit,
            offset=args.offset,
            sort_by=args.sort,
            order=args.order,
            tag=args.tag,
        )
        total = session.papers.count_papers(tag=args.tag)
        payload_papers = [_paper_with_tags_payload(session.papers, paper) for paper in papers]
    payload = {
        "count": len(papers),
        "total_count": total,
        "limit": args.limit,
        "offset": args.offset,
        "sort": args.sort,
        "order": args.order,
        "tag": args.tag,
        "papers": payload_papers,
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_mark(args: argparse.Namespace) -> int:
    with _open_session() as session:
        added = session.papers.add_tag(args.paper_id, args.tag)
        paper = session.papers.get_paper(args.paper_id)
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = {
        "paper_id": paper.id,
        "tag": args.tag.strip().lower(),
        "added": added,
        "tags": tags,
        "paper": _paper_to_payload(paper),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_unmark(args: argparse.Namespace) -> int:
    with _open_session() as session:
        deleted = session.papers.remove_tag(args.paper_id, args.tag)
        paper = session.papers.get_paper(args.paper_id)
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = {
        "paper_id": paper.id,
        "tag": args.tag.strip().lower(),
        "deleted": deleted,
        "tags": tags,
        "paper": _paper_to_payload(paper),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_tags(args: argparse.Namespace) -> int:
    with _open_session() as session:
        paper = session.papers.get_paper(args.paper_id)
        tags = session.papers.list_tags_for_paper(args.paper_id)
    payload = {
        "paper_id": paper.id,
        "tags": tags,
        "paper": _paper_to_payload(paper),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_read_later(args: argparse.Namespace) -> int:
    with _open_session() as session:
        papers = session.papers.list_recent_papers(
            limit=args.limit,
            offset=args.offset,
            sort_by=args.sort,
            order=args.order,
            tag="read_later",
        )
        total = session.papers.count_papers(tag="read_later")
        payload_papers = [_paper_with_tags_payload(session.papers, paper) for paper in papers]
    payload = {
        "count": len(papers),
        "total_count": total,
        "limit": args.limit,
        "offset": args.offset,
        "sort": args.sort,
        "order": args.order,
        "tag": "read_later",
        "papers": payload_papers,
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_find_duplicates(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).find_duplicate_papers(mode=args.mode)
    print(json.dumps(payload, indent=2))
    return 0


def handle_papers_merge(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = _operations(session).merge_papers(
            args.target_paper_id,
            args.source_paper_id,
            prefer=args.prefer,
        )
    print(json.dumps(payload, indent=2))
    return 0

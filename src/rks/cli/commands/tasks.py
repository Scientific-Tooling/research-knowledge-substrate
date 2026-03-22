from __future__ import annotations

import argparse
import json
import sys

from rks.agent import record_task_report
from rks.config import load_paths
from rks.cli._context import _open_session, _task_payload


def register(subparsers) -> None:
    tasks_parser = subparsers.add_parser("tasks", help="Inspect or update queued agent tasks.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command", required=True)

    tasks_list_parser = tasks_subparsers.add_parser("list", help="List queued, completed, or failed tasks.")
    tasks_list_parser.add_argument("--paper-id", help="Filter by paper ID.")
    tasks_list_parser.add_argument("--status", help="Filter by status.")
    tasks_list_parser.set_defaults(handler=handle_tasks_list)

    tasks_show_parser = tasks_subparsers.add_parser("show", help="Show one task.")
    tasks_show_parser.add_argument("task_id", help="Task ID, for example t_000001.")
    tasks_show_parser.set_defaults(handler=handle_tasks_show)

    tasks_fail_parser = tasks_subparsers.add_parser("fail", help="Mark a task as failed.")
    tasks_fail_parser.add_argument("task_id", help="Task ID, for example t_000001.")
    tasks_fail_parser.add_argument("message", help="Failure message to record.")
    tasks_fail_parser.set_defaults(handler=handle_tasks_fail)

    tasks_wait_parser = tasks_subparsers.add_parser(
        "wait",
        help="Block until a task reaches a terminal state (completed or failed).",
    )
    tasks_wait_parser.add_argument("task_id", help="Task ID, for example t_000001.")
    tasks_wait_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Maximum seconds to wait before giving up (default: 300).",
    )
    tasks_wait_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Poll interval in seconds (default: 2).",
    )
    tasks_wait_parser.set_defaults(handler=handle_tasks_wait)


def handle_tasks_list(args: argparse.Namespace) -> int:
    with _open_session() as session:
        tasks = session.tasks.list_tasks(paper_id=args.paper_id, status=args.status)
    print(json.dumps([_task_payload(task) for task in tasks], indent=2))
    return 0


def handle_tasks_show(args: argparse.Namespace) -> int:
    with _open_session() as session:
        task = session.tasks.get_task(args.task_id)
    print(json.dumps(_task_payload(task), indent=2))
    return 0


def handle_tasks_fail(args: argparse.Namespace) -> int:
    with _open_session() as session:
        task = session.tasks.fail_task(args.task_id, args.message)
        record_task_report(session.papers, load_paths(), task, note="Task marked as failed.", error={"message": args.message})
    print(json.dumps(_task_payload(task), indent=2))
    return 0


def handle_tasks_wait(args: argparse.Namespace) -> int:
    import time

    terminal = {"completed", "failed"}
    deadline = time.monotonic() + args.timeout
    while True:
        with _open_session() as session:
            task = session.tasks.get_task(args.task_id)
        if task.status in terminal:
            print(json.dumps(_task_payload(task), indent=2))
            return 0 if task.status == "completed" else 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                json.dumps(
                    {
                        "error": "timeout",
                        "message": f"Task {args.task_id} did not reach a terminal state within {args.timeout}s.",
                        "task": _task_payload(task),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        time.sleep(min(args.interval, remaining))

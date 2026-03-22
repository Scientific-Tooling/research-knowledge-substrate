from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks.config import load_paths
from rks.storage import export_graph_snapshot
from rks.storage.workspace import export_workspace
from rks.cli._context import _open_session


def register(subparsers) -> None:
    export_parser = subparsers.add_parser("export", help="Export graph data.")
    export_subparsers = export_parser.add_subparsers(dest="export_command", required=True)

    export_graph_parser = export_subparsers.add_parser("graph", help="Export a graph snapshot JSON file.")
    export_graph_parser.add_argument("json_path", type=Path, help="Destination path for the graph snapshot.")
    export_graph_parser.set_defaults(handler=handle_export_graph)

    export_workspace_parser = export_subparsers.add_parser(
        "workspace", help="Export a portable workspace archive (.tar.gz) with all data and files."
    )
    export_workspace_parser.add_argument(
        "archive_path", type=Path, help="Destination path for the workspace archive (e.g. my_workspace.tar.gz)."
    )
    export_workspace_parser.set_defaults(handler=handle_export_workspace)


def handle_export_graph(args: argparse.Namespace) -> int:
    with _open_session() as session:
        payload = export_graph_snapshot(session.papers.conn, args.json_path)
    print(json.dumps(payload, indent=2))
    return 0


def handle_export_workspace(args: argparse.Namespace) -> int:
    paths = load_paths()
    with _open_session() as session:
        payload = export_workspace(session.papers.conn, paths.data_dir, args.archive_path)
    print(json.dumps(payload, indent=2))
    return 0

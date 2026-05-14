from __future__ import annotations

import argparse
import json
from pathlib import Path

from rks import __version__
from rks.agent_skills import SKILL_BUNDLE_VERSION, export_bundled_skills, list_bundled_skills
from rks.config import (
    ConfigError,
    global_config_path,
    load_app_config,
    load_global_config,
    load_paths,
    write_global_config,
)
from rks.storage import connect_db, initialize_db
from rks.storage.db import (
    apply_migrations,
    audit_referential_integrity,
    connect_db_readonly,
    current_schema_version,
    list_migration_files,
)
from rks.cli._context import _open_repository, _doctor_recommended_actions, _open_session, _operations


def register(subparsers) -> None:
    # init
    init_parser = subparsers.add_parser("init", help="Set the global RKS data directory and initialize the database.")
    init_parser.add_argument("path", type=Path, help="Directory to store RKS data (PDFs, database, artifacts).")
    init_parser.set_defaults(handler=handle_init)

    # init-db
    init_db_parser = subparsers.add_parser("init-db", help="Initialize the RKS SQLite database (requires prior `rks init`).")
    init_db_parser.set_defaults(handler=handle_init_db)

    # clear
    clear_parser = subparsers.add_parser("clear", help="Delete all papers, artifacts, and the database. Keeps global config.")
    clear_parser.add_argument("--yes", action="store_true", help="Confirm deletion. Required to actually clear data.")
    clear_parser.set_defaults(handler=handle_clear)

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="Run installation and environment self-checks.")
    doctor_parser.set_defaults(handler=handle_doctor)

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Apply schema migrations and report the current version.")
    migrate_parser.set_defaults(handler=handle_migrate)

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show workspace counts and storage coverage metrics.")
    stats_parser.set_defaults(handler=handle_stats)

    # extraction-quality
    extraction_quality_parser = subparsers.add_parser(
        "extraction-quality", help="Show extraction quality metrics across all papers."
    )
    extraction_quality_parser.set_defaults(handler=handle_extraction_quality)

    # evaluate
    evaluate_parser = subparsers.add_parser("evaluate", help="Run quality baseline checks.")
    evaluate_subparsers = evaluate_parser.add_subparsers(dest="evaluate_command", required=True)

    evaluate_baseline_parser = evaluate_subparsers.add_parser(
        "baseline",
        help="Evaluate extraction quality metrics against a baseline spec JSON.",
    )
    evaluate_baseline_parser.add_argument("spec_path", type=Path, help="Path to a baseline spec JSON file.")
    evaluate_baseline_parser.set_defaults(handler=handle_evaluate_baseline)

    evaluate_claims_parser = evaluate_subparsers.add_parser(
        "claims",
        help="Evaluate extracted claims for a paper against a golden set using fuzzy text similarity.",
    )
    evaluate_claims_parser.add_argument("paper_id", help="Paper ID, e.g. p_000001.")
    evaluate_claims_parser.add_argument(
        "--golden", type=Path, required=True, metavar="PATH",
        help="Path to a JSON file containing a list of expected claim text strings.",
    )
    evaluate_claims_parser.add_argument(
        "--min-f1", type=float, default=None, metavar="THRESHOLD",
        help="Exit 1 if the F1 score is below this threshold.",
    )
    evaluate_claims_parser.set_defaults(handler=handle_evaluate_claims)

    # config
    config_parser = subparsers.add_parser("config", help="Manage RKS configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_show_parser = config_subparsers.add_parser("show", help="Show the effective configuration and global config path.")
    config_show_parser.set_defaults(handler=handle_config_show)

    config_set_parser = config_subparsers.add_parser("set", help="Set a configuration value in the global config.")
    config_set_subparsers = config_set_parser.add_subparsers(dest="config_set_key", required=True)

    config_set_data_dir_parser = config_set_subparsers.add_parser("data-dir", help="Set the global data directory path.")
    config_set_data_dir_parser.add_argument("path", type=Path, help="Absolute or relative path to the data directory.")
    config_set_data_dir_parser.set_defaults(handler=handle_config_set_data_dir)

    # skills
    skills_parser = subparsers.add_parser("skills", help="Inspect or export bundled agent skills.")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)

    skills_list_parser = skills_subparsers.add_parser("list", help="List bundled agent skills.")
    skills_list_parser.set_defaults(handler=handle_skills_list)

    skills_export_parser = skills_subparsers.add_parser("export", help="Export bundled agent skills to a directory.")
    skills_export_parser.add_argument("destination", type=Path, help="Directory to write the exported skill bundle into.")
    skills_export_parser.set_defaults(handler=handle_skills_export)

    # serve
    serve_parser = subparsers.add_parser("serve", help="Run the local RKS API and lightweight UI.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.set_defaults(handler=handle_serve)


def handle_init(args: argparse.Namespace) -> int:
    data_dir = args.path.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    global_cfg = load_global_config()
    global_cfg["data_dir"] = str(data_dir)
    cfg_path = write_global_config(global_cfg)
    db_path = data_dir / "rks.sqlite3"
    conn = connect_db(db_path)
    try:
        initialize_db(conn)
        apply_migrations(conn)
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "data_dir": str(data_dir),
                "global_config": str(cfg_path),
                "db_path": str(db_path),
            },
            indent=2,
        )
    )
    return 0


def handle_init_db(args: argparse.Namespace) -> int:
    del args
    with _open_repository() as repo:
        print(json.dumps({"status": "ok", "db_initialized": True}, indent=2))
    return 0


def handle_clear(args: argparse.Namespace) -> int:
    import shutil
    paths = load_paths()
    if not args.yes:
        print(
            json.dumps(
                {
                    "status": "aborted",
                    "reason": "Pass --yes to confirm. This will permanently delete all papers, artifacts, and the database.",
                    "data_dir": str(paths.data_dir),
                },
                indent=2,
            )
        )
        return 1
    removed = []
    for target in (paths.db_path, paths.papers_dir, paths.artifacts_dir):
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(str(target))
    conn = connect_db(paths.db_path)
    try:
        initialize_db(conn)
        apply_migrations(conn)
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "data_dir": str(paths.data_dir),
                "removed": removed,
                "db_reinitialized": True,
            },
            indent=2,
        )
    )
    return 0


def handle_config_show(args: argparse.Namespace) -> int:
    del args
    gcfg_path = global_config_path()
    global_cfg = load_global_config()
    try:
        app_config = load_app_config()
        effective: dict = {
            "data_dir": str(app_config.data_dir),
            "reference_pdf_acquisition": app_config.reference_pdf_acquisition,
            "llm": {
                "base_url": app_config.llm_base_url,
                "model": app_config.llm_model,
                "api_key_env": app_config.llm_api_key_env,
            },
        }
    except ConfigError:
        effective = None
    print(
        json.dumps(
            {
                "global_config_path": str(gcfg_path),
                "global_config_exists": gcfg_path.exists(),
                "effective": effective,
                "raw_global_config": global_cfg,
            },
            indent=2,
        )
    )
    return 0


def handle_config_set_data_dir(args: argparse.Namespace) -> int:
    data_dir = args.path.expanduser().resolve()
    global_cfg = load_global_config()
    old_value = global_cfg.get("data_dir")
    global_cfg["data_dir"] = str(data_dir)
    cfg_path = write_global_config(global_cfg)
    print(
        json.dumps(
            {
                "status": "ok",
                "global_config": str(cfg_path),
                "data_dir": str(data_dir),
                "previous_data_dir": old_value,
            },
            indent=2,
        )
    )
    return 0


def handle_skills_list(args: argparse.Namespace) -> int:
    del args
    payload = [
        {"name": skill.name, "description": skill.description}
        for skill in list_bundled_skills()
    ]
    print(json.dumps(payload, indent=2))
    return 0


def handle_skills_export(args: argparse.Namespace) -> int:
    payload = export_bundled_skills(args.destination)
    print(json.dumps(payload, indent=2))
    return 0


def handle_doctor(args: argparse.Namespace) -> int:
    del args
    gcfg_path = global_config_path()
    global_cfg_exists = gcfg_path.exists()
    global_cfg_has_data_dir = "data_dir" in load_global_config()

    try:
        app_config = load_app_config()
        paths = load_paths()
        data_dir_exists = paths.data_dir.exists()
        db_exists = paths.db_path.exists()
        data_dir_str = str(paths.data_dir)
        db_path_str = str(paths.db_path)
        if db_exists:
            conn = connect_db_readonly(paths.db_path)
            try:
                integrity = audit_referential_integrity(conn)
            finally:
                conn.close()
        else:
            integrity = {"ok": False, "total_orphan_count": None, "orphan_counts": {}}
    except ConfigError:
        data_dir_exists = False
        db_exists = False
        data_dir_str = None
        db_path_str = None
        integrity = {"ok": False, "total_orphan_count": None, "orphan_counts": {}}

    checks = {
        "global_config": {
            "ok": global_cfg_has_data_dir,
            "path": str(gcfg_path),
        },
        "data_dir": {
            "ok": data_dir_exists,
            "path": data_dir_str,
        },
        "database": {
            "ok": db_exists,
            "path": db_path_str,
        },
        "database_integrity": integrity,
        "migrations": {
            "ok": True,
            "count": len(list_migration_files()),
        },
        "bundled_skills": {
            "ok": True,
            "bundle_version": SKILL_BUNDLE_VERSION,
            "skill_count": len(list_bundled_skills()),
        },
    }
    overall_status = "ok" if all(item["ok"] for item in checks.values()) else "action_required"
    payload = {
        "version": __version__,
        "overall_status": overall_status,
        "paths": {
            "global_config": str(gcfg_path),
            "data_dir": data_dir_str,
            "db_path": db_path_str,
        },
        "checks": checks,
        "recommended_actions": _doctor_recommended_actions(checks),
    }
    print(json.dumps(payload, indent=2))
    return 0


def handle_migrate(args: argparse.Namespace) -> int:
    del args
    paths = load_paths()
    conn = connect_db(paths.db_path)
    try:
        payload = apply_migrations(conn)
        initialize_db(conn)
        payload["current_version"] = current_schema_version(conn)
        print(json.dumps(payload, indent=2))
    finally:
        conn.close()
    return 0


def handle_extraction_quality(args: argparse.Namespace) -> int:
    del args
    with _open_session() as session:
        payload = _operations(session).extraction_quality_report()
    print(json.dumps(payload, indent=2))
    return 0


def handle_stats(args: argparse.Namespace) -> int:
    del args
    with _open_session() as session:
        payload = _operations(session).workspace_stats()
    print(json.dumps(payload, indent=2))
    return 0


def handle_evaluate_baseline(args: argparse.Namespace) -> int:
    from rks.cli._context import _load_json_object, _normalize_baseline_checks, _evaluate_baseline_metrics
    spec = _load_json_object(args.spec_path, "baseline spec")
    checks = _normalize_baseline_checks(spec)
    with _open_session() as session:
        metrics = _operations(session).extraction_quality_report()
    evaluation = _evaluate_baseline_metrics(metrics, checks)
    payload = {
        "baseline_name": spec.get("name"),
        "spec_path": str(args.spec_path.resolve()),
        "passed": evaluation["passed"],
        "check_count": len(evaluation["checks"]),
        "failed_check_count": len(evaluation["failed_checks"]),
        "failed_checks": evaluation["failed_checks"],
        "checks": evaluation["checks"],
        "metrics": metrics,
    }
    print(json.dumps(payload, indent=2))
    return 0 if evaluation["passed"] else 1


def handle_evaluate_claims(args: argparse.Namespace) -> int:
    import sys
    from rks.cli._context import _evaluate_claims_against_golden
    golden_raw = json.loads(args.golden.read_text(encoding="utf-8"))
    if not isinstance(golden_raw, list):
        print(json.dumps({"error": "Golden file must be a JSON array of strings."}), file=sys.stderr)
        return 1
    golden_texts = [str(item) for item in golden_raw]
    with _open_session() as session:
        claims = session.claims.list_claims_for_paper(args.paper_id)
    actual_texts = [c.text for c in claims]
    result = _evaluate_claims_against_golden(actual_texts, golden_texts)
    passed = True
    if args.min_f1 is not None:
        passed = result["f1"] >= args.min_f1
    payload = {
        "paper_id": args.paper_id,
        "golden_count": len(golden_texts),
        "actual_count": len(actual_texts),
        "precision": result["precision"],
        "recall": result["recall"],
        "f1": result["f1"],
        "min_f1": args.min_f1,
        "passed": passed,
        "matched_pairs": result["matched_pairs"],
    }
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


def handle_serve(args: argparse.Namespace) -> int:
    from rks.service import serve_http
    serve_http(args.host, args.port)
    return 0

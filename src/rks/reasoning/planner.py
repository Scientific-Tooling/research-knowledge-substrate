from __future__ import annotations

import re


_COMPARE_PATTERNS = [
    re.compile(r"^\s*compare\s+(.+?)\s+with\s+(.+?)\s*$", flags=re.IGNORECASE),
    re.compile(r"^\s*compare\s+(.+?)\s+vs\.?\s+(.+?)\s*$", flags=re.IGNORECASE),
    re.compile(r"^\s*(.+?)\s+vs\.?\s+(.+?)\s*$", flags=re.IGNORECASE),
]


def plan_research_request(request: str, *, project: dict | None = None) -> dict:
    normalized_request = request.strip()
    if not normalized_request:
        raise ValueError("request must not be empty")

    compare_targets = _compare_targets(normalized_request)
    intent = _infer_intent(normalized_request, compare_targets is not None, project is not None)
    scope = _scope_payload(project, normalized_request)
    steps = _plan_steps(intent, scope, normalized_request, compare_targets)
    return {
        "planner_version": "deterministic.v1",
        "request": normalized_request,
        "intent": intent,
        "scope": scope,
        "compare_targets": None if compare_targets is None else {"left": compare_targets[0], "right": compare_targets[1]},
        "recommended_surface": steps[-1]["surface"] if steps else None,
        "steps": steps,
    }


def _scope_payload(project: dict | None, request: str) -> dict:
    if project is not None:
        return {
            "type": "project",
            "id": project["id"],
            "label": project["name"],
            "research_question": project.get("research_question"),
        }
    return {
        "type": "topic",
        "id": None,
        "label": request,
    }


def _infer_intent(request: str, is_compare: bool, has_project_scope: bool) -> str:
    lowered = request.lower()
    if is_compare:
        return "compare"
    if any(token in lowered for token in ("reading list", "what should i read", "reading path", "what to read")):
        return "reading_list"
    if any(token in lowered for token in ("open question", "unknown", "unresolved", "uncertain")):
        return "open_questions"
    if any(token in lowered for token in ("review priority", "replication risk", "what should be reviewed", "review risk", "review next")):
        return "review_priorities"
    if "review" in lowered and "next" in lowered:
        return "review_priorities"
    if any(token in lowered for token in ("opportunit", "next step", "what should we do next", "what next")):
        return "opportunities"
    if any(token in lowered for token in ("disagree", "contradict", "conflict", "refine")):
        return "disagreements"
    if any(token in lowered for token in ("brief", "overview", "summarize", "summary", "state of")):
        return "brief"
    if has_project_scope:
        return "project_answer"
    return "answer"


def _compare_targets(request: str) -> tuple[str, str] | None:
    for pattern in _COMPARE_PATTERNS:
        match = pattern.match(request)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return None


def _plan_steps(intent: str, scope: dict, request: str, compare_targets: tuple[str, str] | None) -> list[dict]:
    if intent == "compare" and compare_targets is not None:
        return [
            {
                "step": "resolve_targets",
                "reason": "A comparison request needs two concrete graph targets.",
                "surface": "compare",
                "cli_command": f'rks output compare "{compare_targets[0]}" "{compare_targets[1]}"',
            },
            {
                "step": "inspect_comparison",
                "reason": "The comparison surface returns shared points, differences, and recommendations.",
                "surface": "compare",
                "cli_command": f'rks output compare "{compare_targets[0]}" "{compare_targets[1]}"',
            },
        ]

    if scope["type"] == "project":
        project_id = scope["id"]
        project_label = scope["label"]
        question = scope.get("research_question") or request
        surface_map = {
            "brief": ("project_brief", f"rks output project-brief {project_id}"),
            "disagreements": ("project_disagreements", f"rks output project-disagreements {project_id}"),
            "opportunities": ("project_opportunities", f"rks output project-opportunities {project_id}"),
            "reading_list": ("project_reading_list", f"rks output project-reading-list {project_id}"),
            "open_questions": ("project_open_questions", f"rks output project-open-questions {project_id}"),
            "review_priorities": ("project_review_priorities", f"rks output project-review-priorities {project_id}"),
            "project_answer": ("project_answer", f'rks output project-answer {project_id} --question "{question}"'),
        }
        surface, command = surface_map.get(intent, surface_map["project_answer"])
        return [
            {
                "step": "inspect_project_scope",
                "reason": "Project-scoped planning should start from explicit project links and hypotheses.",
                "surface": "show_project",
                "cli_command": f"rks show project {project_id}",
            },
            {
                "step": "inspect_project_hypotheses",
                "reason": f"{project_label} may include hypotheses that frame the evidence review.",
                "surface": "project_hypotheses",
                "cli_command": f"rks hypothesis list {project_id}",
            },
            {
                "step": "generate_project_output",
                "reason": "Run the project-scoped output surface that matches the inferred intent.",
                "surface": surface,
                "cli_command": command,
            },
        ]

    surface_map = {
        "brief": ("brief", f'rks output brief "{request}"'),
        "disagreements": ("disagreements", f'rks output disagreements "{request}"'),
        "opportunities": ("opportunities", f'rks output opportunities "{request}"'),
        "reading_list": ("reading_list", f'rks output reading-list "{request}"'),
        "open_questions": ("open_questions", f'rks output open-questions "{request}"'),
        "review_priorities": ("review_priorities", f'rks output review-priorities "{request}"'),
        "answer": ("answer", f'rks output answer "{request}"'),
    }
    surface, command = surface_map.get(intent, surface_map["answer"])
    return [
        {
            "step": "search_graph",
            "reason": "Start from lexical and semantic retrieval over the existing graph.",
            "surface": "search",
            "cli_command": f'rks search "{request}"',
        },
        {
            "step": "generate_output",
            "reason": "Run the output surface that best matches the inferred intent.",
            "surface": surface,
            "cli_command": command,
        },
    ]

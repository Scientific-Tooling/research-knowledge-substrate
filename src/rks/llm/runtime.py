from __future__ import annotations


def run_dual_track_mode(
    mode: str,
    *,
    llm_api,
    agent,
):
    if mode == "llm-api":
        return llm_api()
    if mode == "agent":
        return agent()
    raise ValueError(f"Unsupported mode: {mode}")

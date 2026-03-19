from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rks.service.mcp import RksMcpServer


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "rks", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class McpServiceTest(unittest.TestCase):
    def _call_rpc(self, server: RksMcpServer, method: str, params: dict | None = None, request_id: int = 1) -> dict:
        request = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        response = server.handle_message(request)
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("result", response)
        return response["result"]

    def _call_tool(self, server: RksMcpServer, name: str, arguments: dict, request_id: int = 10) -> dict:
        result = self._call_rpc(
            server,
            "tools/call",
            params={"name": name, "arguments": arguments},
            request_id=request_id,
        )
        self.assertFalse(result.get("isError"), result)
        return result["structuredContent"]

    def test_mcp_tools_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "mcp-paper.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.4\n"
                b"Transformer improves translation quality on WMT14.\n"
                b"Diffusion model reduces image artifacts for generation.\n"
            )

            init_result = run_cli("init-db", cwd=tmp_path)
            self.assertEqual(init_result.returncode, 0, init_result.stderr)

            ingest_result = run_cli("ingest", "pdf", str(pdf_path), cwd=tmp_path)
            self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
            paper_id = json.loads(ingest_result.stdout)["id"]

            extract_result = run_cli("extract", "claims", paper_id, cwd=tmp_path)
            self.assertEqual(extract_result.returncode, 0, extract_result.stderr)

            with patch.dict(os.environ, {"RKS_ROOT": str(tmp_path)}, clear=False):
                server = RksMcpServer()

                tools_payload = self._call_rpc(server, "tools/list", request_id=2)
                tool_names = {entry["name"] for entry in tools_payload["tools"]}
                self.assertIn("search_papers", tool_names)
                self.assertIn("chat_with_paper", tool_names)

                search_payload = self._call_tool(
                    server,
                    "search_papers",
                    {"query": "mcp-paper", "mode": "hybrid", "filters": {"limit": 5}},
                    request_id=3,
                )
                self.assertGreaterEqual(search_payload["count"], 1)
                self.assertEqual(search_payload["papers"][0]["id"], paper_id)

                paper_payload = self._call_tool(server, "get_paper", {"paper_id": paper_id}, request_id=4)
                self.assertEqual(paper_payload["paper"]["id"], paper_id)
                self.assertGreaterEqual(len(paper_payload["sections"]), 1)

                sections_payload = self._call_tool(server, "get_sections", {"paper_id": paper_id}, request_id=5)
                self.assertGreaterEqual(sections_payload["section_count"], 1)

                passages_payload = self._call_tool(
                    server,
                    "retrieve_passages",
                    {"paper_id": paper_id, "question": "What improves translation quality?", "top_k": 3},
                    request_id=6,
                )
                self.assertGreaterEqual(len(passages_payload["passages"]), 1)
                top_chunk_id = passages_payload["passages"][0]["chunk_id"]

                citation_payload = self._call_tool(
                    server,
                    "get_citation_spans",
                    {"paper_id": paper_id, "chunk_ids": [top_chunk_id]},
                    request_id=7,
                )
                self.assertEqual(len(citation_payload["spans"]), 1)
                self.assertEqual(citation_payload["spans"][0]["chunk_id"], top_chunk_id)

                chat_payload = self._call_tool(
                    server,
                    "chat_with_paper",
                    {
                        "session_id": "session_demo",
                        "paper_ids": [paper_id],
                        "message": "这篇文献关于 translation quality 的核心结论是什么？",
                    },
                    request_id=8,
                )
                self.assertEqual(chat_payload["session_id"], "session_demo")
                self.assertEqual(chat_payload["paper_ids"], [paper_id])
                self.assertTrue(chat_payload["answer"])

                note_payload = self._call_tool(
                    server,
                    "save_note",
                    {
                        "session_id": "session_demo",
                        "paper_id": paper_id,
                        "note": "Need to manually compare with follow-up studies.",
                    },
                    request_id=9,
                )
                self.assertEqual(note_payload["note"]["target_id"], paper_id)

                notes_payload = self._call_tool(
                    server,
                    "list_notes",
                    {"paper_id": paper_id},
                    request_id=10,
                )
                self.assertGreaterEqual(len(notes_payload["notes"]), 1)


if __name__ == "__main__":
    unittest.main()

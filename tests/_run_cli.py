from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rks.cli.main import main as _rks_main


class _CliResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_cli(*args: str, cwd: Path) -> _CliResult:
    """Call rks CLI in-process with RKS_DATA_DIR set to cwd.

    Drop-in for the subprocess-based helper: returns an object with
    .returncode, .stdout, and .stderr attributes.
    """
    old_val = os.environ.get("RKS_DATA_DIR")
    os.environ["RKS_DATA_DIR"] = str(cwd)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    returncode = 0
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            result = _rks_main(list(args))
        returncode = int(result) if result is not None else 0
    except SystemExit as exc:
        returncode = int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except Exception:
        import traceback
        stderr_buf.write(traceback.format_exc())
        returncode = 1
    finally:
        if old_val is None:
            os.environ.pop("RKS_DATA_DIR", None)
        else:
            os.environ["RKS_DATA_DIR"] = old_val
    return _CliResult(returncode=returncode, stdout=stdout_buf.getvalue(), stderr=stderr_buf.getvalue())

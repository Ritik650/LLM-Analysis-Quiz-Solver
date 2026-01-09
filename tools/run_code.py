"""
Code executor (E5-hardened).

This tool runs arbitrary LLM-generated Python. That is inherently dangerous, so
we constrain it as much as is portable without a nested container:

  * **Wall-clock timeout** (portable): the process is killed if it runs longer
    than ``RUN_CODE_TIMEOUT`` seconds.
  * **CPU-time limit** (POSIX): ``RLIMIT_CPU`` caps burned CPU seconds so a busy
    loop can't monopolise a core.
  * **File-descriptor limit** (POSIX): ``RLIMIT_NOFILE`` caps open handles.
  * **Memory cap** (POSIX, opt-in): ``RLIMIT_AS`` when ``RUN_CODE_ENFORCE_MEM``
    is set. Off by default because address-space caps frequently break
    numpy/pandas/BLAS, which over-reserve virtual memory.
  * **Network guard** (opt-in): when ``RUN_CODE_ALLOW_NETWORK`` is false, a
    best-effort socket block is prepended to the code.
  * **Isolated cwd** (``LLMFiles/``) and **output truncation**.

Residual risk (documented in the README threat model): full network + FS
isolation requires nsjail / a nested container. On Windows dev, POSIX rlimits
are unavailable and only the wall-clock timeout applies.
"""
from __future__ import annotations

import os
import subprocess

from langchain_core.tools import tool

from config import get_settings

_settings = get_settings()
_MAX_OUTPUT = 10000

_NETWORK_GUARD = (
    "import socket as _socket\n"
    "def _blocked(*a, **k):\n"
    "    raise OSError('network access disabled by sandbox policy')\n"
    "_socket.socket = _blocked\n"
    "_socket.create_connection = _blocked\n"
)


def strip_code_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else ""
    if code.endswith("```"):
        code = code.rsplit("\n", 1)[0]
    return code.strip()


def _build_preexec():
    """Return a preexec_fn applying POSIX rlimits, or None (e.g. on Windows)."""
    if os.name != "posix":
        return None
    try:
        import resource
    except ImportError:
        return None

    cpu = _settings.run_code_cpu_seconds
    mem_bytes = _settings.run_code_mem_mb * 1024 * 1024
    enforce_mem = _settings.run_code_enforce_mem

    def _limits() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        if enforce_mem:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    return _limits


def _truncate(text: str) -> str:
    if len(text) >= _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + "...truncated due to large size"
    return text


@tool
def run_code(code: str) -> dict:
    """
    Execute Python code in a resource-limited subprocess.

    The code is written to ``LLMFiles/runner.py`` and run via ``uv run`` under
    CPU-time, wall-clock, and file-descriptor limits.

    Parameters
    ----------
    code : str
        Python source code to execute.

    Returns
    -------
    dict
        {"stdout": <program output>, "stderr": <errors>, "return_code": <exit code>}
    """
    try:
        code = strip_code_fences(code)
        if not _settings.run_code_allow_network:
            code = _NETWORK_GUARD + code

        os.makedirs("LLMFiles", exist_ok=True)
        with open(os.path.join("LLMFiles", "runner.py"), "w", encoding="utf-8") as f:
            f.write(code)

        proc = subprocess.Popen(
            ["uv", "run", "runner.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd="LLMFiles",
            preexec_fn=_build_preexec(),
        )
        try:
            stdout, stderr = proc.communicate(timeout=_settings.run_code_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {
                "stdout": _truncate(stdout or ""),
                "stderr": f"Execution killed: exceeded {_settings.run_code_timeout}s wall-clock limit.\n"
                + _truncate(stderr or ""),
                "return_code": -9,
            }

        return {
            "stdout": _truncate(stdout),
            "stderr": _truncate(stderr),
            "return_code": proc.returncode,
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "return_code": -1}

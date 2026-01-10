"""Unit tests for the individual tools (network/subprocess mocked or local).

NOTE: ``tools/__init__.py`` does ``from .download_file import download_file``,
which rebinds the ``tools.download_file`` *attribute* to the tool object. So we
fetch the real modules from ``sys.modules`` to patch their internals.
"""
from __future__ import annotations

import os
import sys

import tools.download_file  # noqa: F401  (ensure submodules are imported)
import tools.run_code  # noqa: F401
import tools.send_request  # noqa: F401
from shared_store import BASE64_STORE, url_time
from tools.run_code import run_code, strip_code_fences

dl_mod = sys.modules["tools.download_file"]
run_code_mod = sys.modules["tools.run_code"]
send_mod = sys.modules["tools.send_request"]


def test_strip_code_fences():
    assert strip_code_fences("```python\nprint(1)\n```") == "print(1)"
    assert strip_code_fences("print(1)") == "print(1)"


def test_run_code_executes_and_returns_stdout():
    result = run_code.invoke({"code": "print('hello-sandbox')"})
    assert result["return_code"] == 0
    assert "hello-sandbox" in result["stdout"]


def test_run_code_wall_clock_timeout(monkeypatch):
    # Force a tiny timeout and run something that sleeps far longer.
    monkeypatch.setattr(run_code_mod._settings, "run_code_timeout", 2, raising=False)
    result = run_code.invoke({"code": "import time; time.sleep(30)"})
    assert result["return_code"] == -9
    assert "wall-clock limit" in result["stderr"]


def test_download_file_saves(monkeypatch, tmp_path):
    class FakeResp:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=8192):
            yield b"hello "
            yield b"world"

    class FakeRequests:
        @staticmethod
        def get(*a, **k):
            return FakeResp()

    monkeypatch.setattr(dl_mod, "requests", FakeRequests)
    monkeypatch.chdir(tmp_path)
    name = dl_mod.download_file.invoke({"url": "http://x/f.txt", "filename": "f.txt"})
    assert name == "f.txt"
    saved = tmp_path / "LLMFiles" / "f.txt"
    assert saved.read_bytes() == b"hello world"


def test_post_request_substitutes_base64(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"correct": True, "url": None}

    class FakeRequests:
        @staticmethod
        def post(url, json=None, headers=None):
            captured["payload"] = json
            return FakeResp()

    monkeypatch.setattr(send_mod, "requests", FakeRequests)
    os.environ["url"] = "http://quiz/1"
    url_time["http://quiz/1"] = 0
    BASE64_STORE["k1"] = "ENCODED_IMAGE_DATA"

    result = send_mod.post_request.invoke(
        {
            "url": "http://quiz/1/submit",
            "payload": {"answer": "BASE64_KEY:k1", "email": "e@x.com"},
        }
    )
    assert captured["payload"]["answer"] == "ENCODED_IMAGE_DATA"
    assert result == "Tasks completed"

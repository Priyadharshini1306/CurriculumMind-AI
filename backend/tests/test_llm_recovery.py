import asyncio
import json

import httpx

from app.services import llm_service

OK = {"choices": [{"message": {"content": "```json\n{\"a\": 1}\n```"}}]}


def _run(handler, monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(llm_service.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return asyncio.run(llm_service._chat([{"role": "user", "content": "x"}], 0.2, 100))


def _err(failed):
    return httpx.Response(400, json={"error": {"code": "json_validate_failed", "failed_generation": failed}})


def test_valid_failed_generation_is_salvaged(monkeypatch):
    calls = []
    out = _run(lambda req: (calls.append(1), _err('{"a": 1}'))[1], monkeypatch)
    assert json.loads(out) == {"a": 1} and len(calls) == 1


def test_truncated_output_retries_without_json_mode(monkeypatch):
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        return _err('{"a": [1, 2') if "response_format" in body else httpx.Response(200, json=OK)

    out = _run(handler, monkeypatch)
    assert json.loads(out) == {"a": 1}  # code fence stripped
    assert "response_format" not in bodies[1] and bodies[1]["max_tokens"] > bodies[0]["max_tokens"]

"""Groq client (OpenAI-compatible chat API). Every response is JSON, validated against a Pydantic model; invalid
output is retried once with the validation error fed back to the model."""
import asyncio
import json
import logging
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
MAX_RATE_LIMIT_RETRIES = 5  # Groq's free tier resets its per-minute token budget on its own; waiting always recovers


class LLMError(Exception):
    """Groq unreachable, or it returned output that never validated."""


class RateLimitError(LLMError):
    """Groq's per-minute request/token budget is exhausted. `retry_after` is how long it says to wait, in seconds."""

    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_reset(value: str | None) -> float | None:
    """Groq reports the same wait either as plain seconds ("Retry-After") or as e.g. "1m2.5s"/"34.8s" (the
    x-ratelimit-reset-* headers)."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    m = re.match(r"^(?:(\d+)m)?(\d+(?:\.\d+)?)s$", value.strip())
    if not m:
        return None
    minutes, seconds = m.groups()
    return (int(minutes) * 60 if minutes else 0) + float(seconds)


async def _chat(messages: list[dict], temperature: float, num_predict: int | None = None) -> str:
    s = get_settings()
    payload = {"model": s.groq_model, "messages": messages, "temperature": temperature,
               "response_format": {"type": "json_object"}}
    if num_predict:
        payload["max_tokens"] = num_predict
    headers = {"Authorization": f"Bearer {s.groq_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as c:
            r = await c.post(f"{s.groq_base_url}/chat/completions", json=payload, headers=headers)
            if r.status_code == 429:
                retry_after = (_parse_reset(r.headers.get("retry-after"))
                               or _parse_reset(r.headers.get("x-ratelimit-reset-tokens"))
                               or _parse_reset(r.headers.get("x-ratelimit-reset-requests"))
                               or 10)
                raise RateLimitError(f"Groq rate limit hit: {r.text[:300]}", retry_after)
            if r.status_code >= 400:
                raise LLMError(f"Groq request failed: {r.status_code} {r.text[:500]}")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError) as e:
        msg = str(e) or type(e).__name__
        raise LLMError(f"Groq request failed: {msg}") from e


async def generate_json(system: str, user: str, schema: type[T], temperature: float = 0.2, retries: int = 1,
                        schema_hint: str | None = None, num_ctx: int = 8192, num_predict: int | None = None) -> T:
    """`schema_hint` replaces the (long) auto-generated JSON schema with a short example, saving prompt tokens."""
    hint = schema_hint or ("Respond with a single JSON object only, matching this JSON schema:\n"
                           + json.dumps(schema.model_json_schema()))
    # Groq's free tier is metered per token, and gpt-oss's hidden reasoning tokens are billed the same as visible
    # output -- keeping the model's own "thinking" brief matters as much as keeping the JSON itself short.
    concise = "Think briefly and only as much as needed, then answer. Be concise: no repetition, no extra commentary."
    messages = [
        {"role": "system", "content": f"{system}\n\n{concise}\n\n{hint}"},
        {"role": "user", "content": user},
    ]
    last_err = ""
    rate_limit_attempts = 0
    attempt = 0
    while attempt <= retries:
        try:
            raw = await _chat(messages, temperature, num_predict)
        except RateLimitError as e:
            # doesn't consume a normal retry -- waiting out Groq's own per-minute reset always recovers, unlike a
            # genuine network/validation failure, so it gets its own budget instead of burning the caller's retries
            rate_limit_attempts += 1
            if rate_limit_attempts > MAX_RATE_LIMIT_RETRIES:
                raise
            log.warning("Groq rate-limited (attempt %d), waiting %.1fs: %s", rate_limit_attempts, e.retry_after, e)
            await asyncio.sleep(e.retry_after + 0.5)
            continue
        except LLMError as e:
            # a network-level failure is worth one retry on its own -- it costs nothing when Groq is healthy, and
            # turns one flaky call into a fast recovery instead of failing the whole job
            log.warning("LLM request failed (attempt %d): %s", attempt + 1, e)
            if attempt >= retries:
                raise
            attempt += 1
            continue
        try:
            return schema.model_validate_json(raw)
        except ValidationError as e:
            last_err = str(e)
            log.warning("LLM output failed validation (attempt %d): %s", attempt + 1, last_err[:300])
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That JSON was invalid: {last_err[:800]}\nReturn corrected JSON only."}]
            attempt += 1
    raise LLMError(f"LLM returned invalid JSON after {retries + 1} attempts: {last_err[:300]}")

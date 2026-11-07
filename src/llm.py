"""Provider-agnostic LLM call with disk cache, cost ledger and retries.

Usage:
    from src.llm import call_llm
    result = call_llm("Return JSON with key 'x'.", image=png_bytes, source="doc1:p3")

Provider/model/prices come from .env (see .env.example).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from PIL import Image
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from src.config import Settings, get_settings
from src.image_utils import to_png_bytes

LEDGER_FIELDS = [
    "timestamp", "source", "provider", "model",
    "input_tokens", "output_tokens", "cost_usd", "cache_hit",
]
JSON_INSTRUCTION = "Respond with a single valid JSON object and nothing else."
SUPPORTED_PROVIDERS = ("openai", "gemini", "anthropic")


class LLMJSONError(ValueError):
    """Model output was not valid JSON. `.raw` holds the text (it is still cached)."""

    def __init__(self, raw: str):
        super().__init__(f"Could not parse JSON from model output: {raw[:200]!r}")
        self.raw = raw


# ---------------------------------------------------------------- public API


def call_llm(
    prompt: str,
    image: bytes | Image.Image | None = None,
    model: str | None = None,
    json_output: bool = True,
    max_output_tokens: int | None = None,
    source: str = "",
) -> Any:
    """Send prompt (+ optional PNG image) to the configured provider.

    Returns parsed JSON (dict/list) if json_output, else the raw text.
    `source` is a free-form label (e.g. "file.pdf:p3") written to the ledger.
    """
    settings = get_settings()
    provider = settings.llm_provider
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {SUPPORTED_PROVIDERS}, got {provider!r}")
    model = model or settings.llm_model
    if not model:
        raise ValueError("No model given and LLM_MODEL is not set")
    image_bytes = to_png_bytes(image) if isinstance(image, Image.Image) else image
    max_tokens = max_output_tokens or settings.max_output_tokens

    key = cache_key(prompt, image_bytes, model)
    cache_path = settings.cache_dir / f"{key}.json"

    if cache_path.exists():
        text = json.loads(cache_path.read_text())["text"]
        _log_usage(settings, source, provider, model, 0, 0, cache_hit=True)
    else:
        retryer = Retrying(
            retry=retry_if_exception(is_transient_error),
            stop=stop_after_attempt(settings.max_attempts),
            wait=wait_exponential(multiplier=1, max=settings.retry_max_wait),
            reraise=True,
        )
        text, in_tok, out_tok = retryer(
            _call_provider, provider, model, prompt, image_bytes, json_output, max_tokens
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "provider": provider, "model": model, "text": text,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "created": _now(),
        }))
        _log_usage(settings, source, provider, model, in_tok, out_tok, cache_hit=False)

    return parse_json(text) if json_output else text


def cache_key(prompt: str, image_bytes: bytes | None, model: str) -> str:
    h = hashlib.sha256()
    for part in (prompt.encode(), image_bytes or b"", model.encode()):
        # Length-prefix each part so ("ab", "c") and ("a", "bc") never collide.
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.hexdigest()


def cost_usd(input_tokens: int, output_tokens: int, settings: Settings) -> float:
    return (
        input_tokens / 1_000_000 * settings.price_input_per_1m
        + output_tokens / 1_000_000 * settings.price_output_per_1m
    )


def parse_json(text: str) -> Any:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMJSONError(text) from e


def is_transient_error(exc: BaseException) -> bool:
    """Retry only rate limits, timeouts, connection and 5xx errors."""
    transient = (
        openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError,
        anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError,
        genai_errors.ServerError,
    )
    if isinstance(exc, transient):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 529:  # overloaded
        return True
    if isinstance(exc, genai_errors.ClientError) and exc.code == 429:
        return True
    return False


# ---------------------------------------------------------------- providers


@lru_cache(maxsize=None)
def _get_client(provider: str, api_key: str, base_url: str | None):
    if provider == "openai":
        return openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    if provider == "anthropic":
        return anthropic.Anthropic(api_key=api_key, max_retries=0)
    if provider == "gemini":
        return genai.Client(api_key=api_key)
    raise ValueError(provider)


def _call_provider(
    provider: str, model: str, prompt: str, image: bytes | None,
    json_output: bool, max_tokens: int,
) -> tuple[str, int, int]:
    """Make one real API call. Returns (text, input_tokens, output_tokens)."""
    s = get_settings()
    client = _get_client(provider, s.llm_api_key, s.llm_base_url)
    return {"openai": _openai, "anthropic": _anthropic, "gemini": _gemini}[provider](
        client, model, prompt, image, json_output, max_tokens
    )


def _openai(client, model, prompt, image, json_output, max_tokens):
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image:
        url = "data:image/png;base64," + base64.b64encode(image).decode()
        content.append({"type": "image_url", "image_url": {"url": url}})
    messages = [{"role": "user", "content": content}]
    kwargs: dict = {}
    if json_output:
        messages.insert(0, {"role": "system", "content": JSON_INSTRUCTION})
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=model, messages=messages, max_completion_tokens=max_tokens, **kwargs
    )
    usage = resp.usage
    return resp.choices[0].message.content or "", usage.prompt_tokens, usage.completion_tokens


def _anthropic(client, model, prompt, image, json_output, max_tokens):
    content: list[dict] = []
    if image:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png",
                       "data": base64.b64encode(image).decode()},
        })
    content.append({"type": "text", "text": prompt})
    kwargs: dict = {"system": JSON_INSTRUCTION} if json_output else {}
    resp = client.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}], **kwargs,
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    u = resp.usage
    # Prompt-cache reads/writes are billed as input too.
    in_tok = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
    return text, in_tok, u.output_tokens


def _gemini(client, model, prompt, image, json_output, max_tokens):
    contents: list = []
    if image:
        contents.append(genai_types.Part.from_bytes(data=image, mime_type="image/png"))
    contents.append(prompt)
    config = genai_types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        system_instruction=JSON_INSTRUCTION if json_output else None,
        response_mime_type="application/json" if json_output else None,
    )
    resp = client.models.generate_content(model=model, contents=contents, config=config)
    u = resp.usage_metadata
    # Thinking tokens are billed as output.
    out_tok = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
    return resp.text or "", u.prompt_token_count or 0, out_tok


# ---------------------------------------------------------------- ledger


def _log_usage(settings: Settings, source, provider, model, in_tok, out_tok, cache_hit):
    path: Path = settings.ledger_path
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "timestamp": _now(), "source": source, "provider": provider, "model": model,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": f"{cost_usd(in_tok, out_tok, settings):.6f}",
            "cache_hit": cache_hit,
        })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

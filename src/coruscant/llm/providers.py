"""Provider clients — Anthropic and the OpenAI-compatible family.

Two wire formats cover everything we need: Anthropic's Messages API, and the
OpenAI chat-completions shape (which OpenAI, Ollama, and LM Studio all speak, so
"local Gemma" is just an OpenAI-compatible provider with a localhost base_url and
no key). Stdlib HTTP only — no SDK dependency.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from coruscant.llm.config import ProviderConfig


class LLMError(Exception):
    """A provider call failed (missing key, network, or API error)."""


def _post(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 (admin-configured host)
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"HTTP {exc.code} from {url}: {body}") from exc
    except (URLError, TimeoutError) as exc:
        raise LLMError(f"Could not reach {url}: {exc}") from exc
    except (ValueError, KeyError) as exc:
        raise LLMError(f"Bad response from {url}: {exc}") from exc


def complete(
    provider: ProviderConfig,
    model: str,
    *,
    system: str,
    user: str,
    max_tokens: int = 1024,
    timeout: float = 90.0,
) -> str:
    """Run one completion against the provider; returns the assistant text."""
    base = provider.base_url.rstrip("/")
    if provider.kind == "anthropic":
        if not provider.api_key:
            raise LLMError("Anthropic API key is not set.")
        data = _post(
            f"{base}/v1/messages",
            {"x-api-key": provider.api_key, "anthropic-version": "2023-06-01"},
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout,
        )
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        if not text:
            raise LLMError(f"Empty completion from Anthropic model '{model}'.")
        return text

    if provider.kind == "openai":
        headers: dict[str, str] = {}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        data = _post(
            f"{base}/chat/completions",
            headers,
            {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout,
        )
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI-compatible response: {exc}") from exc

    raise LLMError(f"Unknown provider kind '{provider.kind}'.")

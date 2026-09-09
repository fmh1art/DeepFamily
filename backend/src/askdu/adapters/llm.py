from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, ClassVar, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AzureOpenAI,
    OpenAI,
    OpenAIError,
)
from openai.types.chat import ChatCompletionMessageParam

from askdu.application.ports import ChatModel


class ChatModelError(RuntimeError):
    """Raised when a provider response cannot satisfy the local model contract."""


TokenField = Literal["max_tokens", "max_completion_tokens"]
AuthScheme = Literal["bearer", "api_key"]
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _messages(system: str, user: str) -> list[ChatCompletionMessageParam]:
    if not system.strip() or not user.strip():
        raise ValueError("system and user messages must be non-empty")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _provider_url(raw: str, label: str) -> httpx.URL:
    parsed = httpx.URL(raw.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.host
        or parsed.fragment
        or parsed.userinfo
    ):
        raise ValueError(
            f"{label} must be an absolute HTTP(S) URL without credentials or a fragment"
        )
    if parsed.scheme == "http" and parsed.host not in _LOOPBACK_HOSTS:
        raise ValueError(f"{label} must use HTTPS except for a loopback test server")
    return parsed


class OpenAICompatibleChatModel(ChatModel):
    """Minimal server-side adapter for an OpenAI-compatible chat endpoint.

    The adapter deliberately accepts no per-request base URL, key, or model.
    Credentials are fixed when the server constructs the instance and are never
    included in returned domain objects.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        token_field: TokenField = "max_completion_tokens",
        trust_env_proxy: bool = False,
    ) -> None:
        if not base_url.strip() or not api_key.strip() or not model.strip():
            raise ValueError("base_url, api_key, and model are required")
        if token_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("unsupported token field")
        parsed = _provider_url(base_url, "base_url")
        if parsed.query or parsed.path.rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                "a complete Chat Completions endpoint must use direct_chat_completions mode"
            )
        self._model = model
        self._token_field = token_field
        self._http_client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=trust_env_proxy,
        )
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=self._http_client,
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2_000,
        temperature: float = 0.0,
    ) -> str:
        messages = _messages(system, user)
        if self._token_field == "max_completion_tokens":
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise ChatModelError("Provider returned no textual completion")
        return content.strip()


class AzureChatCompletionsModel(ChatModel):
    """Use an Azure-compatible gateway root with an explicit API version.

    The configured project URL is a gateway root, not the final POST target.
    ``AzureOpenAI`` appends the deployment and Chat Completions route while this
    adapter keeps the API version from the user-supplied query string. The
    pinned GPT-5.5 gateway rejects an explicit ``temperature=0``, so the field
    is deliberately omitted and the prompt/action validators provide the
    deterministic boundary instead.
    """

    def __init__(
        self,
        *,
        gateway_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        token_field: TokenField = "max_completion_tokens",
        trust_env_proxy: bool = False,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not gateway_url.strip() or not api_key.strip() or not model.strip():
            raise ValueError("gateway_url, api_key, and model are required")
        if token_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("unsupported token field")
        _provider_url(gateway_url, "gateway_url")
        split = urlsplit(gateway_url.strip())
        query = parse_qsl(split.query, keep_blank_values=True)
        if len(query) != 1 or query[0][0] != "api-version" or not query[0][1]:
            raise ValueError("Azure gateway URL must contain exactly one non-empty api-version")

        azure_endpoint = urlunsplit((split.scheme, split.netloc, split.path.rstrip("/"), "", ""))
        self._model = model
        self._token_field = token_field
        self._http_client = (
            http_client
            if http_client is not None
            else httpx.Client(
                timeout=timeout_seconds,
                follow_redirects=False,
                trust_env=trust_env_proxy,
            )
        )
        self._client = AzureOpenAI(
            api_key=api_key,
            api_version=query[0][1],
            azure_endpoint=azure_endpoint,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=self._http_client,
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2_000,
        temperature: float = 0.0,
    ) -> str:
        if temperature != 0.0:
            raise ValueError("The pinned Azure Chat profile only supports default temperature")
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _messages(system, user),
            self._token_field: max_tokens,
        }
        try:
            response = self._client.chat.completions.create(**kwargs)
        except APIStatusError as exc:
            raise ChatModelError(f"Provider request failed with HTTP {exc.status_code}") from None
        except (APIConnectionError, APITimeoutError):
            raise ChatModelError("Provider request failed after bounded retries") from None
        except OpenAIError:
            raise ChatModelError("Provider response did not satisfy the client contract") from None

        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise ChatModelError("Provider returned no textual completion")
        return content.strip()


class DirectChatCompletionsModel(ChatModel):
    """POST Chat Completions JSON to an exact, server-configured endpoint.

    Some compatible gateways expose a complete URL, including a path and query
    string, rather than an OpenAI-style ``/v1`` base URL. Using the OpenAI client
    with such a URL appends ``/chat/completions`` in the wrong place. This adapter
    preserves the configured endpoint byte-for-byte and supports the two common
    server-side authentication header conventions without exposing either one to
    an API request.
    """

    _RETRYABLE_STATUS_CODES: ClassVar[set[int]] = {
        408,
        409,
        425,
        429,
        500,
        502,
        503,
        504,
    }

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        auth_scheme: AuthScheme = "bearer",
        token_field: TokenField = "max_completion_tokens",
        trust_env_proxy: bool = False,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not endpoint.strip() or not api_key.strip() or not model.strip():
            raise ValueError("endpoint, api_key, and model are required")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if auth_scheme not in {"bearer", "api_key"}:
            raise ValueError("unsupported authentication scheme")
        if token_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("unsupported token field")
        _provider_url(endpoint, "endpoint")

        self._endpoint = endpoint.strip()
        self._model = model
        self._max_retries = max_retries
        self._token_field = token_field
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=trust_env_proxy,
        )
        self._sleeper = sleeper
        self._auth_header = "Authorization" if auth_scheme == "bearer" else "api-key"
        self._auth_value = f"Bearer {api_key}" if auth_scheme == "bearer" else api_key

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2_000,
        temperature: float = 0.0,
    ) -> str:
        messages = _messages(system, user)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            self._token_field: max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Content-Type": "application/json",
            self._auth_header: self._auth_value,
        }

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(self._endpoint, headers=headers, json=payload)
            except httpx.RequestError:
                if attempt >= self._max_retries:
                    raise ChatModelError("Provider request failed after bounded retries") from None
                self._sleeper(self._retry_delay(attempt, None))
                continue

            if response.status_code in self._RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                self._sleeper(self._retry_delay(attempt, response))
                continue
            if not 200 <= response.status_code < 300:
                raise ChatModelError(f"Provider request failed with HTTP {response.status_code}")

            try:
                body: object = response.json()
            except ValueError:
                raise ChatModelError("Provider returned invalid JSON") from None
            return self._extract_text(body)

        raise ChatModelError("Provider request failed after bounded retries")  # pragma: no cover

    @staticmethod
    def _extract_text(body: object) -> str:
        if not isinstance(body, dict):
            raise ChatModelError("Provider response is not a JSON object")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ChatModelError("Provider returned no completion choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ChatModelError("Provider returned no completion message")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [
                item.get("text", "").strip()
                for item in content
                if isinstance(item, dict)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            ]
            rendered = "".join(parts).strip()
            if rendered:
                return rendered
        raise ChatModelError("Provider returned no textual completion")

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    return min(max(float(retry_after), 0.0), 2.0)
                except ValueError:
                    pass
        return min(0.25 * (2**attempt), 2.0)

"""Environment-configured client for an OpenAI-compatible NVIDIA endpoint."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class ModelError(RuntimeError):
    """Safe, user-displayable model failure without provider error details."""


@dataclass(frozen=True)
class GenerationSettings:
    temperature: float = 1.0
    top_p: float = 0.95
    max_tokens: int = 16384
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "GenerationSettings":
        try:
            return cls(
                temperature=float(os.getenv("NVIDIA_TEMPERATURE", "1.0")),
                top_p=float(os.getenv("NVIDIA_TOP_P", "0.95")),
                max_tokens=int(os.getenv("NVIDIA_MAX_TOKENS", "16384")),
                timeout_seconds=float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "60")),
            )
        except ValueError as exc:
            raise ModelError("Model generation settings must use valid numeric values.") from exc

    def as_metadata(self) -> dict[str, int | float]:
        """Return reproducibility settings safe to show; no credentials are included."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    settings: GenerationSettings

    @classmethod
    def from_env(cls) -> "ModelConfig":
        # dotenv is optional for tests and supplied through requirements for the app.
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv()

        key = os.getenv("NVIDIA_API_KEY", "").strip()
        base_url = os.getenv("NVIDIA_BASE_URL", "").strip()
        model = os.getenv("NVIDIA_MODEL", "").strip()
        if not (key and base_url and model):
            raise ModelError(
                "Configure NVIDIA_API_KEY, NVIDIA_BASE_URL, and NVIDIA_MODEL in .env to enable chat."
            )
        return cls(key, base_url, model, GenerationSettings.from_env())


def _make_client(config: ModelConfig) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelError("The OpenAI client package is unavailable. Install project requirements.") from exc
    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.settings.timeout_seconds,
    )


def generate_reply(messages: list[dict[str, str]], config: ModelConfig, client: Any = None) -> str:
    """Call the configured chat completion endpoint and return plain assistant text."""
    if not messages or any(m.get("role") not in {"system", "user", "assistant"} for m in messages):
        raise ModelError("The model request could not be prepared.")
    api_client = client if client is not None else _make_client(config)
    settings = config.settings
    try:
        response = api_client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=settings.temperature,
            top_p=settings.top_p,
            max_tokens=settings.max_tokens,
            stream=False,
        )
    except Exception as exc:
        # Do not include exception text: provider errors can echo request metadata.
        error_type = type(exc).__name__
        if "Timeout" in error_type or isinstance(exc, TimeoutError):
            raise ModelError("The model request timed out. Please try again.") from None
        if "RateLimit" in error_type:
            raise ModelError("The model is temporarily rate limited. Please try again later.") from None
        if "Connection" in error_type or "APIStatus" in error_type or "APIError" in error_type:
            raise ModelError("The model endpoint is unavailable. Check configuration and try again.") from None
        raise ModelError("The model request failed. Please check the endpoint configuration and try again.") from None

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        raise ModelError("The model returned an unreadable response.") from None
    if not isinstance(content, str) or not content.strip():
        raise ModelError("The model returned an empty response. Please try again.")
    return content.strip()

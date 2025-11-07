"""LLM client factory supporting multiple providers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from openai import OpenAI

from agent.core.event_log import append_event


@dataclass
class LLMClient:
    """Wrapper around an SDK client with provider metadata."""

    provider: str
    client: Any
    supports_quota: bool = False

    @property
    def responses(self) -> Any:  # pragma: no cover - simple delegation
        return self.client.responses


def _normalise_provider(value: Optional[str]) -> str:
    if not value:
        return "scaleway"
    return value.strip().lower() or "scaleway"


def _build_openai_client() -> Optional[LLMClient]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        append_event(
            level="warning",
            source="llm_client",
            message="openai_api_key_missing",
            details={"provider": "openai"},
        )
        return None
    client = OpenAI(api_key=api_key)
    append_event(
        level="info",
        source="llm_client",
        message="client_initialized",
        details={"provider": "openai"},
    )
    return LLMClient(provider="openai", client=client, supports_quota=True)


def _build_scaleway_client() -> Optional[LLMClient]:
    api_key = os.environ.get("SCALEWAY_API_KEY")
    if not api_key:
        append_event(
            level="warning",
            source="llm_client",
            message="scaleway_api_key_missing",
            details={"provider": "scaleway"},
        )
        return None

    base_url = os.environ.get("SCALEWAY_API_BASE", "https://api.scaleway.com/ai/v1alpha1")
    base_url = base_url.rstrip("/")

    header_name = os.environ.get("SCALEWAY_API_KEY_HEADER", "")
    default_headers = {}
    if header_name:
        default_headers[header_name] = api_key
        # Some deployments still expect a bearer token even when a custom header is used.
        api_key = os.environ.get("SCALEWAY_BEARER_TOKEN", api_key)

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers or None,
    )
    append_event(
        level="info",
        source="llm_client",
        message="client_initialized",
        details={"provider": "scaleway", "base_url": base_url},
    )
    return LLMClient(provider="scaleway", client=client, supports_quota=False)


def create_llm_client(provider: Optional[str] = None) -> Optional[LLMClient]:
    """Instantiate an LLM client for the requested provider."""

    resolved = _normalise_provider(provider or os.environ.get("LLM_PROVIDER"))
    if resolved == "openai":
        return _build_openai_client()
    if resolved == "scaleway":
        return _build_scaleway_client()

    append_event(
        level="warning",
        source="llm_client",
        message="unsupported_provider",
        details={"provider": resolved},
    )
    return None

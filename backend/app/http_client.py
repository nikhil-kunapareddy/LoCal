"""Shared async HTTP client and JSON fetch helper.

A single ``httpx.AsyncClient`` is reused across requests (connection pooling) and
carries an explicit timeout, so a slow external API can never hang a request
indefinitely — the failure mode the previous in-process Next.js ``fetchJSON`` had.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


class UpstreamError(RuntimeError):
    """Raised when an external data source returns a non-2xx or is unreachable."""


_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        timeout = get_settings().request_timeout_seconds
        _client = httpx.AsyncClient(timeout=timeout)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    """GET ``url`` and return parsed JSON, raising :class:`UpstreamError` on failure.

    Mirrors the TS ``fetchJSON`` contract (throw on non-ok) but with a bounded
    timeout from settings.
    """
    client = get_client()
    try:
        res = await client.get(url, headers=headers or {})
    except httpx.HTTPError as exc:
        raise UpstreamError(f"request to {url} failed: {exc}") from exc
    if res.status_code >= 400:
        raise UpstreamError(f"HTTP {res.status_code} from {url}")
    return res.json()

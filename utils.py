"""Utility helpers shared across workflow modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

from oxygent.schemas import OxyRequest, OxyResponse, OxyState


def sanitize(value: Any) -> Any:
    """Recursively convert values into JSON-serialisable structures."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return repr(value)


async def call_and_unpack(
    oxy_request: OxyRequest,
    *,
    callee: str,
    arguments: Optional[dict[str, Any]] = None,
) -> Any:
    """Invoke a named oxy and ensure completion, returning the output."""

    response: OxyResponse = await oxy_request.call(
        callee=callee, arguments=arguments or {}
    )
    if response.state is not OxyState.COMPLETED:
        raise RuntimeError(f"调用 {callee} 失败: {response.output}")
    return response.output


def parse_llm_token_limits(pairs: Sequence[str]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for item in pairs:
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid token limit format: {item}. Expected model=limit.")
        model, value = item.split("=", 1)
        model = model.strip()
        if not model:
            raise ValueError(f"Invalid model name in token limit: {item}")
        try:
            limit = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid token limit number in: {item}") from exc
        if limit <= 0:
            raise ValueError(f"Token limit must be positive in: {item}")
        limits[model] = limit
    return limits


"""Shared blackboard helpers exposed as FunctionTools."""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Iterable, Optional

from oxygent.schemas import OxyRequest

from .constants import BLACKBOARD_STATE_KEY
from .utils import sanitize

BLACKBOARD_LOCK = asyncio.Lock()


def _require_valid_request(oxy_request: OxyRequest) -> OxyRequest:
    if oxy_request is None or oxy_request.mas is None:
        raise RuntimeError("blackboard 操作需要有效的 OxyRequest")
    return oxy_request


async def write_blackboard(
    namespace: str,
    payload: Any,
    merge: bool = True,
    oxy_request: OxyRequest = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Write (or merge) payload into the shared blackboard namespace."""

    oxy_request = _require_valid_request(oxy_request)

    async with BLACKBOARD_LOCK:
        board = oxy_request.mas.global_data.setdefault(BLACKBOARD_STATE_KEY, {})
        sanitized_payload = sanitize(payload)
        if merge and isinstance(sanitized_payload, dict):
            existing = board.get(namespace, {})
            if isinstance(existing, dict):
                existing.update(sanitized_payload)
                board[namespace] = existing
            else:
                board[namespace] = sanitized_payload
        else:
            board[namespace] = sanitized_payload
        snapshot = copy.deepcopy(board[namespace])
    return {"namespace": namespace, "snapshot": snapshot}


async def read_blackboard(
    namespace: str,
    default: Optional[Any] = None,
    oxy_request: OxyRequest = None,  # type: ignore[assignment]
) -> Any:
    """Read from the shared blackboard namespace."""

    oxy_request = _require_valid_request(oxy_request)

    async with BLACKBOARD_LOCK:
        board = oxy_request.mas.global_data.get(BLACKBOARD_STATE_KEY, {})
        return copy.deepcopy(board.get(namespace, sanitize(default)))


async def reset_blackboard(
    namespaces: Optional[Iterable[str]] = None,
    oxy_request: OxyRequest = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Reset specific namespaces or clear the entire blackboard."""

    oxy_request = _require_valid_request(oxy_request)

    async with BLACKBOARD_LOCK:
        board = oxy_request.mas.global_data.setdefault(BLACKBOARD_STATE_KEY, {})
        if namespaces is None:
            board.clear()
        else:
            for ns in namespaces:
                board.pop(ns, None)
        snapshot = copy.deepcopy(board)
    return {"current_namespaces": list(snapshot.keys()), "snapshot": snapshot}


"""Implementations of FunctionTool callables."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

import httpx
from PIL import Image

from .utils import sanitize

SAFE_BUILTINS = {
    "range": range,
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "abs": abs,
    "float": float,
    "int": int,
    "str": str,
}


async def load_tasks(data_path: str, task_limit: Optional[int] = None) -> dict[str, Any]:
    """读取 JSONL 数据集并返回任务列表。"""

    path = Path(data_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"数据集不存在: {path}")

    def _read() -> dict[str, Any]:
        tasks: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                tasks.append(json.loads(line))
                if task_limit and len(tasks) >= task_limit:
                    break
        return {
            "tasks": [sanitize(task) for task in tasks],
            "count": len(tasks),
            "source": str(path.resolve()),
        }

    return await asyncio.to_thread(_read)


async def parse_media(
    file_path: str,
    text_preview: int = 400,
    sample_every: int = 512,
) -> dict[str, Any]:
    """对多模态文件进行基础解析。"""

    path = Path(file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"附件不存在: {path}")

    suffix = path.suffix.lower()

    def _summarise_text() -> dict[str, Any]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        preview = text[:text_preview]
        return {
            "type": "text",
            "preview": preview,
            "length": len(text),
            "path": str(path.resolve()),
        }

    def _summarise_csv() -> dict[str, Any]:
        rows: list[list[str]] = []
        with path.open("r", encoding="utf-8", errors="ignore") as file:
            for index, line in enumerate(file):
                rows.append(line.strip().split(","))
                if index >= sample_every:
                    break
        header = rows[0] if rows else []
        return {
            "type": "table",
            "header": header,
            "preview_rows": rows[1:sample_every],
            "path": str(path.resolve()),
        }

    def _summarise_image() -> dict[str, Any]:
        with Image.open(path) as image:
            return {
                "type": "image",
                "mode": image.mode,
                "size": image.size,
                "format": image.format,
                "path": str(path.resolve()),
            }

    if suffix in {".txt", ".md", ".json", ".log"}:
        return await asyncio.to_thread(_summarise_text)
    if suffix == ".csv":
        return await asyncio.to_thread(_summarise_csv)
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif"}:
        return await asyncio.to_thread(_summarise_image)

    return {
        "type": "binary",
        "path": str(path.resolve()),
        "size": path.stat().st_size,
        "hint": "暂未提供专用解析，已返回基础信息。",
    }


async def retrieve_open_web(
    query: str,
    max_results: int = 3,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """使用 DuckDuckGo API 进行简单检索。"""

    params = {
        "q": query,
        "format": "json",
        "no_redirect": 1,
        "no_html": 1,
    }
    headers = {"User-Agent": "OxyGent-Workflow/1.0"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://api.duckduckgo.com/", params=params, headers=headers
            )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # pragma: no cover - 网络依赖
        return {"query": query, "results": [], "error": str(exc)}

    results: list[dict[str, Any]] = []
    for entry in data.get("RelatedTopics", []):
        if "Text" in entry and "FirstURL" in entry:
            results.append({"title": entry.get("Text"), "url": entry.get("FirstURL")})
        for sub_entry in entry.get("Topics", []):
            if "Text" in sub_entry and "FirstURL" in sub_entry:
                results.append(
                    {"title": sub_entry.get("Text"), "url": sub_entry.get("FirstURL")}
                )
        if len(results) >= max_results:
            break

    return {"query": query, "results": results[:max_results]}


async def validate_answer(
    answer: Any,
    required_keys: Optional[list[str]] = None,
    numeric_bounds: Optional[tuple[float, float]] = None,
) -> dict[str, Any]:
    """根据约束校验答案。"""

    if isinstance(answer, str):
        try:
            parsed = json.loads(answer)
        except json.JSONDecodeError:
            parsed = {"text": answer}
    else:
        parsed = answer or {}

    result = {
        "is_valid": True,
        "checks": [],
        "structured_answer": sanitize(parsed),
    }

    if required_keys:
        missing = [key for key in required_keys if key not in parsed]
        result["checks"].append({"type": "required_keys", "missing": missing})
        if missing:
            result["is_valid"] = False

    if numeric_bounds and isinstance(parsed, dict):
        lower, upper = numeric_bounds
        numeric_values = [value for value in parsed.values() if isinstance(value, (int, float))]
        violations = [value for value in numeric_values if not (lower <= value <= upper)]
        result["checks"].append(
            {"type": "numeric_bounds", "bounds": [lower, upper], "violations": violations}
        )
        if violations:
            result["is_valid"] = False

    return result


async def write_result(
    output_path: str,
    content: str,
    overwrite: bool = True,
) -> dict[str, Any]:
    """写入结果文件。"""

    path = Path(output_path).expanduser()

    def _write() -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if overwrite else "x"
        with path.open(mode, encoding="utf-8") as file:
            file.write(content)
        return {"path": str(path.resolve()), "bytes": len(content)}

    return await asyncio.to_thread(_write)

